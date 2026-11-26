"""Select platform for Dreame wet & dry vacuum (writable enum properties)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameWetDryConfigEntry
from .const import (
    H15_PRIMARY_SELECT_KEYS,
    H15_SELECT_SETTINGS,
    H15_SELECT_VALUE_ALIASES,
    KNOWN_SELECT_PROPS,
    decode_schedule,
)
from .entity import DreameH15Setting, DreameWetDryEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DreameWetDryConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    if coordinator.is_h15_pro_heat:
        async_add_entities(DreameH15Select(coordinator, key) for key in H15_SELECT_SETTINGS if key in H15_PRIMARY_SELECT_KEYS)
        return

    async_add_entities(
        DreameWetDrySelect(coordinator, key, meta)
        for key, meta in KNOWN_SELECT_PROPS.items()
    )


class DreameWetDrySelect(DreameWetDryEntity, SelectEntity):
    """An enum device setting exposed as a dropdown."""

    def __init__(self, coordinator, key, meta) -> None:
        super().__init__(coordinator, key, meta)
        self._value_to_label: dict[int, str] = meta["options"]
        self._label_to_value = {v: k for k, v in self._value_to_label.items()}
        self._attr_options = list(self._value_to_label.values())

    @property
    def current_option(self) -> str | None:
        raw = self._raw
        if raw is None:
            return None
        try:
            return self._value_to_label.get(int(raw))
        except (ValueError, TypeError):
            return None

    async def async_select_option(self, option: str) -> None:
        value = self._label_to_value.get(option)
        if value is not None:
            await self._set(value)


class DreameH15Select(DreameH15Setting, SelectEntity):
    """An H15 enum shown as a dropdown with only app-supported options."""

    def __init__(self, coordinator, key) -> None:
        super().__init__(coordinator, key)
        self._options = H15_SELECT_SETTINGS[key]
        self._attr_options = list(self._options.values())

    @property
    def current_option(self) -> str | None:
        if self._key == (1, 77) and self._raw not in self._options:
            try:
                decode_schedule(self._raw)
                return "Custom weekdays"
            except ValueError:
                return None
        raw = self._raw
        if self._key == (24, 1):
            raw = raw & 29 if raw is not None and raw <= 31 else None
        raw = H15_SELECT_VALUE_ALIASES.get(self._key, {}).get(raw, raw)
        return self._options.get(raw)

    @property
    def available(self) -> bool:
        if self._key == (24, 1):
            return super().available and self._raw is not None and self._raw <= 31
        return super().available

    @property
    def options(self) -> list[str]:
        options = list(self._options.values())
        if self.current_option == "Custom weekdays":
            options.append("Custom weekdays")
        return options

    async def async_select_option(self, option: str) -> None:
        if option == "Custom weekdays" and self.current_option == option:
            return
        for raw, label in self._options.items():
            if option == label:
                await self._write(raw)
                return
        raise HomeAssistantError(f"Unsupported H15 option: {option}")
