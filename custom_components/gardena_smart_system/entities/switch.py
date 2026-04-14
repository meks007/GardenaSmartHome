"""Switch entity for Gardena Smart Power Socket."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import (
    DOMAIN,
    POWER_SOCKET_ACTIVITY_OFF,
    SERVICE_POWER_SOCKET,
)
from ..coordinator import GardenaDataCoordinator
from .base import GardenaEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gardena power socket switch entities."""
    coordinator: GardenaDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[GardenaPowerSocket] = []
    for device_id, device in coordinator.devices.items():
        for service in device.get("services", []):
            if service["type"] == SERVICE_POWER_SOCKET:
                entities.append(
                    GardenaPowerSocket(
                        coordinator=coordinator,
                        device_id=device_id,
                        service_id=service["id"],
                    )
                )

    async_add_entities(entities)


class GardenaPowerSocket(GardenaEntity, SwitchEntity):
    """Representation of a Gardena Smart Power Socket."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        device_id: str,
        service_id: str,
    ) -> None:
        """Initialize the power socket entity."""
        super().__init__(coordinator, device_id, service_id, SERVICE_POWER_SOCKET)
        self._attr_unique_id = f"{device_id}_{service_id}_switch"
        self._attr_name = "Power Socket"

    @property
    def is_on(self) -> bool:
        """Return true if the socket is on."""
        activity = self.get_service_attribute("activity", POWER_SOCKET_ACTIVITY_OFF)
        if isinstance(activity, dict):
            activity = activity.get("value", POWER_SOCKET_ACTIVITY_OFF)
        return activity != POWER_SOCKET_ACTIVITY_OFF

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "activity": self.get_service_attribute("activity"),
            "duration": self.get_service_attribute("duration"),
            "rf_link_level": self.get_common_attribute("rfLinkLevel"),
            "battery_level": self.get_common_attribute("batteryLevel"),
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the power socket."""
        duration = kwargs.get("duration")
        await self.coordinator.client.power_socket_on(self._service_id, duration)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the power socket."""
        await self.coordinator.client.power_socket_off(self._service_id)
