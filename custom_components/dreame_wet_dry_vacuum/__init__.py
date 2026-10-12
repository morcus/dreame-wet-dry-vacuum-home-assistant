"""Dreame wet & dry vacuum integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DreameAPI, DreameAPIError, DreameAuthError
from .const import CONF_DEVICE_ID, CONF_REGION, H15_MIX_MODEL
from .coordinator import DreameWetDryCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.BUTTON,
]

type DreameWetDryConfigEntry = ConfigEntry[DreameWetDryCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: DreameWetDryConfigEntry) -> bool:
    """Set up Dreame wet & dry vacuum from a config entry."""
    api = DreameAPI(
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        region=entry.data.get(CONF_REGION, "eu"),
        session=async_get_clientsession(hass),
    )

    try:
        await api.login()
        devices = await api.get_devices()
    except DreameAuthError as err:
        raise ConfigEntryAuthFailed(f"Dreame credentials rejected: {err}") from err
    except DreameAPIError as err:
        raise ConfigEntryNotReady(f"Cannot connect to Dreame cloud: {err}") from err

    device_id = entry.data[CONF_DEVICE_ID]
    device_info = next((d for d in devices if str(d.get("did")) == str(device_id)), {})
    if not device_info:
        raise ConfigEntryNotReady("Dreame device is missing from this account")
    model = device_info.get("model") or entry.data.get("device_model")

    coordinator = DreameWetDryCoordinator(hass, entry, api, device_id, device_info)

    # Raises ConfigEntryNotReady / ConfigEntryAuthFailed on failure
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    coordinator.start_polling()

    # Start the real-time MQTT feed. start() builds an SSL context (blocking
    # disk I/O), so keep it off the event loop.
    await hass.async_add_executor_job(coordinator.start_mqtt)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.async_on_ha_stop)
    )

    platforms = (
        [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
        if model == H15_MIX_MODEL else PLATFORMS
    )
    await hass.config_entries.async_forward_entry_setups(entry, platforms)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: DreameWetDryConfigEntry) -> bool:
    """Unload a config entry."""
    model = entry.runtime_data.device_info_raw.get("model") or entry.data.get("device_model")
    platforms = (
        [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]
        if model == H15_MIX_MODEL else PLATFORMS
    )
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        coordinator = entry.runtime_data
        coordinator.stopping = True
        coordinator.stop_polling()
        if coordinator.mqtt:
            await hass.async_add_executor_job(coordinator.mqtt.stop)
    return unloaded
