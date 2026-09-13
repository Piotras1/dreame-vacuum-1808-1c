"""Diagnostic sensors for the Dreame MC1808 (brushes, filter, cleaning stats).

These share the same coordinator as the vacuum entity (one poll of the
device feeds all of them) and the same device_info, so they show up
grouped under the vacuum's device page instead of as standalone entities.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, DreameVacuumCoordinator, DreameVacuumEntity
from .dreame_client import DreameStatus

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DreameSensorDescription(SensorEntityDescription):
    """Sensor description with a function to pull the value off DreameStatus."""

    value_fn: Callable[[DreameStatus], object] = lambda status: None


SENSOR_DESCRIPTIONS: tuple[DreameSensorDescription, ...] = (
    DreameSensorDescription(
        key="battery_level",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.battery,
    ),
    DreameSensorDescription(
        key="main_brush_life_level",
        name="Main brush life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:broom",
        value_fn=lambda status: status.brush_life_level,
    ),
    DreameSensorDescription(
        key="side_brush_life_level",
        name="Side brush life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:broom",
        value_fn=lambda status: status.brush_life_level2,
    ),
    DreameSensorDescription(
        key="filter_life_level",
        name="Filter life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:air-filter",
        value_fn=lambda status: status.filter_life_level,
    ),
    DreameSensorDescription(
        key="total_clean_count",
        name="Total cleanings",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:counter",
        value_fn=lambda status: status.total_clean_count,
    ),
    DreameSensorDescription(
        key="cleaning_area",
        name="Last cleaning area",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:texture-box",
        value_fn=lambda status: status.area,
    ),
    DreameSensorDescription(
        key="cleaning_time",
        name="Last cleaning time",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer-outline",
        value_fn=lambda status: status.timer,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up diagnostic sensors from a config entry."""
    coordinator: DreameVacuumCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DreameVacuumSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class DreameVacuumSensor(DreameVacuumEntity, SensorEntity):
    """A single read-only diagnostic value from the vacuum."""

    entity_description: DreameSensorDescription

    def __init__(
        self,
        coordinator: DreameVacuumCoordinator,
        description: DreameSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def native_value(self):
        """Return the current value for this sensor."""
        status = self.coordinator.data
        if status is None:
            return None
        return self.entity_description.value_fn(status)
