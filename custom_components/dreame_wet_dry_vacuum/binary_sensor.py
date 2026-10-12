"""Binary sensor platform for Dreame wet & dry vacuum."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DreameWetDryConfigEntry
from .const import ALERT_BINARY_SENSORS, H15_MIX_MODEL, KNOWN_BINARY_PROPS
from .coordinator import DreameWetDryCoordinator
from .entity import build_device_info

_BINARY_DEVICE_CLASSES = {
    "running": BinarySensorDeviceClass.RUNNING,
    "connectivity": BinarySensorDeviceClass.CONNECTIVITY,
    "problem": BinarySensorDeviceClass.PROBLEM,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameWetDryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DreameWetDryCoordinator = entry.runtime_data
    entities = [
        DreameWetDryOnlineSensor(coordinator),
        DreameWetDryChargingSensor(coordinator),
    ]
    if coordinator.device_info_raw.get("model") == H15_MIX_MODEL:
        # 4.2 bit 4096 was observed when this H15 Mix rejected self-cleaning
        # with a full dirty-water tank. Other H14 alert bits remain unverified.
        tank_full = next(
            meta for meta in ALERT_BINARY_SENSORS if meta["key"] == "dirty_tank_full"
        )
        entities.append(DreameWetDryAlertBinary(coordinator, tank_full))
        async_add_entities(entities)
        return
    for key, meta in KNOWN_BINARY_PROPS.items():
        entities.append(DreameWetDryPropBinary(coordinator, key, meta))
    for meta in ALERT_BINARY_SENSORS:
        entities.append(DreameWetDryAlertBinary(coordinator, meta))
    async_add_entities(entities)


class DreameWetDryPropBinary(CoordinatorEntity[DreameWetDryCoordinator], BinarySensorEntity):
    """Binary sensor backed by a (siid, piid) property (on when value != 0)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameWetDryCoordinator, key: tuple[int, int], meta: dict) -> None:
        super().__init__(coordinator)
        self._data_key = f"{key[0]}.{key[1]}"
        self._bit_mask = meta.get("bit_mask")
        self._attr_unique_id = f"{coordinator.device_id}_{meta['key']}"
        self._attr_translation_key = meta["key"]
        self._attr_icon = meta.get("icon")
        if dc := _BINARY_DEVICE_CLASSES.get(meta.get("device_class")):
            self._attr_device_class = dc
        if meta.get("diagnostic"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_device_info = build_device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        val = self.coordinator.data.get(self._data_key)
        if val is None:
            return None
        try:
            ival = int(val)
        except (ValueError, TypeError):
            return None
        if self._bit_mask is not None:
            return (ival & self._bit_mask) != 0
        return ival != 0


class DreameWetDryAlertBinary(CoordinatorEntity[DreameWetDryCoordinator], BinarySensorEntity):
    """Specific alert backed by a single bit (or bit field) of a warn/error prop.

    On when (value & bit_mask) != 0. Several of these can share one property
    (e.g. multiple bits of 4.2). The raw warn/error value comes from MQTT push
    and the periodic iotstatus refresh, so the alert survives a HA restart.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameWetDryCoordinator, meta: dict) -> None:
        super().__init__(coordinator)
        self._data_key = meta["data_key"]
        self._bit_mask = meta["bit_mask"]
        self._attr_unique_id = f"{coordinator.device_id}_{meta['key']}"
        self._attr_translation_key = meta["key"]
        self._attr_icon = meta.get("icon")
        if dc := _BINARY_DEVICE_CLASSES.get(meta.get("device_class")):
            self._attr_device_class = dc
        self._attr_device_info = build_device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        val = self.coordinator.data.get(self._data_key)
        if val is None:
            return None
        try:
            return (int(val) & self._bit_mask) != 0
        except (ValueError, TypeError):
            return None


class _BaseBinary(CoordinatorEntity[DreameWetDryCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameWetDryCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.device_id}_{key}"
        self._attr_device_info = build_device_info(coordinator)


class DreameWetDryOnlineSensor(_BaseBinary):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: DreameWetDryCoordinator) -> None:
        super().__init__(coordinator, "online")

    @property
    def is_on(self) -> bool:
        # Cloud-reported device state, refreshed by the 5-min snapshot poll
        snap = self.coordinator.snapshot or self.coordinator.device_info_raw
        online = snap.get("online")
        if online is not None:
            return bool(online)
        # Fallback: at least tell whether the real-time feed is up
        mqtt = self.coordinator.mqtt
        return bool(mqtt and mqtt.connected)


class DreameWetDryChargingSensor(_BaseBinary):
    _attr_translation_key = "charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator: DreameWetDryCoordinator) -> None:
        super().__init__(coordinator, "charging")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.get("status_group") == "charging"
