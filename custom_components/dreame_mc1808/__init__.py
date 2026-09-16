"""The Dreame MC1808 vacuum integration.

Flattened on purpose: constants, the DataUpdateCoordinator, and the shared
entity base class all live here now instead of separate const.py /
coordinator.py / entity.py files, since none of them are big enough to
justify their own file. Only files Home Assistant itself requires to be
separate stay separate:
  - vacuum.py / sensor.py / binary_sensor.py  (loaded by domain name when
    a platform is forwarded)
  - config_flow.py                            (loaded by name when the
    "Add integration" UI flow starts)
  - dreame_client.py                          (the device driver - no HA
    dependency at all, kept apart so it stays testable on its own)
"""
from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, service
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .dreame_client import DeviceException, DreameStatus, DreameVacuum

_LOGGER = logging.getLogger(__name__)

# --- constants -------------------------------------------------------------

DOMAIN = "dreame_mc1808"
DEFAULT_NAME = "Dreame Vacuum"

SCAN_INTERVAL_SECONDS = 30

# The vacuum entity domain this integration's entities live under - not to
# be confused with DOMAIN (this integration's own domain), which is what
# the vacuum_clean_zone service is registered under (see async_setup below).
VACUUM_ENTITY_DOMAIN = "vacuum"

SERVICE_CLEAN_ZONE = "vacuum_clean_zone"
ATTR_ZONE = "zone"
ATTR_REPEATS = "repeats"

# EXPERIMENTAL - see dreame_client.py's segment_cleanup() docstring.
SERVICE_CLEAN_SEGMENT = "vacuum_clean_segment"
ATTR_ROOM_IDS = "room_ids"
ATTR_FAN_SPEED = "fan_speed"

PLATFORMS: list[Platform] = [Platform.VACUUM, Platform.SENSOR, Platform.BINARY_SENSOR]


# --- coordinator -------------------------------------------------------------


class DreameVacuumCoordinator(DataUpdateCoordinator[DreameStatus]):
    """Polls the vacuum once per interval; hands the same DreameStatus
    snapshot to every entity (vacuum + sensors + binary sensor) instead of
    each entity polling the device independently."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, device: DreameVacuum
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.data.get(CONF_HOST)})",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.device = device
        self.entry = entry

    async def _async_update_data(self) -> DreameStatus:
        try:
            return await self.hass.async_add_executor_job(self.device.status)
        except (DeviceException, OSError) as exc:
            raise UpdateFailed(f"Error communicating with vacuum: {exc}") from exc


# --- shared entity base ------------------------------------------------------


class DreameVacuumEntity(CoordinatorEntity[DreameVacuumCoordinator]):
    """Common base for every entity belonging to one physical vacuum.

    Providing the same `device_info` (keyed off the config entry) from one
    place is what makes the vacuum entity and the diagnostic sensors show
    up grouped under a single device in Settings -> Devices & services.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: DreameVacuumCoordinator) -> None:
        super().__init__(coordinator)
        entry = coordinator.entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data.get(CONF_NAME) or DEFAULT_NAME,
            manufacturer="Dreame",
            model="MC1808 / 1C STYTJ01ZHM",
        )


# --- integration setup --------------------------------------------------

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register integration-wide services.

    Per current HA guidance, entity services must be registered under the
    integration's own domain (dreame_mc1808), not under the entity's
    platform domain (vacuum) - and from here (async_setup), not from a
    platform's async_setup_entry, so the service exists even before any
    config entry has finished loading.
    """
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CLEAN_ZONE,
        entity_domain=VACUUM_ENTITY_DOMAIN,
        schema={
            vol.Required(ATTR_ZONE): cv.string,
            vol.Optional(ATTR_REPEATS, default=1): vol.All(
                vol.Coerce(int), vol.Clamp(min=1, max=3)
            ),
        },
        func="async_clean_zone",
    )
    # EXPERIMENTAL - see dreame_client.py's segment_cleanup() docstring
    # for sourcing/caveats. Test on real hardware before relying on it.
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_CLEAN_SEGMENT,
        entity_domain=VACUUM_ENTITY_DOMAIN,
        schema={
            vol.Required(ATTR_ROOM_IDS): vol.All(cv.ensure_list, [vol.Coerce(int)]),
            vol.Optional(ATTR_REPEATS, default=1): vol.All(
                vol.Coerce(int), vol.Clamp(min=1, max=3)
            ),
            vol.Optional(ATTR_FAN_SPEED, default=1): vol.All(
                vol.Coerce(int), vol.Clamp(min=0, max=3)
            ),
        },
        func="async_clean_segment",
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dreame MC1808 from a config entry."""
    device = DreameVacuum(entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    coordinator = DreameVacuumCoordinator(hass, entry, device)

    # Fail entry setup (with a clean "retry" state) if the vacuum can't be
    # reached yet, instead of silently creating entities with no data.
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
