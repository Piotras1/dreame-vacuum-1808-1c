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
from .vacuum import ERROR_CODE_TO_ERROR
from .vacuum import STATE_CODE_TO_ACTIVITY

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class DreameSensorDescription(SensorEntityDescription):
    """Sensor description with a function to pull the value off DreameStatus."""

    value_fn: Callable[[DreameStatus], object] = lambda status: None


MOP_MODE_NAMES = {1: "Low", 2: "Medium", 3: "High"}
WATER_BOX_STATES = {0: "Tank off", 1: "Tank on"}

SENSOR_DESCRIPTIONS: tuple[DreameSensorDescription, ...] = (
    DreameSensorDescription(
        key="mop_water_level",
        name="Mop water level",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:water-percent",
        value_fn=lambda status: MOP_MODE_NAMES.get(status.mop_mode, status.mop_mode),
    ),
    DreameSensorDescription(
        key="water_tank_status",
        name="Water tank status",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:cup-water",
        value_fn=lambda status: WATER_BOX_STATES.get(status.water_box, status.water_box),
    ),
    DreameSensorDescription(
        key="main_brush_time_left",
        name="Main brush time left",
        native_unit_of_measurement="h",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer-sync-outline",
        value_fn=lambda status: status.brush_left_time,
    ),
    DreameSensorDescription(
        key="side_brush_time_left",
        name="Side brush time left",
        native_unit_of_measurement="h",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer-sync-outline",
        value_fn=lambda status: status.brush_left_time2,
    ),
    DreameSensorDescription(
        key="filter_left_time",
        name="Filter time left",
        native_unit_of_measurement="h",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer-sync-outline",
        value_fn=lambda status: status.filter_left_time,
    ),
    DreameSensorDescription(
        key="battery_level",
        name="Battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
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
        icon="mdi:pinwheel-outline",
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
        native_unit_of_measurement="cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:counter",
        value_fn=lambda status: status.total_clean_count,
    ),
    DreameSensorDescription(
        key="status",
        name="vacuum status",
        icon="mdi:robot-vacuum",
        value_fn=lambda status: STATE_CODE_TO_ACTIVITY.get(status.status, "Unknown") if status.status is not None else None,
    ),
    DreameSensorDescription(
        key="cleaning_area",
        name="Last cleaning area",
        native_unit_of_measurement="m²",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:texture-box",
        value_fn=lambda status: status.area,
    ),
    DreameSensorDescription(
        key="cleaning_time",
        name="Last cleaning time",
        native_unit_of_measurement="min",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer-outline",
        value_fn=lambda status: status.timer,
    ),
    DreameSensorDescription(
        key="vacuum_error",
        name="Error status",
        icon="mdi:alert-circle-outline",
        value_fn=lambda status: ERROR_CODE_TO_ERROR.get(status.error, "Unknown") if status.error is not None else None,
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
    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return {
            "available_states": list(STATE_CODE_TO_ACTIVITY.values())
        }
