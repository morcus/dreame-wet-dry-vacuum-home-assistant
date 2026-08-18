"""Data coordinator for Dreame wet & dry vacuum (MQTT push + HTTP seed)."""

from __future__ import annotations

import logging

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DreameAPI, DreameAPIError, DreameAuthError
from .const import (
    CONSUMABLE_MAX_KEYS,
    CONF_REGION,
    DOMAIN,
    KNOWN_BINARY_PROPS,
    KNOWN_MQTT_PROPS,
    KNOWN_NUMBER_PROPS,
    KNOWN_SELECT_PROPS,
    KNOWN_SWITCH_PROPS,
    MQTT_ONLY_KEYS,
    STATUS_GROUP,
)
from .dreame_mqtt import DreameMqttClient

# All "siid.piid" keys worth polling from the cloud status endpoint.
# MQTT_ONLY_KEYS (fast-changing progress) are excluded: they're driven by the
# real-time MQTT push, and a coarse 5-min poll would make them jump around.
_POLL_KEYS: list[str] = sorted(
    {f"{s}.{p}" for s, p in (
        set(KNOWN_MQTT_PROPS)
        | set(KNOWN_BINARY_PROPS)
        | set(KNOWN_SWITCH_PROPS)
        | set(KNOWN_NUMBER_PROPS)
        | set(KNOWN_SELECT_PROPS)
    ) - MQTT_ONLY_KEYS}
    | set(CONSUMABLE_MAX_KEYS)
)

_LOGGER = logging.getLogger(__name__)

# Safety-net HTTP refresh interval (MQTT is the primary, real-time source)
HTTP_REFRESH = timedelta(minutes=5)


class DreameWetDryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds live device state. Primary feed is MQTT push; HTTP snapshot seeds
    battery/status and acts as a periodic safety net."""

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
            # No self-rescheduling interval: async_set_updated_data (fired on
            # every MQTT push) would postpone it indefinitely while the device
            # is active. The safety-net poll runs on an independent timer
            # instead (see start_polling).
            update_interval=None,
        )
        self.api = api
        self.device_id = device_id
        self.device_info_raw = device_info
        self._region = entry.data.get(CONF_REGION, "eu")
        # Latest cloud snapshot (online, battery, status…), refreshed each poll
        self.snapshot: dict[str, Any] = {}
        # Live property store keyed by (siid, piid)
        self.props: dict[tuple[int, int], Any] = {}
        # Callback set by the sensor platform to add entities for new props
        self.new_prop_callback: Callable[[set[tuple[int, int]]], None] | None = None
        self.mqtt: DreameMqttClient | None = None
        self._unsub_poll: Callable[[], None] | None = None

    @callback
    def start_polling(self) -> None:
        """Start the fixed-interval safety-net poll."""
        self._unsub_poll = async_track_time_interval(
            self.hass, self._async_scheduled_poll, HTTP_REFRESH
        )

    @callback
    def stop_polling(self) -> None:
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

        Does blocking I/O (SSL context) — call from an executor.
        """
        snap = self.device_info_raw
        bind = snap.get("bindDomain") or snap.get("bind_domain")
        if not bind:
            _LOGGER.warning("No bindDomain; MQTT disabled, HTTP polling only")
            return

        self.mqtt = DreameMqttClient(
            uid=self.api.uid,
            access_token=self.api.access_token,
            device_id=self.device_id,
            model=snap.get("model", ""),
            bind_domain=bind,
            on_update=self._handle_mqtt_update,
            region=self._region,
        )
        self.mqtt.start()

    async def async_set_prop(self, siid: int, piid: int, value: Any) -> bool:
        """Write a property to the device, then optimistically update state."""
        ok = await self.api.set_property(self.device_id, siid, piid, value)
        if ok:
            self.props[(siid, piid)] = value
            self.async_set_updated_data(self._build_data())
        else:
            _LOGGER.warning("set_property %s.%s=%s rejected by device", siid, piid, value)
        return ok

    def _handle_mqtt_update(self, state: dict[tuple[int, int], Any]) -> None:
        """Called from the MQTT thread when properties change."""
        # Marshal everything (including the props mutation) to the HA loop
        self.hass.loop.call_soon_threadsafe(self._apply_mqtt_state, dict(state))

    @callback
    def _apply_mqtt_state(self, state: dict[tuple[int, int], Any]) -> None:
        new_keys = set(state) - set(self.props)
        self.props.update(state)
        if new_keys and self.new_prop_callback:
            self.new_prop_callback(new_keys)
        self.async_set_updated_data(self._build_data())

    def _build_data(self) -> dict[str, Any]:
        """Flatten props + snapshot into a name->value dict for entities."""
        data: dict[str, Any] = {f"{s}.{p}": v for (s, p), v in self.props.items()}
        # status_group from the main status property (2.1) if present
        status = self.props.get((2, 1))
        if status is not None:
            data["status_group"] = STATUS_GROUP.get(int(status), "unknown")
        return data

    async def _async_update_data(self) -> dict[str, Any]:
        """HTTP safety-net refresh: seed battery + status from the snapshot."""
        try:
            snapshot = await self.api.get_device_snapshot(self.device_id)
        except DreameAuthError as err:
            # Credentials rejected: surface it so HA starts a reauth flow
            raise ConfigEntryAuthFailed(f"Dreame credentials rejected: {err}") from err
        except DreameAPIError as err:
            # If MQTT is alive we can tolerate HTTP errors
            if self.props:
                return self._build_data()
            raise UpdateFailed(f"Dreame API error: {err}") from err

        if snapshot:
            self.snapshot = snapshot
            if snapshot.get("battery") is not None and (3, 1) not in self.props:
                self.props[(3, 1)] = snapshot["battery"]
            if snapshot.get("status") is not None and (2, 1) not in self.props:
                self.props[(2, 1)] = snapshot["status"]

        # Refresh MQTT credentials if the token rotated (it expires after 2 h)
        if self.mqtt and self.api.access_token:
            self.mqtt.update_token(self.api.access_token)

        # Read cloud-cached property values (warn/error, consumables, settings…).
        # This is what makes alerts like "dirty tank full" reliable even when MQTT
        # missed the push (e.g. HA started after the event fired).
        try:
            values = await self.api.get_status_props(self.device_id, _POLL_KEYS)
            for key, value in values.items():
                s, _, p = key.partition(".")
                self.props[(int(s), int(p))] = value
        except (DreameAPIError, ValueError) as err:
            _LOGGER.debug("status_props poll failed (non-fatal): %s", err)

        return self._build_data()
