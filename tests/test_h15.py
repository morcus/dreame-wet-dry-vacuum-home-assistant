"""H15 Mix command confirmation without Home Assistant or a live device."""
import asyncio
from types import SimpleNamespace

import pytest

from custom_components.dreame_wet_dry_vacuum.h15 import (
    async_start_self_clean,
    dirty_tank_full,
)


async def no_sleep(_seconds):
    pass


def coordinator(*, online=True, status=4, status_after_refresh=26,
                full_tank=False, full_tank_after_refresh=False):
    sent = []
    snapshot = {"online": online, "status": status}
    props = {(2, 1): status, (4, 2): 4096 if full_tank else 0}

    async def set_property(*args):
        sent.append(args)
        return False  # observed live: code 1 can still start the cycle

    async def refresh():
        if status_after_refresh is not None:
            snapshot["status"] = status_after_refresh
            props[(2, 1)] = status_after_refresh
        if full_tank_after_refresh:
            props[(4, 2)] = 4096

    return SimpleNamespace(
        snapshot=snapshot,
        props=props,
        api=SimpleNamespace(set_property=set_property),
        device_id="test-device",
        async_request_refresh=refresh,
        sent=sent,
    )


def test_code_one_is_accepted_after_observed_state_change():
    device = coordinator()
    asyncio.run(async_start_self_clean(device, no_sleep))
    assert device.sent == [("test-device", 1, 1, 1)]


@pytest.mark.parametrize("online,status", [(False, 4), (True, 23), (True, 26)])
def test_command_blocked_unless_online_and_charging(online, status):
    device = coordinator(online=online, status=status)
    with pytest.raises(RuntimeError, match="charging on its station"):
        asyncio.run(async_start_self_clean(device, no_sleep))
    assert device.sent == []


def test_no_state_change_is_reported_as_failure():
    device = coordinator(status_after_refresh=None)
    with pytest.raises(RuntimeError, match="did not confirm"):
        asyncio.run(async_start_self_clean(device, no_sleep))
    assert len(device.sent) == 1


def test_full_tank_blocks_command_before_send():
    device = coordinator(full_tank=True)
    assert dirty_tank_full(device)
    with pytest.raises(RuntimeError, match="dirty water tank is full"):
        asyncio.run(async_start_self_clean(device, no_sleep))
    assert device.sent == []


def test_full_tank_during_start_reports_specific_error():
    device = coordinator(status_after_refresh=11, full_tank_after_refresh=True)
    with pytest.raises(RuntimeError, match="dirty water tank is full"):
        asyncio.run(async_start_self_clean(device, no_sleep))
    assert len(device.sent) == 1


def test_paused_without_full_tank_reports_device_problem():
    device = coordinator(status_after_refresh=11)
    with pytest.raises(RuntimeError, match="paused self-cleaning"):
        asyncio.run(async_start_self_clean(device, no_sleep))


def test_transient_start_followed_by_pause_is_not_success():
    device = coordinator(status_after_refresh=None)
    states = iter((26, 11))

    async def refresh():
        status = next(states)
        device.props[(2, 1)] = status
        device.snapshot["status"] = status

    device.async_request_refresh = refresh
    with pytest.raises(RuntimeError, match="paused self-cleaning"):
        asyncio.run(async_start_self_clean(device, no_sleep))
