"""Model-specific H15 Mix command confirmation."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .const import H15_MIX_DIRTY_TANK_FULL_BIT


def dirty_tank_full(coordinator: Any) -> bool:
    """Return the H15 Mix full-tank flag observed in property 4.2."""
    try:
        return bool(int(coordinator.props.get((4, 2), 0)) & H15_MIX_DIRTY_TANK_FULL_BIT)
    except (TypeError, ValueError):
        return False


async def async_start_self_clean(
    coordinator: Any,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Start self-cleaning and confirm the observed device state.

    The H15 Mix has returned per-property code 1 even when it started the
    cycle. Only a subsequent status change counts as success.
    """
    snapshot = coordinator.snapshot
    status = coordinator.props.get((2, 1), snapshot.get("status"))
    if dirty_tank_full(coordinator):
        raise RuntimeError("H15 Mix dirty water tank is full; empty it before self-cleaning")
    if not snapshot.get("online") or status not in (4, 15):
        raise RuntimeError("H15 Mix must be charging on its station")

    await coordinator.api.set_property(coordinator.device_id, 1, 1, 1)
    active_observations = 0
    for _ in range(5):
        await sleep(2)
        await coordinator.async_request_refresh()
        if dirty_tank_full(coordinator):
            raise RuntimeError("H15 Mix dirty water tank is full; empty it before self-cleaning")
        status = coordinator.props.get((2, 1), coordinator.snapshot.get("status"))
        if status in (5, 26, 27, 28):
            active_observations += 1
            if active_observations >= 2:
                return
        else:
            active_observations = 0
        if status in (11, 30, 31):
            raise RuntimeError("H15 Mix paused self-cleaning; check the device")
    raise RuntimeError("H15 Mix did not confirm self-cleaning")
