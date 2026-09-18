"""Number platform for Dreame MC1808."""
from __future__ import annotations

import logging
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, DreameVacuumCoordinator, DreameVacuumEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dreame volume number entity."""
    coordinator: DreameVacuumCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DreameVolumeNumber(coordinator)])


class DreameVolumeNumber(DreameVacuumEntity, NumberEntity):
    """Representation of the volume control slider."""

    _attr_name = "Volume"
    _attr_icon = "mdi:volume-high"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: DreameVacuumCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_volume"

    @property
    def native_value(self) -> float | None:
        """Return the current volume level."""
        status = self.coordinator.data
        if status is None:
            return None
        val = getattr(status, "audio_volume", None)
        return float(val) if val is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Set new volume value on the robot."""
        volume = int(value)
        try:
            # Używamy właściwej metody z dreame_client.py
            await self.hass.async_add_executor_job(
                self.coordinator.device.audio_position, volume
            )
            await self.coordinator.async_request_refresh()
        except Exception as exc:
            _LOGGER.error("Failed to set volume to %s: %s", volume, exc)