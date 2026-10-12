"""Button platform for Dreame wet & dry vacuum (one-shot commands)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameWetDryConfigEntry
from .const import H15_MIX_MODEL, KNOWN_BUTTON_PROPS
from .entity import DreameWetDryEntity
from .h15 import async_start_self_clean, dirty_tank_full


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameWetDryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    buttons = KNOWN_BUTTON_PROPS.items()
    if coordinator.device_info_raw.get("model") == H15_MIX_MODEL:
        buttons = [(key, meta) for key, meta in buttons if key == (1, 1)]
    async_add_entities(
        DreameWetDryButton(coordinator, key, meta)
        for key, meta in buttons
    )


class DreameWetDryButton(DreameWetDryEntity, ButtonEntity):
    """Sends a fixed value to a property when pressed."""

    def __init__(self, coordinator, key, meta) -> None:
        super().__init__(coordinator, key, meta)
        self._press_value = meta.get("press_value", 1)

    @property
    def available(self) -> bool:
        if self.coordinator.device_info_raw.get("model") == H15_MIX_MODEL:
            status = self.coordinator.props.get((2, 1))
            return (
                bool(self.coordinator.snapshot.get("online"))
                and status in (4, 15)
                and not dirty_tank_full(self.coordinator)
            )
        return super().available

    async def async_press(self) -> None:
        if self.coordinator.device_info_raw.get("model") == H15_MIX_MODEL:
            try:
                await async_start_self_clean(self.coordinator)
            except RuntimeError as err:
                raise HomeAssistantError(str(err)) from err
            return
        await self._set(self._press_value)
