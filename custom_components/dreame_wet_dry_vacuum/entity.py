"""Shared base entity for Dreame wet & dry vacuum controls."""
from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import DreameWetDryCoordinator


def build_device_info(coordinator: DreameWetDryCoordinator) -> DeviceInfo:
    """Device registry info shared by every entity of this device.

    The device-list record has no top-level "name"; the display name lives in
    deviceInfo.displayName (or customName).
    """
    snap = coordinator.device_info_raw
    return DeviceInfo(
        identifiers={(DOMAIN, coordinator.device_id)},
        name=(snap.get("deviceInfo") or {}).get("displayName")
        or snap.get("customName")
        or snap.get("name")
        or "Dreame Wet & Dry Vacuum",
        manufacturer=MANUFACTURER,
        model=snap.get("model", MODEL),
        sw_version=snap.get("ver") or snap.get("firmware"),
    )


class DreameWetDryEntity(CoordinatorEntity[DreameWetDryCoordinator]):
    """Base entity bound to one (siid, piid) property."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameWetDryCoordinator, key: tuple[int, int], meta: dict) -> None:
        super().__init__(coordinator)
        self._key = key
        self._siid, self._piid = key
        self._data_key = f"{key[0]}.{key[1]}"
        self._meta = meta
        self._attr_unique_id = f"{coordinator.device_id}_{meta['key']}"
        # Display names come from translations/<lang>.json (entity section),
        # keyed by the meta "key"; the "name" field in const.py is documentation.
        self._attr_translation_key = meta["key"]
        self._attr_icon = meta.get("icon")
        self._attr_device_info = build_device_info(coordinator)

    @property
    def _raw(self) -> Any:
        return self.coordinator.data.get(self._data_key)

    async def _set(self, value: Any) -> bool:
        if not await self.coordinator.async_set_prop(self._siid, self._piid, value):
            raise HomeAssistantError(f"Dreame rejected property {self._data_key}")
        return True
