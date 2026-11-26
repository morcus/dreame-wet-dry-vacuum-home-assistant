"""Data coordinator for Dreame wet & dry vacuum (MQTT push + HTTP seed)."""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DreameAPI, DreameAPIError, DreameAuthError
from .const import (
    CONSUMABLE_MAX_KEYS,
    DOMAIN,
    H15_BUTTON_COMMANDS,
    H15_CONTROL_KEYS,
    H15_TARGETED_KEYS,
    KNOWN_BINARY_PROPS,
    KNOWN_MQTT_PROPS,
    KNOWN_NUMBER_PROPS,
    KNOWN_SELECT_PROPS,
    KNOWN_SWITCH_PROPS,
    MQTT_ONLY_KEYS,
    STATUS_GROUP,
    build_h15_command_plan,
    build_h15_write_plan,
    build_schedule_day_plan,
    is_h15_pro_heat,
)
from .dreame_mqtt import DreameMqttClient

_LOGGER = logging.getLogger(__name__)

HTTP_REFRESH = timedelta(minutes=5)

_POLL_KEYS: list[str] = sorted(
    {
        f"{s}.{p}"
        for s, p in (
            set(KNOWN_MQTT_PROPS)
            | set(KNOWN_BINARY_PROPS)
            | set(KNOWN_SWITCH_PROPS)
            | set(KNOWN_NUMBER_PROPS)
            | set(KNOWN_SELECT_PROPS)
        )
        - MQTT_ONLY_KEYS
    }
    | set(CONSUMABLE_MAX_KEYS)
)

# Expanded H15 discovery.
#
# The first mapping build and the explicit "Refresh mapping snapshot" button
# scan these ranges only. The normal 5-minute poll reads only properties that
# were actually discovered, so this does not create a permanent large poll.
#
# The Dreame common plugin defines services through at least SIID 26 and also
# contains SIID 100 (DeviceControl), so we deliberately include 1..40 + 100.
# PIID 120 covers the newly found H15 properties above the previous PIID-80
# limit (for example 1.81, 1.82 and 1.83).
_H15_SCAN_SIIDS: tuple[int, ...] = tuple(range(1, 41)) + (100,)
_H15_PIID_RANGE = range(1, 121)
_H15_DISCOVERY_CHUNK = 100
_H15_DIRECT_CHUNK = 50

# Settings values the device only reports when the app opens a settings page.
# They are cached across restarts so controls are not "unknown" after every
# restart. The lifting-arm bitfield (24.1) is deliberately excluded: writes to
# it are bit-merged, so a stale cached value must never be used as a base.
_H15_PERSIST_EXCLUDE: set[tuple[int, int]] = {(24, 1)}
_H15_SETTINGS_SAVE_DELAY = 10
# Values the app assumes when the device never reports them
# (HomePage registerDeviceData). 26.2 Smart Moisture Protection: 0 = on.
_H15_APP_DEFAULTS: dict[tuple[int, int], Any] = {(26, 2): 0}
_H15_EXTRAS_INTERVAL = timedelta(hours=1)
_H15_SESSION_DUR_PIIDS = (189, 190, 191)


class DreameWetDryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Hold live device state from MQTT plus cloud polling."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: DreameAPI,
        device_id: str,
        device_info: dict[str, Any],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{device_id}",
            update_interval=None,
        )
        self.api = api
        self.device_id = device_id
        self.device_info_raw = device_info
        self.snapshot: dict[str, Any] = {}
        self.props: dict[tuple[int, int], Any] = {}
        self.new_prop_callback: Callable[[set[tuple[int, int]]], None] | None = None
        self.mqtt: DreameMqttClient | None = None
        self._unsub_poll: Callable[[], None] | None = None

        self._model = str(device_info.get("model") or "")
        self._is_h15 = is_h15_pro_heat(self._model)
        self._h15_discovery_done = False
        self._h15_poll_keys: list[str] = []

        self._h15_mapping_snapshot: dict[str, Any] = {}
        self._h15_last_changes: dict[str, dict[str, Any]] = {}
        self._h15_last_scan: datetime | None = None
        self._h15_write_lock = asyncio.Lock()
        self._h15_settings_store: Store = Store(
            hass, 1, f"{DOMAIN}.{device_id}.h15_settings"
        )
        self._h15_settings_restored = False
        self.h15_app_defaults: set[tuple[int, int]] = set()
        self.h15_clean_stats: dict[str, Any] = {}
        self.h15_firmware: dict[str, Any] = {}
        self._h15_extras_at: datetime | None = None
        self._h15_extras_task: asyncio.Task | None = None

    @property
    def model(self) -> str:
        """Return the Dreame model identifier."""
        return self._model

    @property
    def is_h15_pro_heat(self) -> bool:
        """Return whether this coordinator is for the H15 Pro Heat profile."""
        return self._is_h15

    @property
    def h15_last_changes(self) -> dict[str, dict[str, Any]]:
        """Return changes detected by the last manual H15 mapping scan."""
        return self._h15_last_changes

    @property
    def h15_last_scan(self) -> datetime | None:
        """Return timestamp of the last manual/initial H15 mapping scan."""
        return self._h15_last_scan

    @callback
    def start_polling(self) -> None:
        """Start the fixed-interval safety-net poll."""
        self._unsub_poll = async_track_time_interval(
            self.hass, self._async_scheduled_poll, HTTP_REFRESH
        )

    @callback
    def stop_polling(self) -> None:
        """Stop the fixed-interval poll."""
        if self._unsub_poll:
            self._unsub_poll()
            self._unsub_poll = None

    async def _async_scheduled_poll(self, _now: datetime) -> None:
        await self.async_refresh()

    async def async_shutdown(self) -> None:
        self.stop_polling()
        await super().async_shutdown()

    def start_mqtt(self) -> None:
        """Create and start the MQTT client.

        This performs blocking SSL setup and is called from an executor.
        """
        snap = self.device_info_raw
        bind = snap.get("bindDomain") or snap.get("bind_domain")
        if not bind:
            _LOGGER.info("Device metadata has no bindDomain; using HTTP polling")
            return

        self.mqtt = DreameMqttClient(
            uid=self.api.uid,
            access_token=self.api.access_token,
            device_id=self.device_id,
            model=snap.get("model", ""),
            bind_domain=bind,
            on_update=self._handle_mqtt_update,
        )
        self.mqtt.start()

    async def async_set_prop(self, siid: int, piid: int, value: Any) -> bool:
        """Write a property, then optimistically update state on success."""
        ok = await self.api.set_property(self.device_id, siid, piid, value)
        if ok:
            self.props[(siid, piid)] = value
            self.async_set_updated_data(self._build_data())
        else:
            _LOGGER.warning(
                "set_property %s.%s=%s rejected by device", siid, piid, value
            )
        return ok

    async def async_set_h15_setting(
        self, key: tuple[int, int], value: int, *, arm_bit: int | None = None
    ) -> None:
        """Write an H15 setting batch without using legacy H14 mappings."""
        if not self._is_h15:
            raise ValueError("H15 controls cannot write to this device model")
        async with self._h15_write_lock:
            if arm_bit is not None or key == (24, 1):
                # Refresh the shared bitfield when live RPC is available.
                # A sleeping device may return no value; never invent a default.
                rows = await self.api.get_properties(
                    self.device_id, [{"siid": 24, "piid": 1}]
                )
                for row in rows:
                    if (
                        row.get("code") == 0 and row.get("siid") == 24
                        and row.get("piid") == 1 and row.get("value") is not None
                    ):
                        self.props[(24, 1)] = row["value"]
            if key in {(16, 1), (16, 2), (16, 7), (16, 8)}:
                await self._async_read_control_properties({(16, 1), (16, 2), (16, 8)})
            if key in {(1, 8), (1, 10), (1, 81), (1, 82), (1, 75), (1, 83)}:
                await self._async_read_control_properties({(1, 8), (1, 10), (1, 81), (1, 82), (1, 75), (1, 83)})
            if key in {(1, 76), (1, 77)}:
                await self._async_read_control_properties({(1, 76), (1, 77)})
            plan = build_h15_write_plan(key, value, self.props, arm_bit=arm_bit)
            ok = await self.api.set_h15_properties(self.device_id, plan)
            if not ok:
                raise HomeAssistantError(
                    "Dreame did not confirm the H15 setting change; refresh the device and retry"
                )
            new_keys = self._apply_h15_values({f"{s}.{p}": v for (s, p), v in plan.items()})
            if new_keys and self.new_prop_callback:
                self.new_prop_callback(new_keys)
            self.async_set_updated_data(self._build_data())

    async def _async_read_control_properties(self, keys: set[tuple[int, int]]) -> None:
        """Read targeted state without inventing command results or counters."""
        rows = await self.api.get_properties(
            self.device_id, [{"siid": siid, "piid": piid} for siid, piid in sorted(keys)]
        )
        values = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("code") != 0:
                continue
            key = (row.get("siid"), row.get("piid"))
            if key in keys and row.get("value") is not None:
                values[f"{key[0]}.{key[1]}"] = row["value"]
        new_keys = self._apply_h15_values(values)
        if new_keys and self.new_prop_callback:
            self.new_prop_callback(new_keys)

    async def async_set_h15_schedule_day(self, day: int, enabled: bool) -> None:
        if not self._is_h15:
            raise ValueError("H15 schedules cannot write to this model")
        async with self._h15_write_lock:
            await self._async_read_control_properties({(1, 76), (1, 77)})
            plan = build_schedule_day_plan(day, enabled, self.props)
            if not await self.api.set_h15_properties(self.device_id, plan):
                raise HomeAssistantError("Dreame did not confirm the schedule change")
            self._apply_h15_values({f"{siid}.{piid}": value for (siid, piid), value in plan.items()})
            self.async_set_updated_data(self._build_data())

    async def async_send_h15_command(self, command: str) -> None:
        """Send an app command and then read device state, never fake a reset."""
        if not self._is_h15 or command not in H15_BUTTON_COMMANDS:
            raise ValueError("Unsupported command for this model")
        meta = H15_BUTTON_COMMANDS[command]
        keys = ({(10, 1)} if "move" in meta else {meta["remaining"], meta["maximum"]} if "reset" in meta
                else {(1, 28), (1, 8), (1, 10), (3, 1), (4, 1), (4, 2)})
        async with self._h15_write_lock:
            await self._async_read_control_properties(keys)
            if "move" in meta and (self.snapshot or self.device_info_raw).get("online") is not True:
                raise HomeAssistantError("Movement requires an online device")
            plan = build_h15_command_plan(command, self.props)
            if "move" in meta:
                try:
                    if not await self.api.set_h15_properties(self.device_id, plan):
                        raise HomeAssistantError("Dreame rejected the movement command")
                    await asyncio.sleep(0.3)
                finally:
                    # Finish the stop RPC even if the button task was cancelled.
                    stop_task = asyncio.create_task(self.api.set_h15_properties(self.device_id, {meta["move"]: 0}))
                    try:
                        stopped = await asyncio.shield(stop_task)
                    except asyncio.CancelledError:
                        await stop_task
                        raise
                    if not stopped:
                        raise HomeAssistantError("Dreame did not acknowledge stopping movement")
            elif not await self.api.set_h15_properties(self.device_id, plan):
                raise HomeAssistantError("Dreame rejected the command; refresh the device and retry")
            try:
                await self._async_read_control_properties(keys)
            except DreameAPIError as err:
                _LOGGER.debug("Command accepted, awaiting telemetry: %s", err)
            self.async_set_updated_data(self._build_data())

    def _handle_mqtt_update(self, state: dict[tuple[int, int], Any]) -> None:
        """Receive an MQTT update from the MQTT thread."""
        self.hass.loop.call_soon_threadsafe(self._apply_mqtt_state, dict(state))

    @callback
    def _apply_mqtt_state(self, state: dict[tuple[int, int], Any]) -> None:
        """Apply MQTT properties on the Home Assistant event loop."""
        new_keys = set(state) - set(self.props)
        self.props.update(state)
        self.h15_app_defaults.difference_update(state)

        if self._is_h15:
            for siid, piid in sorted(state):
                key = f"{siid}.{piid}"
                if key not in self._h15_poll_keys:
                    self._h15_poll_keys.append(key)
            self._h15_poll_keys.sort(key=self._property_sort_key)
            if any(self._h15_is_persisted(pair) for pair in state):
                self._schedule_h15_settings_save()

        if new_keys and self.new_prop_callback:
            self.new_prop_callback(new_keys)

        self.async_set_updated_data(self._build_data())
        if self._is_h15:
            self._schedule_h15_awake_refresh()

    @callback
    def _schedule_h15_awake_refresh(self) -> None:
        """Read app-only settings live while the unit is awake (read-only).

        The cloud cache never holds H15 settings or consumable max life; the app
        reads them with get_properties when a page opens. An MQTT push means the
        unit is online, so retry the same targeted read, throttled.
        """
        task = getattr(self, "_h15_awake_task", None)
        if task is not None and not task.done():
            return
        now = datetime.now(UTC)
        sleeping = self.props.get((1, 28)) == 7
        gap = timedelta(minutes=30 if sleeping else 10)
        last = getattr(self, "_h15_awake_at", None)
        if last is not None and now - last < gap:
            return
        self._h15_awake_at = now
        self._h15_awake_task = self.hass.async_create_background_task(
            self._async_h15_awake_refresh(), "dreame_h15_awake_refresh"
        )

    async def _async_h15_awake_refresh(self) -> None:
        await asyncio.sleep(2)
        try:
            live = await self._get_h15_targeted_live_props()
        except Exception as err:  # noqa: BLE001 - best effort, never fatal
            _LOGGER.debug("H15 awake refresh failed (non-fatal): %s", err)
            return
        if not live:
            return
        new_keys = self._apply_h15_values(live)
        if new_keys and self.new_prop_callback:
            self.new_prop_callback(new_keys)
        self.async_set_updated_data(self._build_data())
        _LOGGER.info("H15 awake refresh read %d live properties", len(live))

    @staticmethod
    def _property_sort_key(key: str) -> tuple[int, int]:
        try:
            siid, piid = key.split(".", 1)
            return int(siid), int(piid)
        except (TypeError, ValueError):
            return (9999, 9999)

    @staticmethod
    def _all_h15_scan_keys() -> list[str]:
        return [
            f"{siid}.{piid}"
            for siid in _H15_SCAN_SIIDS
            for piid in _H15_PIID_RANGE
        ]

    def _build_data(self) -> dict[str, Any]:
        """Flatten properties for Home Assistant entities."""
        data: dict[str, Any] = {
            f"{siid}.{piid}": value
            for (siid, piid), value in self.props.items()
        }

        # Never apply the inherited H14 status-group table to H15.
        if not self._is_h15:
            status = self.props.get((2, 1))
            if status is not None:
                try:
                    data["status_group"] = STATUS_GROUP.get(int(status), "unknown")
                except (TypeError, ValueError):
                    data["status_group"] = "unknown"

        return data

    async def _get_status_props_chunked(
        self,
        keys: list[str],
        *,
        chunk_size: int = _H15_DISCOVERY_CHUNK,
    ) -> dict[str, Any]:
        """Read cloud-cached status properties in bounded chunks."""
        result: dict[str, Any] = {}
        for start in range(0, len(keys), chunk_size):
            chunk = keys[start : start + chunk_size]
            try:
                values = await self.api.get_status_props(self.device_id, chunk)
            except DreameAuthError:
                raise
            except (DreameAPIError, ValueError) as err:
                _LOGGER.debug("status_props chunk failed (non-fatal): %s", err)
                continue
            if isinstance(values, dict):
                result.update(values)
        return result

    async def _get_h15_targeted_live_props(self) -> dict[str, Any]:
        """Try direct read-only get_properties for app-known H15 keys.

        The cloud cache is the primary source on this model. Direct RPC often
        returns null while the unit sleeps, but it can expose extra settings
        while the vacuum is awake. Only successful, non-null results are merged.
        """
        props = [{"siid": s, "piid": p} for s, p in H15_TARGETED_KEYS]
        result: dict[str, Any] = {}

        for start in range(0, len(props), _H15_DIRECT_CHUNK):
            chunk = props[start : start + _H15_DIRECT_CHUNK]
            try:
                rows = await self.api.get_properties(self.device_id, chunk)
            except DreameAuthError:
                raise
            except (DreameAPIError, ValueError) as err:
                _LOGGER.debug("H15 direct get_properties failed (non-fatal): %s", err)
                continue

            for item in rows or []:
                try:
                    if int(item.get("code", -1)) != 0:
                        continue
                    value = item.get("value")
                    if value is None:
                        continue
                    key = f"{int(item['siid'])}.{int(item['piid'])}"
                except (KeyError, TypeError, ValueError):
                    continue
                result[key] = value

        return result

    async def _read_full_h15_profile(self) -> dict[str, Any]:
        """Read the expanded H15 profile from cache plus targeted live RPC."""
        cached = await self._get_status_props_chunked(self._all_h15_scan_keys())
        usable = {key: value for key, value in cached.items() if value is not None}

        # Prefer a successful live value over an older cached value.
        live = await self._get_h15_targeted_live_props()
        usable.update(live)
        return usable

    @staticmethod
    def _h15_is_persisted(pair: tuple[int, int]) -> bool:
        return pair in H15_CONTROL_KEYS and pair not in _H15_PERSIST_EXCLUDE

    async def _async_restore_h15_settings(self) -> None:
        """Seed settings values cached from earlier sessions (live data wins)."""
        self._h15_settings_restored = True
        try:
            stored = await self._h15_settings_store.async_load() or {}
        except Exception as err:  # noqa: BLE001 - cache only, never fatal
            _LOGGER.debug("H15 settings cache could not be loaded: %s", err)
            return
        restored = 0
        for key, value in (stored.get("values") or {}).items():
            try:
                siid_text, piid_text = key.split(".", 1)
                pair = (int(siid_text), int(piid_text))
            except (AttributeError, TypeError, ValueError):
                continue
            if value is None or not self._h15_is_persisted(pair) or pair in self.props:
                continue
            self.props[pair] = value
            restored += 1
        if restored:
            _LOGGER.debug("Restored %s cached H15 setting value(s)", restored)
        for pair, value in _H15_APP_DEFAULTS.items():
            if pair not in self.props:
                self.props[pair] = value
                self.h15_app_defaults.add(pair)

    @callback
    def _schedule_h15_extras(self) -> None:
        """Hourly read-only app data: cleaning record and firmware check."""
        now = datetime.now(UTC)
        if self._h15_extras_at and now - self._h15_extras_at < _H15_EXTRAS_INTERVAL:
            return
        if self._h15_extras_task and not self._h15_extras_task.done():
            return
        self._h15_extras_at = now
        self._h15_extras_task = self.hass.async_create_background_task(
            self._async_refresh_h15_extras(), "dreame_h15_extras"
        )

    async def _async_refresh_h15_extras(self) -> None:
        tz_name = str(self.hass.config.time_zone or "UTC")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            tz = UTC
        now = datetime.now(tz)
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        begin = today - timedelta(days=29)
        begin_ms, end_ms = int(begin.timestamp() * 1000), int(now.timestamp() * 1000)
        stats: dict[str, Any] = {}
        try:
            levels = {}
            for name, piid in (("light", 64), ("moderate", 65), ("heavy", 66)):
                rows = await self.api.get_clean_statistics(
                    self.device_id, piid, 1, begin_ms, end_ms, tz_name
                )
                for row in rows:
                    day = str(row.get("day") or "").split(" ")[0]
                    if not day:
                        continue
                    try:
                        seconds = int(float(row.get("data") or 0))
                    except (TypeError, ValueError):
                        seconds = 0
                    levels.setdefault(day, {"light": 0, "moderate": 0, "heavy": 0})[name] = seconds
            days = dict(sorted(levels.items()))
            today_key = today.strftime("%Y-%m-%d")
            week_keys = {(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}
            def _sum(keys):
                out = {"light": 0, "moderate": 0, "heavy": 0}
                for k in keys:
                    for lvl, sec in days.get(k, {}).items():
                        out[lvl] += sec
                return out
            stats["today"] = _sum({today_key})
            stats["week"] = _sum(week_keys)
            stats["month"] = _sum(set(days))
            stats["daily"] = {k: sum(v.values()) for k, v in days.items()}
        except DreameAPIError as err:
            _LOGGER.debug("H15 cleaning statistics unavailable: %s", err)
        try:
            sessions = await self.api.get_clean_sessions(self.device_id, begin_ms, end_ms)
            parsed = []
            for item in sessions:
                try:
                    content = json.loads(item.get("valueStr") or "[]")
                except (TypeError, ValueError):
                    content = []
                seconds = sum(
                    int(c.get("value") or 0) for c in content
                    if isinstance(c, dict) and c.get("piid") in _H15_SESSION_DUR_PIIDS
                )
                try:
                    ts = datetime.fromtimestamp(int(item.get("eventTime")) / 1000, UTC)
                except (TypeError, ValueError):
                    continue
                parsed.append({"time": ts.isoformat(), "seconds": seconds})
            parsed.sort(key=lambda s: s["time"], reverse=True)
            stats["sessions"] = parsed[:20]
            week_start = (today - timedelta(days=6)).astimezone(UTC).isoformat()
            stats["sessions_week"] = sum(1 for s in parsed if s["time"] >= week_start)
            stats["sessions_month"] = len(parsed)
        except DreameAPIError as err:
            _LOGGER.debug("H15 cleaning sessions unavailable: %s", err)
        if stats:
            stats["updated"] = datetime.now(UTC).isoformat()
            self.h15_clean_stats = stats
        try:
            self.h15_firmware = await self.api.check_device_version(self.device_id)
        except DreameAPIError as err:
            _LOGGER.debug("H15 firmware check unavailable: %s", err)
        self.async_set_updated_data(self._build_data())

    @callback
    def _schedule_h15_settings_save(self) -> None:
        """Persist the latest known settings values (debounced)."""
        if not self._is_h15:
            return

        def _data() -> dict[str, Any]:
            return {
                "values": {
                    f"{siid}.{piid}": value
                    for (siid, piid), value in self.props.items()
                    if value is not None and self._h15_is_persisted((siid, piid))
                    and (siid, piid) not in self.h15_app_defaults
                }
            }

        self._h15_settings_store.async_delay_save(_data, _H15_SETTINGS_SAVE_DELAY)

    def _apply_h15_values(self, values: dict[str, Any]) -> set[tuple[int, int]]:
        """Apply returned H15 values and return newly discovered property keys."""
        new_keys: set[tuple[int, int]] = set()

        for key, value in values.items():
            if value is None:
                continue
            try:
                siid_text, piid_text = key.split(".", 1)
                pair = (int(siid_text), int(piid_text))
            except (TypeError, ValueError):
                continue

            if pair not in self.props:
                new_keys.add(pair)
            self.props[pair] = value
            self.h15_app_defaults.discard(pair)

            if key not in self._h15_poll_keys:
                self._h15_poll_keys.append(key)

        self._h15_poll_keys.sort(key=self._property_sort_key)
        self._schedule_h15_settings_save()
        return new_keys

    async def _async_discover_h15_properties(self) -> None:
        """Discover all readable properties in the expanded H15 profile."""
        if self._h15_discovery_done:
            return

        usable = await self._read_full_h15_profile()
        new_keys = self._apply_h15_values(usable)

        self._h15_mapping_snapshot = dict(usable)
        self._h15_last_changes = {}
        self._h15_last_scan = datetime.now(UTC)
        self._h15_discovery_done = True

        if new_keys and self.new_prop_callback:
            self.new_prop_callback(new_keys)

        _LOGGER.info(
            "H15 Pro Heat baseline discovered %d properties for model=%s "
            "(scan SIIDs 1-40 + 100, PIIDs 1-120)",
            len(self._h15_mapping_snapshot),
            self._model,
        )

    async def async_refresh_h15_mapping(self) -> dict[str, dict[str, Any]]:
        """Run a fresh expanded H15 scan and compare with the previous snapshot.

        This operation is read-only and never writes to the vacuum.
        """
        if not self._is_h15:
            return {}

        usable = await self._read_full_h15_profile()

        if not self._h15_mapping_snapshot:
            self._h15_mapping_snapshot = dict(usable)

        changes: dict[str, dict[str, Any]] = {}
        for key, new_value in usable.items():
            if key not in self._h15_mapping_snapshot:
                changes[key] = {"old": "<new>", "new": new_value}
                continue

            old_value = self._h15_mapping_snapshot[key]
            if old_value != new_value:
                changes[key] = {"old": old_value, "new": new_value}

        new_keys = self._apply_h15_values(usable)

        self._h15_mapping_snapshot.update(usable)
        self._h15_last_changes = changes
        self._h15_last_scan = datetime.now(UTC)

        if new_keys and self.new_prop_callback:
            self.new_prop_callback(new_keys)

        self.async_set_updated_data(self._build_data())

        if changes:
            lines = [
                f"{key}: {change['old']!r} -> {change['new']!r}"
                for key, change in sorted(
                    changes.items(),
                    key=lambda item: self._property_sort_key(item[0]),
                )
            ]
            _LOGGER.info(
                "H15 mapping scan detected %d change(s):\n%s",
                len(changes),
                "\n".join(lines),
            )
        else:
            _LOGGER.info("H15 mapping scan detected no property changes")

        return changes

    async def _async_background_h15_discovery(self) -> None:
        """Run the full H15 discovery scan without blocking setup or polls."""
        try:
            await self._async_discover_h15_properties()
        except Exception as err:  # noqa: BLE001 - retried on the next poll
            _LOGGER.warning("H15 property discovery failed, will retry: %s", err)
            return
        self.async_set_updated_data(self._build_data())

    async def _async_poll_h15_properties(self) -> None:
        """Refresh only properties already discovered for the H15."""
        if not self._h15_discovery_done:
            # The full H15 scan is ~50 sequential cloud calls (~1 min). Running it
            # inside the first refresh made config-entry setup exceed its time
            # budget and get cancelled, so run it in the background instead.
            task = getattr(self, "_h15_discovery_task", None)
            if task is None or task.done():
                self._h15_discovery_task = self.hass.async_create_background_task(
                    self._async_background_h15_discovery(), "dreame_h15_discovery"
                )
            return

        if not self._h15_poll_keys:
            return

        values = await self._get_status_props_chunked(self._h15_poll_keys)
        self._apply_h15_values(values)

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh cloud snapshot and cached properties."""
        if self._is_h15 and not self._h15_settings_restored:
            await self._async_restore_h15_settings()
        if self._is_h15:
            self._schedule_h15_extras()
        try:
            snapshot = await self.api.get_device_snapshot(self.device_id)
        except DreameAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Dreame credentials rejected: {err}"
            ) from err
        except DreameAPIError as err:
            if self.props:
                return self._build_data()
            raise UpdateFailed(f"Dreame API error: {err}") from err

        if snapshot:
            self.snapshot = snapshot
            if snapshot.get("battery") is not None and (3, 1) not in self.props:
                self.props[(3, 1)] = snapshot["battery"]
            if snapshot.get("status") is not None and (2, 1) not in self.props:
                self.props[(2, 1)] = snapshot["status"]
            if self.mqtt and self.api.access_token:
                self.mqtt.update_token(self.api.access_token)

        try:
            if self._is_h15:
                await self._async_poll_h15_properties()
            else:
                values = await self.api.get_status_props(self.device_id, _POLL_KEYS)
                for key, value in values.items():
                    siid_text, _, piid_text = key.partition(".")
                    self.props[(int(siid_text), int(piid_text))] = value
        except DreameAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Dreame credentials rejected: {err}"
            ) from err
        except (DreameAPIError, ValueError) as err:
            _LOGGER.debug("status_props poll failed (non-fatal): %s", err)

        return self._build_data()
