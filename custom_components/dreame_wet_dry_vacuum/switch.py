"""Switch platform for Dreame wet & dry vacuum (writable boolean properties)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DreameWetDryConfigEntry
from .const import (
    H15_ARM_MODES,
    H15_SCHEDULE_DAYS,
    H15_SWITCH_SETTINGS,
    KNOWN_SWITCH_PROPS,
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
        async_add_entities([
            *(DreameH15Switch(coordinator, key) for key in H15_SWITCH_SETTINGS),
            *(DreameH15Switch(coordinator, (24, 1), arm_bit=bit) for bit in H15_ARM_MODES),
            *(DreameWetDryScheduleDaySwitch(coordinator, day) for day in H15_SCHEDULE_DAYS),
        ])
        return

    async_add_entities(
        DreameWetDrySwitch(coordinator, key, meta)
        for key, meta in KNOWN_SWITCH_PROPS.items()
    )


class DreameWetDrySwitch(DreameWetDryEntity, SwitchEntity):
    """A boolean device setting (0/1).

    For `optimistic` props the current state isn't readable from any channel, so
    the entity is marked assumed_state and only reflects the last command sent
    (stored optimistically by the coordinator after a successful write).
    """

    def __init__(self, coordinator, key, meta) -> None:
        super().__init__(coordinator, key, meta)
        if meta.get("optimistic"):
            self._attr_assumed_state = True

    @property
    def is_on(self) -> bool | None:
        raw = self._raw
        if raw is None:
            return None
        try:
            return int(raw) != 0
        except (ValueError, TypeError):
            return bool(raw)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(0)


class DreameH15Switch(DreameH15Setting, SwitchEntity):
    """A boolean setting or one inverted lifting-arm mode bit."""

    @property
    def is_on(self) -> bool | None:
        value = self._raw
        if value is None:
            return None
        if self._arm_bit is not None:
            return value <= 31 and not bool(value & (1 << self._arm_bit))
        on, off = H15_SWITCH_SETTINGS[self._key]
        return True if value == on else False if value == off else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._write(1 if self._arm_bit is not None else H15_SWITCH_SETTINGS[self._key][0])

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._write(0 if self._arm_bit is not None else H15_SWITCH_SETTINGS[self._key][1])




class DreameWetDryScheduleDaySwitch(DreameH15Setting, SwitchEntity):
    """One scheduled weekday, preserving all other weekdays and start time."""

    def __init__(self, coordinator, day: int) -> None:
        super().__init__(coordinator, (1, 77))
        self._day = day
        self._attr_name = f"Wash and dry schedule — {H15_SCHEDULE_DAYS[day]}"
        self._attr_unique_id += f"_day_{day}"

    @property
    def is_on(self) -> bool | None:
        try:
            return self._day in decode_schedule(self._raw)["days"]
        except ValueError:
            return None

    @property
    def available(self) -> bool:
        return super().available and self.is_on is not None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_h15_schedule_day(self._day, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_h15_schedule_day(self._day, False)
