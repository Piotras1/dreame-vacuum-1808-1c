"""Binary sensor(s) for the Dreame MC1808 (currently: charging status).

Grouped under the same device as the vacuum entity and the diagnostic
sensors via the shared DreameVacuumEntity base / coordinator.
"""
from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, DreameVacuumCoordinator, DreameVacuumEntity

_LOGGER = logging.getLogger(__name__)

# Same "status" field vacuum.py uses for the main activity (see
# STATE_CODE_TO_ACTIVITY in vacuum.py). Code 6 = actively charging on the
# dock. Once the battery hits 100% the device reports Idle (2) instead,
# even while still physically on the dock - confirmed against real
# hardware behavior. The separate "state"/ChargeStatus property (siid 2)
# was tried first but doesn't track reliably on this firmware, so we key
# off the main status field instead.
CHARGING_STATUS_CODE = 6


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the charging binary sensor from a config entry."""
    coordinator: DreameVacuumCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DreameChargingBinarySensor(coordinator)])


class DreameChargingBinarySensor(DreameVacuumEntity, BinarySensorEntity):
    """Whether the vacuum is currently charging on the dock."""

    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: DreameVacuumCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_battery_charging"

    @property
    def is_on(self) -> bool | None:
        """Return True while the vacuum is actively charging."""
        status = self.coordinator.data
        if status is None or status.status is None:
            return None
        return int(status.status) == CHARGING_STATUS_CODE