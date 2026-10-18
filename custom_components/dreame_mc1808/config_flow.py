"""Config flow for the Dreame MC1808 vacuum integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN
from homeassistant.data_entry_flow import FlowResult

from . import DEFAULT_NAME, DOMAIN
from .dreame_client import DeviceException, DreameVacuum

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_TOKEN): vol.All(str, vol.Length(min=32, max=32)),
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


async def _async_validate_connection(hass, host: str, token: str) -> str:
    """Try to talk to the device once; raises on failure. Returns the device MAC."""
    device = DreameVacuum(host, token)
    await hass.async_add_executor_job(device.status)
    info = await hass.async_add_executor_job(device.info)
    mac = info.mac_address
    if not mac:
        raise DeviceException("Device did not return a MAC address")
    return mac


class DreameMC1808ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Dreame MC1808 vacuum."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                mac = await _async_validate_connection(
                    self.hass, user_input[CONF_HOST], user_input[CONF_TOKEN]
                )
            except (DeviceException, OSError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Dreame vacuum")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reconfiguration of an existing entry (e.g. IP change)."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                mac = await _async_validate_connection(
                    self.hass, user_input[CONF_HOST], user_input[CONF_TOKEN]
                )
            except (DeviceException, OSError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error reconfiguring Dreame vacuum")
                errors["base"] = "unknown"
            else:
                # Ensure the MAC isn't already used by a different entry
                existing = await self.async_set_unique_id(mac)
                if existing and existing.entry_id != entry.entry_id:
                    return self.async_abort(reason="already_configured")

                new_data = {
                    **entry.data,
                    CONF_HOST: user_input[CONF_HOST],
                    CONF_TOKEN: user_input[CONF_TOKEN],
                    CONF_NAME: user_input.get(CONF_NAME, entry.data.get(CONF_NAME, DEFAULT_NAME)),
                }
                self.hass.config_entries.async_update_entry(
                    entry,
                    data=new_data,
                    title=user_input.get(CONF_NAME, entry.title),
                    unique_id=mac,
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reconfigure_successful")

        # Prefill form with current values
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST, "")): str,
                vol.Required(CONF_TOKEN, default=entry.data.get(CONF_TOKEN, "")): vol.All(
                    str, vol.Length(min=32, max=32)
                ),
                vol.Optional(
                    CONF_NAME, default=entry.data.get(CONF_NAME, entry.title)
                ): str,
            }
        )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
            description_placeholders={"name": entry.title},
        )
