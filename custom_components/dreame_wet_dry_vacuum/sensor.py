"""Sensor platform for Dreame wet & dry vacuum."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DreameWetDryConfigEntry
from .const import (
    CONSUMABLE_SENSORS,
    DEVICE_STATUS,
    ERROR_DECODE,
    H15_ERROR_FIELDS,
    H15_GENERAL_SENSOR_KEYS,
    H15_PROPERTY_META,
    H15_SCHEDULE_DAYS,
    H15_WARN_FIELDS,
    KNOWN_MQTT_PROPS,
    WARN_DECODE,
    decode_field_alerts,
    decode_h15_alerts,
    decode_schedule,
    h15_sensor_is_optional,
)
from .coordinator import DreameWetDryCoordinator
from .entity import build_device_info

_LOGGER = logging.getLogger(__name__)

_DECODE_TABLES = {"warn": WARN_DECODE, "error": ERROR_DECODE}

_DEVICE_CLASSES = {
    "battery": SensorDeviceClass.BATTERY,
    "duration": SensorDeviceClass.DURATION,
    "timestamp": SensorDeviceClass.TIMESTAMP,
}
_STATE_CLASSES = {
    "measurement": SensorStateClass.MEASUREMENT,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameWetDryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: DreameWetDryCoordinator = entry.runtime_data

    if coordinator.is_h15_pro_heat:
        _setup_h15_sensors(coordinator, async_add_entities)
        return

    added: set[tuple[int, int]] = set()

    @callback
    def _add_new(keys: set[tuple[int, int]]) -> None:
        entities = []
        for key in keys:
            if key in added or key not in KNOWN_MQTT_PROPS:
                continue
            added.add(key)
            entities.append(DreameWetDrySensor(coordinator, key))
        if entities:
            async_add_entities(entities)

    coordinator.new_prop_callback = _add_new
    _add_new(set(KNOWN_MQTT_PROPS))

    async_add_entities(
        DreameWetDryConsumableSensor(coordinator, meta)
        for meta in CONSUMABLE_SENSORS
    )


def _decode_h15_mechanical_arm_2449(raw: Any) -> list[str]:
    """Decode w2449e lifting-arm inverted mode bits from Dreame app logic."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return []

    modes = (
        (0, "Smart"),
        (3, "Hot Water"),
        (2, "Suction"),
        (4, "Custom"),
    )
    return [name for bit, name in modes if ((value >> bit) & 1) == 0]


def _setup_h15_sensors(
    coordinator: DreameWetDryCoordinator,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Expose useful H15 telemetry; keep research properties in exports."""
    added: set[tuple[int, int]] = set()

    @callback
    def _add_new(keys: set[tuple[int, int]]) -> None:
        entities: list[SensorEntity] = []
        for key in sorted(keys):
            if key in added or h15_sensor_is_optional(key) or coordinator.props.get(key) in (None, -1, "-1"):
                continue
            added.add(key)
            entities.append(DreameH15PropertySensor(coordinator, key))
        if entities:
            async_add_entities(entities)

    coordinator.new_prop_callback = _add_new
    _add_new(set(coordinator.props))
    async_add_entities([DreameH15CleanTimeSensor(coordinator, p) for p in ("today", "week", "month")])
    async_add_entities([DreameH15CleanSessionsSensor(coordinator), DreameH15LastSessionSensor(coordinator)])
    async_add_entities([DreameH15MappingChangesSensor(coordinator),
                        *(DreameWetDryConsumableSensor(coordinator, meta, percentage=percentage)
                          for meta in CONSUMABLE_SENSORS
                          if meta["key"] != "back_brush" or coordinator.props.get((7, 7), -1) >= 0
                          for percentage in (False, True))])

    _LOGGER.info(
        "Created %d H15 Pro Heat property sensors for model=%s",
        len(added),
        coordinator.model,
    )


_CLEAN_PERIOD_NAMES = {"today": "Cleaning time today", "week": "Cleaning time (7 days)", "month": "Cleaning time (30 days)"}


class DreameH15CleanTimeSensor(CoordinatorEntity[DreameWetDryCoordinator], SensorEntity):
    """Floor-cleaning time from the app Cleaning Record (dirt-level split)."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = "min"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: DreameWetDryCoordinator, period: str) -> None:
        super().__init__(coordinator)
        self._period = period
        self._attr_name = _CLEAN_PERIOD_NAMES[period]
        self._attr_unique_id = f"{coordinator.device_id}_h15_clean_time_{period}"
        self._attr_device_info = build_device_info(coordinator)

    def _levels(self) -> dict[str, int] | None:
        return (self.coordinator.h15_clean_stats or {}).get(self._period)

    @property
    def available(self) -> bool:
        return super().available and self._levels() is not None

    @property
    def native_value(self) -> float | None:
        levels = self._levels()
        return round(sum(levels.values()) / 60, 1) if levels is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        levels = self._levels() or {}
        total = sum(levels.values())
        attrs: dict[str, Any] = {f"{k}_dirt_minutes": round(v / 60, 1) for k, v in levels.items()}
        attrs.update({f"{k}_dirt_percent": (round(v * 100 / total) if total else 0) for k, v in levels.items()})
        if self._period == "month":
            attrs["daily_minutes"] = {d: round(s / 60, 1) for d, s in (self.coordinator.h15_clean_stats or {}).get("daily", {}).items()}
        attrs["source"] = "Dreamehome Cleaning Record"
        return attrs


class DreameH15CleanSessionsSensor(CoordinatorEntity[DreameWetDryCoordinator], SensorEntity):
    """Number of floor-cleaning sessions in the last 7 days."""

    _attr_has_entity_name = True
    _attr_name = "Cleaning sessions (7 days)"
    _attr_icon = "mdi:counter"
    _attr_native_unit_of_measurement = "sessions"

    def __init__(self, coordinator: DreameWetDryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_h15_clean_sessions_week"
        self._attr_device_info = build_device_info(coordinator)

    @property
    def available(self) -> bool:
        return super().available and "sessions_week" in (self.coordinator.h15_clean_stats or {})

    @property
    def native_value(self) -> int | None:
        return (self.coordinator.h15_clean_stats or {}).get("sessions_week")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        stats = self.coordinator.h15_clean_stats or {}
        return {"sessions_30_days": stats.get("sessions_month"),
                "recent_sessions": [{"time": s["time"], "minutes": round(s["seconds"] / 60, 1)}
                                    for s in stats.get("sessions", [])[:10]]}


class DreameH15LastSessionSensor(CoordinatorEntity[DreameWetDryCoordinator], SensorEntity):
    """Start time of the most recent floor-cleaning session."""

    _attr_has_entity_name = True
    _attr_name = "Last cleaning"
    _attr_icon = "mdi:history"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: DreameWetDryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_h15_last_session"
        self._attr_device_info = build_device_info(coordinator)

    def _last(self) -> dict[str, Any] | None:
        sessions = (self.coordinator.h15_clean_stats or {}).get("sessions") or []
        return sessions[0] if sessions else None

    @property
    def available(self) -> bool:
        return super().available and self._last() is not None

    @property
    def native_value(self) -> datetime | None:
        last = self._last()
        return datetime.fromisoformat(last["time"]) if last else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = self._last() or {}
        return {"duration_minutes": round(last.get("seconds", 0) / 60, 1)} if last else {}


class DreameH15MappingChangesSensor(
    CoordinatorEntity[DreameWetDryCoordinator], SensorEntity
):
    """Show the result of the last explicit H15 mapping snapshot comparison."""

    _attr_has_entity_name = True
    _attr_entity_registry_enabled_default = False
    _attr_name = "Mapping changes"
    _attr_icon = "mdi:compare"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DreameWetDryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_h15_mapping_changes"
        self._attr_device_info = build_device_info(coordinator)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.h15_last_changes)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        changes = self.coordinator.h15_last_changes
        attrs: dict[str, Any] = {
            "model": self.coordinator.model,
            "changed_properties": list(changes),
            "changes": changes,
        }
        if self.coordinator.h15_last_scan is not None:
            attrs["last_scan"] = self.coordinator.h15_last_scan.isoformat()
        return attrs


class DreameH15PropertySensor(
    CoordinatorEntity[DreameWetDryCoordinator], SensorEntity
):
    """Read-only H15 property sensor.

    Confirmed/candidate names come from the model profile. Anything not mapped
    remains a Raw SIID.PIID sensor instead of inheriting H14 semantics.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DreameWetDryCoordinator,
        key: tuple[int, int],
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._data_key = f"{key[0]}.{key[1]}"
        self._meta = H15_PROPERTY_META.get(key, {})

        # H15-specific IDs prevent old H14 sensor semantics from being reused.
        self._attr_unique_id = (
            f"{coordinator.device_id}_h15_property_{key[0]}_{key[1]}"
        )
        self._attr_name = self._meta.get("name", f"Raw {self._data_key}")
        self._attr_icon = self._meta.get("icon", "mdi:code-tags")
        self._attr_device_info = build_device_info(coordinator)

        self._attr_entity_category = (
            None if key in H15_GENERAL_SENSOR_KEYS else EntityCategory.DIAGNOSTIC
        )
        if h15_sensor_is_optional(key) or coordinator.props.get(key) == -1:
            self._attr_entity_registry_enabled_default = False

        device_class = self._meta.get("device_class")
        if device_class == "battery":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif device_class == "duration":
            self._attr_device_class = SensorDeviceClass.DURATION
        elif device_class == "timestamp":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP

        state_class = self._meta.get("state_class")
        if state_class == "measurement":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        elif state_class == "total_increasing":
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

        if unit := self._meta.get("unit"):
            self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        raw = self.coordinator.data.get(self._data_key)
        if raw is None:
            return None

        if self._meta.get("timestamp"):
            try:
                return datetime.fromtimestamp(float(raw), UTC) if float(raw) > 0 else None
            except (TypeError, ValueError, OverflowError, OSError):
                return None
        if self._meta.get("remaining_time") and raw in (-1, "-1"):
            return None

        # Lists/dicts are valid raw Dreame values, but HA sensor state itself
        # must be scalar. Preserve the exact value in raw_value attributes.
        if isinstance(raw, (list, dict, tuple)):
            return json.dumps(raw, ensure_ascii=False, separators=(",", ":"))

        if self._meta.get("decoder") in {"warnings", "errors"}:
            fields = H15_WARN_FIELDS if self._key == (4, 1) else H15_ERROR_FIELDS
            alerts = decode_h15_alerts(raw, fields)
            return len(alerts) if alerts is not None else None
        if self._meta.get("decoder") == "schedule":
            try:
                schedule = decode_schedule(int(raw))
                return "Off" if not schedule["enabled"] else "Once" if schedule["once"] else ", ".join(H15_SCHEDULE_DAYS[day] for day in schedule["days"])
            except (ValueError, TypeError):
                return f"Unknown ({raw})"

        value_map = self._meta.get("value_map")
        if isinstance(value_map, dict):
            try:
                numeric = int(raw)
            except (TypeError, ValueError):
                return str(raw)
            return value_map.get(numeric, f"Unknown ({raw})")

        if self._meta.get("decoder") == "mechanical_arm_2449":
            modes = _decode_h15_mechanical_arm_2449(raw)
            if len(modes) == 4:
                return "All modes"
            return ", ".join(modes) if modes else "None"

        return raw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        raw = self.coordinator.data.get(self._data_key)
        attrs: dict[str, Any] = {
            "model": self.coordinator.model,
            "siid": self._key[0],
            "piid": self._key[1],
            "property": self._data_key,
            "mapping_status": self._meta.get("confidence", "unmapped"),
            "raw_value": raw,
        }

        if self._meta.get("decoder") in {"warnings", "errors"}:
            fields = H15_WARN_FIELDS if self._key == (4, 1) else H15_ERROR_FIELDS
            attrs["active_alerts"] = decode_h15_alerts(raw, fields)
            attrs["mapping_source"] = "Dreamehome warnVersion=2 (w2449e)"

        if note := self._meta.get("note"):
            attrs["mapping_note"] = note

        value_map = self._meta.get("value_map")
        if isinstance(value_map, dict):
            attrs["known_values"] = {
                str(key): value for key, value in value_map.items()
            }

        if self._meta.get("decoder") == "mechanical_arm_2449" and raw is not None:
            attrs["selected_modes"] = _decode_h15_mechanical_arm_2449(raw)
            attrs["bit_semantics"] = {
                "0": "Smart selected when bit=0",
                "3": "Hot Water selected when bit=0",
                "2": "Suction selected when bit=0",
                "4": "Custom selected when bit=0",
            }

        if self._meta.get("bitfield") and raw is not None:
            try:
                value = int(raw)
                attrs["active_bits"] = [
                    1 << bit for bit in range(32) if value & (1 << bit)
                ]
            except (TypeError, ValueError):
                pass

        if self._meta.get("remaining_time") and raw is not None:
            try:
                minutes = int(raw)
                if minutes >= 0:
                    attrs["hours_remaining"] = round(minutes / 60, 1)
            except (TypeError, ValueError):
                pass

        return attrs


class DreameWetDrySensor(
    CoordinatorEntity[DreameWetDryCoordinator], SensorEntity
):
    """One legacy/H14 sensor per (siid, piid) property."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DreameWetDryCoordinator,
        key: tuple[int, int],
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._data_key = f"{key[0]}.{key[1]}"
        meta = KNOWN_MQTT_PROPS.get(key, {})
        self._meta = meta
        self._is_enum = meta.get("enum", False)
        self._list_scalar = meta.get("list_scalar", False)
        self._is_timestamp = meta.get("timestamp", False)
        self._is_bitmask = meta.get("bitmask", False)
        self._decode = meta.get("decode")

        self._attr_unique_id = f"{coordinator.device_id}_{self._data_key}"
        self._attr_translation_key = meta["key"]
        self._attr_icon = meta.get("icon")

        if dc := _DEVICE_CLASSES.get(meta.get("device_class")):
            self._attr_device_class = dc
        if sc := _STATE_CLASSES.get(meta.get("state_class")):
            self._attr_state_class = sc
        if meta.get("unit"):
            self._attr_native_unit_of_measurement = meta["unit"]
        if meta.get("device_class") == "battery":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if meta.get("diagnostic") or not meta:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

        self._attr_device_info = build_device_info(coordinator)

    def _scalar(self, raw: Any) -> Any:
        if self._list_scalar and isinstance(raw, list):
            return raw[0] if raw else None
        return raw

    @property
    def native_value(self) -> Any:
        raw = self.coordinator.data.get(self._data_key)
        if raw is None:
            return None
        raw = self._scalar(raw)
        if raw is None:
            return None
        if self._is_timestamp:
            try:
                return datetime.fromtimestamp(int(raw), tz=UTC)
            except (ValueError, TypeError, OSError):
                return None
        if self._is_enum:
            try:
                return DEVICE_STATUS.get(int(raw), str(raw))
            except (ValueError, TypeError):
                return str(raw)
        if isinstance(raw, list):
            return ", ".join(str(x) for x in raw)
        return raw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {"siid": self._key[0], "piid": self._key[1]}
        raw = self.coordinator.data.get(self._data_key)
        if self._is_enum or self._is_timestamp or self._list_scalar:
            attrs["raw_value"] = raw
        if self._is_bitmask and raw is not None:
            try:
                ival = int(raw)
                bits = [bit for bit in range(32) if ival & (1 << bit)]
                attrs["active_bits"] = [1 << bit for bit in bits]
                if self._decode and self._decode in _DECODE_TABLES:
                    attrs["alerts"] = decode_field_alerts(
                        ival, _DECODE_TABLES[self._decode]
                    )
            except (ValueError, TypeError):
                pass
        return attrs


class DreameWetDryConsumableSensor(
    CoordinatorEntity[DreameWetDryCoordinator], SensorEntity
):
    """Remaining life: H15 percentage, legacy/H14 hours."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DreameWetDryCoordinator, meta: dict, *, percentage: bool = False) -> None:
        super().__init__(coordinator)
        self._percentage = percentage and coordinator.is_h15_pro_heat
        self._left_key = meta["left"]
        self._max_key = meta["max"]
        # H15 does not report maximum life (6.6 / 19.2) in the cloud cache.
        # Dreame rates the roller brush and filter at 60 h (3600 min); use that
        # documented default so percentages work. A device-reported maximum,
        # when available, still takes precedence below.
        self._full_life_min = meta["full_life_min"]
        if coordinator.is_h15_pro_heat:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if self._percentage:
            self._attr_native_unit_of_measurement = "%"
        self._attr_unique_id = (
            f"{coordinator.device_id}_consumable_{meta['key']}"
            + ("_percent" if self._percentage else "")
        )
        self._attr_translation_key = f"consumable_{meta['key']}" + ("_percent" if self._percentage else "")
        self._attr_icon = meta.get("icon")
        self._attr_device_info = build_device_info(coordinator)

    def _left_minutes(self) -> int | None:
        try:
            value = int(self.coordinator.data.get(self._left_key))
            return None if self.coordinator.is_h15_pro_heat and value < 0 else value
        except (ValueError, TypeError):
            return None

    @property
    def native_value(self) -> float | None:
        left = self._left_minutes()
        if self._percentage:
            return self.extra_state_attributes.get("percent_remaining")
        return None if left is None else round(left / 60, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        left = self._left_minutes()
        if left is None:
            return {}

        raw_max = self.coordinator.data.get(self._max_key)
        try:
            full = int(raw_max)
        except (ValueError, TypeError):
            full = -1

        from_device = full > 0
        if not from_device:
            full = self._full_life_min

        attrs: dict[str, Any] = {
            "minutes_remaining": left,
            "full_life_hours": round(full / 60, 1),
            "full_life_source": "device" if from_device else "default (60 h)",
        }
        if full <= 0 and self.coordinator.is_h15_pro_heat:
            attrs.pop("full_life_hours")
        if full > 0:
            # H15: same float expression as Dreamehome MaterialPage
            # (parseInt(left / max * 100)), so the value always equals the app.
            attrs["percent_remaining"] = max(
                0, min(100, int(left / full * 100) if self.coordinator.is_h15_pro_heat
                       else round(left / full * 100))
            )
            if self.coordinator.is_h15_pro_heat:
                attrs["hours_remaining_app"] = int(left / full * full / 60)
                attrs["replace_soon"] = attrs["percent_remaining"] < 20
        return attrs
