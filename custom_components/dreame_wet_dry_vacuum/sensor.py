"""Sensor platform for Dreame wet & dry vacuum (dynamic, MQTT-driven)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DreameWetDryConfigEntry
from .const import (
    CONSUMABLE_SENSORS,
    DEVICE_STATUS,
    ERROR_DECODE,
    KNOWN_MQTT_PROPS,
    WARN_DECODE,
    decode_field_alerts,
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
    coordinator: DreameWetDryCoordinator = entry.runtime_data
    added: set[tuple[int, int]] = set()

    @callback
    def _add_new(keys: set[tuple[int, int]]) -> None:
        entities = []
        for key in keys:
            # Only create sensors for *recognised* properties. Props handled by
            # another platform (switch/number/select/button) or not yet identified
            # are intentionally not turned into generic "Propriété X.Y" sensors.
            if key in added or key not in KNOWN_MQTT_PROPS:
                continue
            added.add(key)
            entities.append(DreameWetDrySensor(coordinator, key))
        if entities:
            async_add_entities(entities)

    coordinator.new_prop_callback = _add_new
    _add_new(set(KNOWN_MQTT_PROPS))

    # Consumable life sensors: state = hours remaining (left / 60, no constant),
    # with percent + minutes as attributes.
    async_add_entities(
        DreameWetDryConsumableSensor(coordinator, meta) for meta in CONSUMABLE_SENSORS
    )


class DreameWetDrySensor(CoordinatorEntity[DreameWetDryCoordinator], SensorEntity):
    """One sensor per (siid, piid) property."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameWetDryCoordinator, key: tuple[int, int]) -> None:
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
                return datetime.fromtimestamp(int(raw), tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                return None
        if self._is_enum:
            try:
                return DEVICE_STATUS.get(int(raw), str(raw))
            except (ValueError, TypeError):
                return str(raw)
        # Lists we don't reduce: present as string to stay valid
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
                bits = [b for b in range(32) if ival & (1 << b)]
                attrs["active_bits"] = [1 << b for b in bits]
                if self._decode and self._decode in _DECODE_TABLES:
                    attrs["alerts"] = decode_field_alerts(ival, _DECODE_TABLES[self._decode])
            except (ValueError, TypeError):
                pass
        return attrs


class DreameWetDryConsumableSensor(CoordinatorEntity[DreameWetDryCoordinator], SensorEntity):
    """Consumable remaining life. State = hours remaining (minutes / 60, no
    constant). Percentage is exposed as an attribute, using the device's `max`
    property when available, otherwise the documented full-life fallback."""

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "h"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DreameWetDryCoordinator, meta: dict) -> None:
        super().__init__(coordinator)
        self._left_key = meta["left"]
        self._max_key = meta["max"]
        self._full_life_min = meta["full_life_min"]
        self._attr_unique_id = f"{coordinator.device_id}_consumable_{meta['key']}"
        self._attr_translation_key = f"consumable_{meta['key']}"
        self._attr_icon = meta.get("icon")
        self._attr_device_info = build_device_info(coordinator)

    def _left_minutes(self) -> int | None:
        try:
            return int(self.coordinator.data.get(self._left_key))
        except (ValueError, TypeError):
            return None

    @property
    def native_value(self) -> float | None:
        left = self._left_minutes()
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
        if full > 0:
            attrs["percent_remaining"] = max(0, min(100, round(left / full * 100)))
        return attrs
