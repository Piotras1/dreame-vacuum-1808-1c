"""Vacuum platform for the Dreame MC1808."""
from __future__ import annotations

from functools import partial
import logging

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, DreameVacuumCoordinator, DreameVacuumEntity
from .dreame_client import DeviceException

_LOGGER = logging.getLogger(__name__)

ATTR_STATUS = "status"
ATTR_ERROR = "error"
ATTR_FAN_SPEED = "fan_speed"
ATTR_CLEANING_TIME = "cleaning_time"
ATTR_CLEANING_AREA = "cleaning_area"
ATTR_MAIN_BRUSH_LEFT_TIME = "main_brush_time_left"
ATTR_MAIN_BRUSH_LIFE_LEVEL = "main_brush_life_level"
ATTR_SIDE_BRUSH_LEFT_TIME = "side_brush_time_left"
ATTR_SIDE_BRUSH_LIFE_LEVEL = "side_brush_life_level"
ATTR_FILTER_LIFE_LEVEL = "filter_life_level"
ATTR_FILTER_LEFT_TIME = "filter_left_time"
ATTR_CLEANING_TOTAL_TIME = "total_cleaning_count"

SUPPORT_DREAME = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.START
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.FAN_SPEED
)

STATE_CODE_TO_ACTIVITY = {
    1: VacuumActivity.CLEANING,
    2: VacuumActivity.IDLE,
    3: VacuumActivity.PAUSED,
    4: VacuumActivity.ERROR,
    5: VacuumActivity.RETURNING,
    6: VacuumActivity.DOCKED,
}

SPEED_CODE_TO_NAME = {
    0: "Silent",
    1: "Standard",
    2: "Medium",
    3: "Turbo",
}

ERROR_CODE_TO_ERROR = {
    0: "NoError",
    1: "Drop",
    2: "Cliff",
    3: "Bumper",
    4: "Gesture",
    5: "Bumper_repeat",
    6: "Drop_repeat",
    7: "Optical_flow",
    8: "No_box",
    9: "No_tankbox",
    10: "Waterbox_empty",
    11: "Box_full",
    12: "Brush",
    13: "Side_brush",
    14: "Fan",
    15: "Left_wheel_motor",
    16: "Right_wheel_motor",
    17: "Turn_suffocate",
    18: "Forward_suffocate",
    19: "Charger_get",
    20: "Battery_low",
    21: "Charge_fault",
    22: "Battery_percentage",
    23: "Heart",
    24: "Camera_occlusion",
    25: "Camera_fault",
    26: "Event_battery",
    27: "Forward_looking",
    28: "Gyroscope",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the vacuum entity from a config entry.

    The vacuum_clean_zone service is registered once, integration-wide, in
    __init__.py's async_setup - not here. Registering entity services from
    a platform's async_setup_entry is deprecated as of HA 2025.9/2025.10;
    it made service availability depend on a config entry having loaded.
    """
    coordinator: DreameVacuumCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DreameVacuumEntityImpl(coordinator)])


class DreameVacuumEntityImpl(DreameVacuumEntity, StateVacuumEntity):
    """Representation of the Dreame MC1808 vacuum itself.

    `_attr_name = None` makes this the device's "main" entity, so it is
    just shown as the device name (e.g. "Tadeusz") rather than
    "Tadeusz Vacuum".
    """

    _attr_name = None

    def __init__(self, coordinator: DreameVacuumCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_vacuum"
        self._fan_speeds_reverse = {v: k for k, v in SPEED_CODE_TO_NAME.items()}

    @property
    def device(self):
        """The underlying DreameVacuum device client object."""
        return self.coordinator.device

    @property
    def activity(self) -> VacuumActivity | None:
        """Return the current activity of the vacuum cleaner."""
        status = self.coordinator.data
        if status is None or status.status is None:
            return None
        return STATE_CODE_TO_ACTIVITY.get(int(status.status))

    @property
    def fan_speed(self):
        """Return the fan speed of the vacuum cleaner."""
        status = self.coordinator.data
        if status is None or status.fan_speed is None:
            return None
        return SPEED_CODE_TO_NAME.get(status.fan_speed, "Unknown")

    @property
    def fan_speed_list(self):
        """Return the list of available fan speed steps."""
        return list(self._fan_speeds_reverse.keys())

    @property
    def supported_features(self):
        """Flag vacuum cleaner robot features that are supported."""
        return SUPPORT_DREAME

    @property
    def extra_state_attributes(self):
        """Return additional state attributes."""
        status = self.coordinator.data
        if status is None:
            return None
        activity = (
            STATE_CODE_TO_ACTIVITY.get(int(status.status))
            if status.status is not None
            else None
        )
        return {
            ATTR_STATUS: activity.value if activity is not None else None,
            ATTR_ERROR: ERROR_CODE_TO_ERROR.get(status.error, "Unknown"),
            ATTR_FAN_SPEED: SPEED_CODE_TO_NAME.get(status.fan_speed, "Unknown"),
            ATTR_MAIN_BRUSH_LEFT_TIME: status.brush_left_time,
            ATTR_MAIN_BRUSH_LIFE_LEVEL: status.brush_life_level,
            ATTR_SIDE_BRUSH_LEFT_TIME: status.brush_left_time2,
            ATTR_SIDE_BRUSH_LIFE_LEVEL: status.brush_life_level2,
            ATTR_FILTER_LIFE_LEVEL: status.filter_life_level,
            ATTR_FILTER_LEFT_TIME: status.filter_left_time,
            ATTR_CLEANING_AREA: status.area,
            ATTR_CLEANING_TIME: status.timer,
            ATTR_CLEANING_TOTAL_TIME: status.total_clean_count,
        }

    async def _try_command(self, mask_error, func, *args, **kwargs):
        """Call a vacuum command, handle errors, then refresh shared data."""
        try:
            await self.hass.async_add_executor_job(partial(func, *args, **kwargs))
            await self.coordinator.async_request_refresh()
            return True
        except DeviceException as exc:
            _LOGGER.error(mask_error, exc)
            return False

    async def async_locate(self, **kwargs):
        """Locate the vacuum cleaner."""
        await self._try_command("Unable to locate the vacuum: %s", self.device.find)

    async def async_start(self):
        """Start or resume the cleaning task."""
        await self._try_command("Unable to start the vacuum: %s", self.device.start)

    async def async_stop(self, **kwargs):
        """Stop the vacuum cleaner."""
        await self._try_command("Unable to stop: %s", self.device.stop)

    async def async_pause(self):
        """Pause the cleaning task.

        Note: the MC1808 miot actions expose `stop` (aiid 2 on siid 18) but
        no distinct "pause in place" action, so this currently issues the
        same command as async_stop. If your unit resumes from a different
        spot than expected, try `stop_sweeping` (siid 3) instead.
        """
        await self._try_command("Unable to pause: %s", self.device.stop)

    async def async_return_to_base(self, **kwargs):
        """Send the vacuum cleaner back to the dock."""
        await self._try_command(
            "Unable to return home: %s", self.device.return_home
        )

    async def async_set_fan_speed(self, fan_speed, **kwargs):
        """Set fan speed."""
        if fan_speed in self._fan_speeds_reverse:
            fan_speed = self._fan_speeds_reverse[fan_speed]
        else:
            try:
                fan_speed = int(fan_speed)
            except ValueError as exc:
                _LOGGER.error(
                    "Fan speed step not recognized (%s). Valid speeds: %s",
                    exc,
                    self.fan_speed_list,
                )
                return
        await self._try_command(
            "Unable to set fan speed: %s", self.device.set_fan_speed, fan_speed
        )

    async def async_clean_zone(self, zone, repeats=1):
        """Clean selected area.

        Note: the MC1808 zoned-clean action has no repeat-count parameter,
        so `repeats` is accepted for service-call compatibility but has no
        effect on the device yet.
        """
        if repeats != 1:
            _LOGGER.debug(
                "repeats=%s requested but not supported by this device; ignoring",
                repeats,
            )
        try:
            await self.hass.async_add_executor_job(self.device.zone_cleanup, zone)
            await self.coordinator.async_request_refresh()
        except (OSError, DeviceException) as exc:
            _LOGGER.error("Unable to send zoned_clean command to the vacuum: %s", exc)
