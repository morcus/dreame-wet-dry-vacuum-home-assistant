"""Firmware update status for the Dreame H15 (read-only, from the app OTA check)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DreameWetDryConfigEntry
from .coordinator import DreameWetDryCoordinator
from .entity import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameWetDryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DreameWetDryCoordinator = entry.runtime_data
    if coordinator.is_h15_pro_heat:
        async_add_entities([DreameH15FirmwareUpdate(coordinator)])


class DreameH15FirmwareUpdate(CoordinatorEntity[DreameWetDryCoordinator], UpdateEntity):
    """Shows installed/latest firmware; installing stays in the Dreamehome app."""

    _attr_has_entity_name = True
    _attr_name = "Firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DreameWetDryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_h15_firmware"
        self._attr_device_info = build_device_info(coordinator)

    def _data(self) -> dict[str, Any]:
        return self.coordinator.h15_firmware or {}

    @property
    def installed_version(self) -> str | None:
        data = self._data()
        return str(data.get("curVersion") or self.coordinator.device_info_raw.get("ver") or "") or None

    @property
    def latest_version(self) -> str | None:
        data = self._data()
        if data.get("hasNewFirmware") and data.get("newVersion"):
            return str(data["newVersion"])
        return self.installed_version

    @property
    def release_summary(self) -> str | None:
        fw = self._data().get("firmwareVersion") or {}
        parts = [f"{k}: {v.get('description')}" for k, v in fw.items()
                 if isinstance(v, dict) and v.get("hasNewFirmware") and v.get("description")]
        return "\n\n".join(parts)[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"install_from": "Dreamehome app (Settings > Firmware Upgrade)"}
