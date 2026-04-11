"""Lawn mower entity for Gardena Smart System."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lawn_mower import (
    LawnMowerActivity,
    LawnMowerEntity,
    LawnMowerEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import (
    DOMAIN,
    MOWER_ACTIVITY_NONE,
    MOWER_ACTIVITY_OK_CHARGING,
    MOWER_ACTIVITY_OK_CUTTING,
    MOWER_ACTIVITY_OK_CUTTING_TIMER_OVERRIDDEN,
    MOWER_ACTIVITY_OK_LEAVING,
    MOWER_ACTIVITY_OK_SEARCHING,
    MOWER_ACTIVITY_PARKED_AUTOTIMER,
    MOWER_ACTIVITY_PARKED_PARK_SELECTED,
    MOWER_ACTIVITY_PARKED_TIMER,
    MOWER_ACTIVITY_PAUSED,
    SERVICE_COMMON,
    SERVICE_MOWER,
)
from ..coordinator import GardenaDataCoordinator
from .base import GardenaEntity

_LOGGER = logging.getLogger(__name__)

MOWING_ACTIVITIES = {
    MOWER_ACTIVITY_OK_CUTTING,
    MOWER_ACTIVITY_OK_CUTTING_TIMER_OVERRIDDEN,
    MOWER_ACTIVITY_OK_SEARCHING,
    MOWER_ACTIVITY_OK_LEAVING,
}

DOCKED_ACTIVITIES = {
    MOWER_ACTIVITY_OK_CHARGING,
    MOWER_ACTIVITY_PARKED_TIMER,
    MOWER_ACTIVITY_PARKED_PARK_SELECTED,
    MOWER_ACTIVITY_PARKED_AUTOTIMER,
    MOWER_ACTIVITY_NONE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gardena lawn mower entities."""
    coordinator: GardenaDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[GardenaLawnMower] = []
    for device_id, device in coordinator.devices.items():
        for service in device.get("services", []):
            if service["type"] == SERVICE_MOWER:
                entities.append(
                    GardenaLawnMower(
                        coordinator=coordinator,
                        device_id=device_id,
                        service_id=service["id"],
                    )
                )

    async_add_entities(entities)


class GardenaLawnMower(GardenaEntity, LawnMowerEntity):
    """Representation of a Gardena Sileno lawn mower."""

    _attr_supported_features = (
        LawnMowerEntityFeature.START_MOWING
        | LawnMowerEntityFeature.DOCK
        | LawnMowerEntityFeature.PAUSE
    )

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        device_id: str,
        service_id: str,
    ) -> None:
        """Initialize the lawn mower entity."""
        super().__init__(coordinator, device_id, service_id, SERVICE_MOWER)
        self._attr_unique_id = f"{device_id}_{SERVICE_MOWER}"
        self._attr_translation_key = "mower"

    @property
    def activity(self) -> LawnMowerActivity | None:
        """Return the current activity."""
        gardena_activity = self.get_service_attribute("activity", {})
        if isinstance(gardena_activity, dict):
            gardena_activity = gardena_activity.get("value", "")

        if gardena_activity in MOWING_ACTIVITIES:
            return LawnMowerActivity.MOWING
        if gardena_activity == MOWER_ACTIVITY_PAUSED:
            return LawnMowerActivity.PAUSED
        if gardena_activity in DOCKED_ACTIVITIES:
            return LawnMowerActivity.DOCKED
        if gardena_activity and "ERROR" in str(gardena_activity).upper():
            return LawnMowerActivity.ERROR

        return LawnMowerActivity.DOCKED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "battery_level": self.get_common_attribute("batteryLevel"),
            "rf_link_level": self.get_common_attribute("rfLinkLevel"),
            "operating_hours": self.get_service_attribute("operatingHours"),
            "last_error_code": self.get_service_attribute("lastErrorCode"),
            "activity": self.get_service_attribute("activity"),
        }

    async def async_start_mowing(self) -> None:
        """Start mowing."""
        await self.coordinator.client.mower_start(self._service_id)

    async def async_dock(self) -> None:
        """Dock the mower."""
        await self.coordinator.client.mower_park(self._service_id)

    async def async_pause(self) -> None:
        """Pause the mower."""
        await self.coordinator.client.mower_pause(self._service_id)
