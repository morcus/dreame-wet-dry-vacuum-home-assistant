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
from .const import (
    ALERT_BINARY_SENSORS,
    H15_ALERT_BINARY_SENSORS,
    H15_PRIMARY_ALERT_KEYS,
    KNOWN_BINARY_PROPS,
)
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

    if coordinator.is_h15_pro_heat:
        # Use the H15 app warning table; keep legacy H14 masks separate.
        async_add_entities([DreameWetDryOnlineSensor(coordinator), DreameWetDryChargingSensor(coordinator),
                            *(DreameWetDryMappedAlert(coordinator, meta) for meta in H15_ALERT_BINARY_SENSORS if meta["key"] in H15_PRIMARY_ALERT_KEYS)])
        return

    entities = [
        DreameWetDryOnlineSensor(coordinator),
        DreameWetDryChargingSensor(coordinator),
    ]
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
        if self.coordinator.is_h15_pro_heat:
            state = self.coordinator.data.get("1.28")
            try:
                return int(state) in {4, 15} if state is not None else None
            except (TypeError, ValueError):
                return None
        return self.coordinator.data.get("status_group") == "charging"


class DreameWetDryMappedAlert(CoordinatorEntity, BinarySensorEntity):
    """An exact model-specific field match, including multi-bit fault codes."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, meta: dict) -> None:
        super().__init__(coordinator)
        self._meta = meta
        self._attr_unique_id = f"{coordinator.device_id}_{meta['key']}"
        self._attr_name = meta["name"]
        self._attr_device_info = build_device_info(coordinator)

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.data.get(self._meta["data_key"])
        try:
            value = int(raw)
            if isinstance(raw, bool) or value < 0 or value != float(raw):
                return None
        except (TypeError, ValueError, OverflowError):
            return None
        return ((value >> self._meta["shift"]) & self._meta["field_mask"]) in self._meta["field_values"]

    @property
    def extra_state_attributes(self) -> dict:
        return {"property": self._meta["data_key"], "raw_value": self.coordinator.data.get(self._meta["data_key"]),
                "mapping_status": self._meta.get("confidence", "plugin"), "mapping_source": "Dreamehome H15 warning table"}
