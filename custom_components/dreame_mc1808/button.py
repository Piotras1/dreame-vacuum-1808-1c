"""Button platform for Dreame MC1808."""
from __future__ import annotations

import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from . import DOMAIN, DreameVacuumCoordinator, DreameVacuumEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Dreame button entities."""
    coordinator: DreameVacuumCoordinator = hass.data[DOMAIN][entry.entry_id]
    
    buttons = [
        # Sterowanie podstawowe (Sekcja Główna / Sterowanie)
        DreameActionButton(
            coordinator,
            name="Start cleaning",
            icon="mdi:play",
            unique_id_suffix="start",
            action_func=coordinator.device.start_sweep,
        ),
        DreameActionButton(
            coordinator,
            name="Stop cleaning",
            icon="mdi:stop",
            unique_id_suffix="stop",
            action_func=coordinator.device.stop_sweeping,
        ),
        DreameActionButton(
            coordinator,
            name="Go home",
            icon="mdi:home-import-outline",
            unique_id_suffix="go_home",
            action_func=coordinator.device.return_home,
        ),
        DreameActionButton(
            coordinator,
            name="Find me",
            icon="mdi:map-marker-radius",
            unique_id_suffix="find_me",
            action_func=coordinator.device.find,
        ),
        # Resetowanie zużycia części (Sekcja Konfiguracja / Diagnostyka)
        DreameActionButton(
            coordinator,
            name="Reset main brush",
            icon="mdi:broom",
            unique_id_suffix="reset_main_brush",
            action_func=coordinator.device.reset_brush_life,
            entity_category=EntityCategory.CONFIG,
        ),
        DreameActionButton(
            coordinator,
            name="Reset side brush",
            icon="mdi:pinwheel-outline",
            unique_id_suffix="reset_side_brush",
            action_func=coordinator.device.reset_brush_life2,
            entity_category=EntityCategory.CONFIG,
        ),
        DreameActionButton(
            coordinator,
            name="Reset filter",
            icon="mdi:air-filter",
            unique_id_suffix="reset_filter",
            action_func=coordinator.device.reset_filter_life,
            entity_category=EntityCategory.CONFIG,
        ),
    ]

    async_add_entities(buttons)


class DreameActionButton(DreameVacuumEntity, ButtonEntity):
    """Representation of a Dreame action button."""

    def __init__(
        self,
        coordinator: DreameVacuumCoordinator,
        name: str,
        icon: str,
        unique_id_suffix: str,
        action_func,
        entity_category: EntityCategory | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_id_suffix}"
        self._action_func = action_func
        if entity_category:
            self._attr_entity_category = entity_category

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.hass.async_add_executor_job(self._action_func)
            await self.coordinator.async_request_refresh()
        except Exception as exc:
            _LOGGER.error("Failed to execute action %s: %s", self._attr_name, exc)
