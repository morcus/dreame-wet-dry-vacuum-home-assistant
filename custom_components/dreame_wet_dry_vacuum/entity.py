"""Shared base entity for Dreame wet & dry vacuum controls."""
from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DreameAPIError
from .const import (
    DOMAIN,
    H15_ARM_MODES,
    H15_PROPERTY_META,
    MANUFACTURER,
    MODEL,
    h15_setting_name,
)
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
        return await self.coordinator.async_set_prop(self._siid, self._piid, value)


class DreameH15Setting(CoordinatorEntity):
    """A model-specific setting with explicit write error handling."""

    _attr_has_entity_name = True
    # Daily controls belong in the device's Controls card, not Configuration.
    _attr_entity_category = None

    def __init__(self, coordinator, key: tuple[int, int], *, arm_bit: int | None = None) -> None:
        super().__init__(coordinator)
        self._key = key
        self._arm_bit = arm_bit
        suffix = f"_bit_{arm_bit}" if arm_bit is not None else ""
        self._attr_unique_id = f"{coordinator.device_id}_h15_setting_{key[0]}_{key[1]}{suffix}"
        self._attr_name = (
            f"Lifting arm — {H15_ARM_MODES[arm_bit]}"
            if arm_bit is not None else h15_setting_name(key)
        )
        self._attr_icon = H15_PROPERTY_META[key].get("icon")
        self._attr_device_info = build_device_info(coordinator)

    @property
    def _raw(self) -> int | None:
        raw = self.coordinator.data.get(f"{self._key[0]}.{self._key[1]}")
        if isinstance(raw, bool):
            return None
        try:
            value = int(raw)
            return value if value >= 0 and value == float(raw) else None
        except (TypeError, ValueError, OverflowError):
            return None

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        if self._arm_bit is not None:
            return self._raw is not None and self._raw <= 31
        if self._key in {(16, 7), (16, 8), (16, 1), (16, 2)}:
            if self.coordinator.data.get("16.6") not in (1, "1"):
                return False
            if self._key in {(16, 1), (16, 2)} and self.coordinator.data.get("16.7") not in (4, "4"):
                return False
            if self._key == (16, 1):
                return self.coordinator.data.get("16.8") in (0, "0")
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "property": f"{self._key[0]}.{self._key[1]}",
            "raw_value": self._raw,
            "mapping_status": H15_PROPERTY_META[self._key]["confidence"],
            "write_source": "Dreamehome H15 app",
            **({"value_source": "app default (device has not reported it)"}
               if self._key in getattr(self.coordinator, "h15_app_defaults", ()) else {}),
        }

    async def _write(self, value: int) -> None:
        try:
            await self.coordinator.async_set_h15_setting(self._key, value, arm_bit=self._arm_bit)
        except (ValueError, DreameAPIError) as err:
            raise HomeAssistantError(str(err)) from err
