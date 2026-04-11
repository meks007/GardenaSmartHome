"""Valve entity for Gardena Smart System."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.valve import (
    ValveDeviceClass,
    ValveEntity,
    ValveEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import (
    DOMAIN,
    SERVICE_VALVE,
    VALVE_ACTIVITY_CLOSED,
    VALVE_ACTIVITY_MANUAL_WATERING,
    VALVE_ACTIVITY_SCHEDULED_WATERING,
)
from ..coordinator import GardenaDataCoordinator
from .base import GardenaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gardena valve entities."""
    coordinator: GardenaDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[GardenaValve] = []
    for device_id, device in coordinator.devices.items():
        for service in device.get("services", []):
            if service["type"] == SERVICE_VALVE:
                entities.append(
                    GardenaValve(
                        coordinator=coordinator,
                        device_id=device_id,
                        service_id=service["id"],
                    )
                )

    async_add_entities(entities)


class GardenaValve(GardenaEntity, ValveEntity):
    """Representation of a Gardena irrigation valve."""

    _attr_device_class = ValveDeviceClass.WATER
    _attr_reports_position = False
    _attr_supported_features = (
        ValveEntityFeature.OPEN | ValveEntityFeature.CLOSE
    )

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        device_id: str,
        service_id: str,
    ) -> None:
        """Initialize the valve entity."""
        super().__init__(coordinator, device_id, service_id, SERVICE_VALVE)
        self._attr_unique_id = f"{device_id}_{service_id}"
        self._attr_translation_key = "valve"

    @property
    def is_closed(self) -> bool:
        """Return if the valve is closed."""
        activity = self.get_service_attribute("activity", {})
        if isinstance(activity, dict):
            activity = activity.get("value", VALVE_ACTIVITY_CLOSED)
        return activity == VALVE_ACTIVITY_CLOSED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "activity": self.get_service_attribute("activity"),
            "duration": self.get_service_attribute("duration"),
            "battery_level": self.get_common_attribute("batteryLevel"),
            "rf_link_level": self.get_common_attribute("rfLinkLevel"),
        }

    async def async_open_valve(self, **kwargs: Any) -> None:
        """Open the valve."""
        duration = kwargs.get("duration", 30)
        await self.coordinator.client.valve_open(self._service_id, duration)

    async def async_close_valve(self, **kwargs: Any) -> None:
        """Close the valve."""
        await self.coordinator.client.valve_close(self._service_id)
