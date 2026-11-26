"""Config flow for Dreame wet & dry vacuum."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import CountrySelector

from .api import DreameAPI, DreameAPIError, DreameAuthError
from .const import CONF_COUNTRY, CONF_DEVICE_ID, CONF_REGION, DOMAIN, REGIONS


def _user_schema(default_country: str | None) -> vol.Schema:
    """Use HA's country silently; ask only when the system has no country."""
    fields = {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_REGION, default="auto"): vol.In(REGIONS),
    }
    if not default_country:
        fields[vol.Required(CONF_COUNTRY)] = CountrySelector()
    return vol.Schema(fields)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


def _device_name(device: dict[str, Any]) -> str:
    """Best available display name for a device-list record."""
    return (
        (device.get("deviceInfo") or {}).get("displayName")
        or device.get("customName")
        or device.get("model")
        or str(device.get("did"))
    )


class DreameWetDryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the config flow for Dreame wet & dry vacuum."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str = ""
        self._password: str = ""
        self._region: str = "auto"
        self._country: str = ""
        self._devices: list[dict[str, Any]] = []

    def _api(
        self, username: str, password: str, region: str, country: str
    ) -> DreameAPI:
        return DreameAPI(
            username,
            password,
            region,
            country=country,
            session=async_get_clientsession(self.hass),
        )

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        country = (self.hass.config.country or "").upper()
        if len(country) != 2:
            country = ""

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]
            self._region = user_input[CONF_REGION]
            self._country = (user_input.get(CONF_COUNTRY) or country).upper()

            api = self._api(
                self._username, self._password, self._region, self._country
            )
            try:
                await api.login()
                self._devices = await api.get_devices()
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except DreameAPIError:
                errors["base"] = "cannot_connect"

            if not errors:
                if len(self._devices) == 1:
                    return await self._async_create_entry(self._devices[0])
                if len(self._devices) > 1:
                    return await self.async_step_device()
                errors["base"] = "no_devices"

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(country or None),
            errors=errors,
        )

    async def async_step_device(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            device = next(
                (d for d in self._devices if str(d["did"]) == str(user_input[CONF_DEVICE_ID])),
                None,
            )
            if device:
                return await self._async_create_entry(device)

        device_options = {
            str(d["did"]): f"{_device_name(d)} ({d.get('model', 'unknown')})"
            for d in self._devices
        }

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {vol.Required(CONF_DEVICE_ID): vol.In(device_options)}
            ),
        )

    async def _async_create_entry(self, device: dict[str, Any]) -> ConfigFlowResult:
        device_id = device["did"]
        await self.async_set_unique_id(str(device_id))
        self._abort_if_unique_id_configured()
        # Entries created before unique_id was set are only matchable by data
        self._async_abort_entries_match({CONF_DEVICE_ID: device_id})

        name = _device_name(device)
        return self.async_create_entry(
            title=name,
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_REGION: self._region,
                CONF_COUNTRY: self._country,
                CONF_DEVICE_ID: device_id,
                "device_model": device.get("model", ""),
                "device_name": name,
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication after the stored password stopped working."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            api = self._api(
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                entry.data.get(CONF_REGION, "auto"),
                entry.data.get(CONF_COUNTRY)
                or (self.hass.config.country or "").upper(),
            )
            try:
                await api.login()
            except DreameAuthError:
                errors["base"] = "invalid_auth"
            except DreameAPIError:
                errors["base"] = "cannot_connect"

            if not errors:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )
