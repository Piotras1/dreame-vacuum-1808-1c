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


async def _async_validate_connection(hass, host: str, token: str) -> None:
    """Try to talk to the device once; raises on failure."""
    device = DreameVacuum(host, token)
    await hass.async_add_executor_job(device.status)


class DreameMC1808ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Dreame MC1808 vacuum."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial (and only) step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_HOST])
            self._abort_if_unique_id_configured()

            try:
                await _async_validate_connection(
                    self.hass, user_input[CONF_HOST], user_input[CONF_TOKEN]
                )
            except (DeviceException, OSError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Dreame vacuum")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
