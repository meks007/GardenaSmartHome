"""Base entity for Gardena Smart System."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN, SERVICE_COMMON
from ..coordinator import GardenaDataCoordinator


class GardenaEntity(CoordinatorEntity[GardenaDataCoordinator]):
    """Base class for Gardena Smart System entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        device_id: str,
        service_id: str,
        service_type: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._service_id = service_id
        self._service_type = service_type

        device = coordinator.get_device(device_id)
        device_name = "Gardena Device"
        model = None
        serial = None

        if device:
            attrs = device.get("attributes", {})
            device_name = attrs.get("name", {}).get("value", device_name)
            model = attrs.get("modelType", {}).get("value")
            serial = attrs.get("serial", {}).get("value")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="Gardena",
            model=model,
            serial_number=serial,
        )

    def get_service_attribute(
        self, attribute: str, default: Any = None
    ) -> Any:
        """Get attribute value from device service."""
        return self.coordinator.get_service_attribute(
            self._device_id, self._service_type, attribute, default
        )

    def get_common_attribute(
        self, attribute: str, default: Any = None
    ) -> Any:
        """Get attribute value from the COMMON service."""
        return self.coordinator.get_service_attribute(
            self._device_id, SERVICE_COMMON, attribute, default
        )
