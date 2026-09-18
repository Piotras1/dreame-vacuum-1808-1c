"""Select platform for Dreame MC1808."""
from __future__ import annotations

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, DreameVacuumCoordinator, DreameVacuumEntity
from .vacuum import SPEED_CODE_TO_NAME

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dreame fan speed select entity."""
    coordinator: DreameVacuumCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DreameFanSpeedSelect(coordinator)])


class DreameFanSpeedSelect(DreameVacuumEntity, SelectEntity):
    """Representation of the fan speed select dropdown."""

    _attr_name = "Fan speed"
    _attr_icon = "mdi:fan"
    _attr_options = list(SPEED_CODE_TO_NAME.values())

    def __init__(self, coordinator: DreameVacuumCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_fan_speed_select"
        self._name_to_code = {v: k for k, v in SPEED_CODE_TO_NAME.items()}

    @property
    def current_option(self) -> str | None:
        """Return the selected fan speed."""
        status = self.coordinator.data
        if status is None or status.fan_speed is None:
            return None
        return SPEED_CODE_TO_NAME.get(status.fan_speed)

    async def async_select_option(self, option: str) -> None:
        """Change the selected fan speed."""
        speed_code = self._name_to_code.get(option)
        if speed_code is None:
            _LOGGER.error("Unknown fan speed option: %s", option)
            return

        try:
            await self.hass.async_add_executor_job(
                self.coordinator.device.set_fan_speed, speed_code
            )
            await self.coordinator.async_request_refresh()
        except Exception as exc:
            _LOGGER.error("Failed to set fan speed to %s: %s", option, exc)