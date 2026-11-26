"""Number platform for Dreame wet & dry vacuum (writable numeric settings)."""
from __future__ import annotations

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameWetDryConfigEntry
from .const import H15_NUMBER_SETTINGS, KNOWN_NUMBER_PROPS
from .entity import DreameH15Setting, DreameWetDryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameWetDryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.is_h15_pro_heat:
        async_add_entities(DreameH15Number(coordinator, key) for key in H15_NUMBER_SETTINGS)
        return

    async_add_entities(
        DreameWetDryNumber(coordinator, key, meta)
        for key, meta in KNOWN_NUMBER_PROPS.items()
    )


class DreameWetDryNumber(DreameWetDryEntity, NumberEntity):
    """A numeric device setting."""

    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, key, meta) -> None:
        super().__init__(coordinator, key, meta)
        self._attr_native_min_value = meta.get("min", 0)
        self._attr_native_max_value = meta.get("max", 100)
        self._attr_native_step = meta.get("step", 1)
        if meta.get("unit"):
            self._attr_native_unit_of_measurement = meta["unit"]
        if meta.get("config"):
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def native_value(self) -> float | None:
        raw = self._raw
        if raw is None:
            return None
        try:
            return float(raw)
        except (ValueError, TypeError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self._set(int(value))


class DreameH15Number(DreameH15Setting, NumberEntity):
    """Three-position voice volume or schedule time in minutes."""

    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, key) -> None:
        super().__init__(coordinator, key)
        minimum, maximum, step = H15_NUMBER_SETTINGS[key]
        if key == (1, 14):
            self._attr_name = None
            self._attr_translation_key = "h15_volume"
        self._scale = 60 if key == (1, 76) else 30
        self._attr_native_min_value = minimum / self._scale
        self._attr_native_max_value = maximum / self._scale
        self._attr_native_step = step / self._scale
        self._attr_native_unit_of_measurement = "min" if key == (1, 76) else None

    @property
    def native_value(self) -> float | None:
        value = self._raw
        minimum, maximum, step = H15_NUMBER_SETTINGS[self._key]
        return value / self._scale if value is not None and minimum <= value <= maximum and value % step == 0 else None

    async def async_set_native_value(self, value: float) -> None:
        if not math.isfinite(value) or value != int(value):
            raise HomeAssistantError("Setting must be a whole number")
        await self._write(int(value * self._scale))

    @property
    def extra_state_attributes(self) -> dict:
        attrs = super().extra_state_attributes
        if self._key == (1, 76) and self.native_value is not None:
            minutes = int(self.native_value)
            attrs["time"] = f"{minutes // 60:02d}:{minutes % 60:02d}"
            attrs["timezone"] = "Device timezone"
        if self._key == (1, 14):
            attrs["levels"] = {0: "Silent", 1: "Low", 2: "High"}
            attrs["volume_level"] = {0: "Silent", 30: "Low", 60: "High"}.get(self._raw)
        return attrs
