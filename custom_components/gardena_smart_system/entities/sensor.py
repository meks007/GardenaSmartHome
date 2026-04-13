"""Sensor entities for Gardena Smart System."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..const import DOMAIN, SERVICE_COMMON, SERVICE_SENSOR
from ..coordinator import GardenaDataCoordinator
from .base import GardenaEntity

_LOGGER = logging.getLogger(__name__)


@dataclass
class GardenaSensorDescription:
    """Describe a Gardena sensor."""

    key: str
    attribute: str
    name: str
    device_class: SensorDeviceClass | None
    native_unit: str | None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


SOIL_SENSOR_TYPES: list[GardenaSensorDescription] = [
    GardenaSensorDescription(
        key="soil_temperature",
        attribute="soilTemperature",
        name="Soil Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit=UnitOfTemperature.CELSIUS,
    ),
    GardenaSensorDescription(
        key="soil_humidity",
        attribute="soilHumidity",
        name="Soil Humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit=PERCENTAGE,
    ),
    GardenaSensorDescription(
        key="light_intensity",
        attribute="lightIntensity",
        name="Light Intensity",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit="lx",
    ),
    GardenaSensorDescription(
        key="ambient_temperature",
        attribute="ambientTemperature",
        name="Ambient Temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit=UnitOfTemperature.CELSIUS,
    ),
]

BATTERY_SENSOR = GardenaSensorDescription(
    key="battery",
    attribute="batteryLevel",
    name="Battery",
    device_class=SensorDeviceClass.BATTERY,
    native_unit=PERCENTAGE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gardena sensor entities."""
    coordinator: GardenaDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[GardenaSensor] = []
    for device_id, device in coordinator.devices.items():
        services = device.get("services", [])
        service_types = {s["type"] for s in services}

        # Add soil sensors if device has SENSOR service
        if SERVICE_SENSOR in service_types:
            sensor_service = next(
                s for s in services if s["type"] == SERVICE_SENSOR
            )
            service_attrs = sensor_service.get("attributes", {})
            for desc in SOIL_SENSOR_TYPES:
                if desc.attribute in service_attrs:
                    entities.append(
                        GardenaSensor(
                            coordinator=coordinator,
                            device_id=device_id,
                            service_id=sensor_service["id"],
                            description=desc,
                        )
                    )

        # Add battery sensor if device has COMMON service with battery
        if SERVICE_COMMON in service_types:
            common_service = next(
                s for s in services if s["type"] == SERVICE_COMMON
            )
            if "batteryLevel" in common_service.get("attributes", {}):
                entities.append(
                    GardenaSensor(
                        coordinator=coordinator,
                        device_id=device_id,
                        service_id=common_service["id"],
                        description=BATTERY_SENSOR,
                    )
                )

    async_add_entities(entities)


class GardenaSensor(GardenaEntity, SensorEntity):
    """Representation of a Gardena sensor."""

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        device_id: str,
        service_id: str,
        description: GardenaSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        service_type = (
            SERVICE_COMMON if description.key == "battery" else SERVICE_SENSOR
        )
        super().__init__(coordinator, device_id, service_id, service_type)
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_name = description.name
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.native_unit
        self._attr_state_class = description.state_class
        self._description = description

    @property
    def native_value(self) -> float | None:
        """Return the sensor value."""
        value = self.get_service_attribute(self._description.attribute, {})
        if isinstance(value, dict):
            value = value.get("value")
        if value is not None:
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        return None


# Binary sensor setup


async def async_setup_binary_sensors(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Gardena binary sensor entities."""
    coordinator: GardenaDataCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[GardenaBinarySensor] = []

    # Gateway online/offline sensors
    for device_id, device in coordinator.devices.items():
        services = device.get("services", [])
        if any(s["type"] == SERVICE_COMMON for s in services):
            common_service = next(
                s for s in services if s["type"] == SERVICE_COMMON
            )
            entities.append(
                GardenaGatewayBinarySensor(
                    coordinator=coordinator,
                    device_id=device_id,
                    service_id=common_service["id"],
                )
            )

    # WebSocket connected sensors (one per location)
    for location in coordinator.locations:
        entities.append(
            GardenaWebSocketBinarySensor(
                coordinator=coordinator,
                location=location,
            )
        )

    async_add_entities(entities)


class GardenaBinarySensor(GardenaEntity, BinarySensorEntity):
    """Base binary sensor for Gardena."""


class GardenaGatewayBinarySensor(GardenaBinarySensor):
    """Binary sensor for gateway online/offline status."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        device_id: str,
        service_id: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, device_id, service_id, SERVICE_COMMON)
        self._attr_unique_id = f"{device_id}_connectivity"
        self._attr_name = "Connection"

    @property
    def is_on(self) -> bool:
        """Return true if the gateway is online."""
        rf_state = self.get_common_attribute("rfLinkState", {})
        if isinstance(rf_state, dict):
            rf_state = rf_state.get("value", "OFFLINE")
        return rf_state == "ONLINE"


class GardenaWebSocketBinarySensor(BinarySensorEntity):
    """Binary sensor for WebSocket connection status."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: GardenaDataCoordinator,
        location: dict[str, Any],
    ) -> None:
        """Initialize the WebSocket binary sensor."""
        self._coordinator = coordinator
        self._location_id = location["id"]
        location_name = location.get("attributes", {}).get(
            "name", self._location_id
        )
        self._attr_unique_id = f"ws_{self._location_id}"
        self._attr_name = f"WebSocket {location_name}"
        self._attr_device_info = None  # No device association

    @property
    def is_on(self) -> bool:
        """Return true if the WebSocket is connected."""
        return self._coordinator.is_ws_connected(self._location_id)

    @property
    def available(self) -> bool:
        """Return True - this sensor is always available."""
        return True
