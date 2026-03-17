"""Data update coordinator for Gardena Smart System."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api.auth import GardenaAuth, GardenaAuthError
from .api.client import GardenaApiError, GardenaClient
from .api.websocket import GardenaWebSocket
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DOMAIN,
    SERVICE_COMMON,
    SERVICE_DEVICE,
    SERVICE_MOWER,
    SERVICE_SENSOR,
    SERVICE_VALVE,
    SERVICE_VALVE_SET,
)

_LOGGER = logging.getLogger(__name__)


class GardenaDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate data from Gardena Smart System API.

    Uses WebSocket for real-time updates with REST API fallback.
    Addresses issues #303 (reconnect), #306 (device lookup), #313 (connector closed).
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )
        self._entry = entry
        self._session: aiohttp.ClientSession | None = None
        self._auth: GardenaAuth | None = None
        self._client: GardenaClient | None = None
        self._websockets: dict[str, GardenaWebSocket] = {}
        self._devices: dict[str, dict[str, Any]] = {}
        self._locations: list[dict[str, Any]] = []
        self._ws_connected: dict[str, bool] = {}

    @property
    def auth(self) -> GardenaAuth:
        """Return the auth handler."""
        assert self._auth is not None
        return self._auth

    @property
    def client(self) -> GardenaClient:
        """Return the API client."""
        assert self._client is not None
        return self._client

    @property
    def devices(self) -> dict[str, dict[str, Any]]:
        """Return all known devices."""
        return self._devices

    @property
    def locations(self) -> list[dict[str, Any]]:
        """Return all locations."""
        return self._locations

    def is_ws_connected(self, location_id: str | None = None) -> bool:
        """Check if WebSocket is connected for a location or any location."""
        if location_id:
            return self._ws_connected.get(location_id, False)
        return any(self._ws_connected.values())

    def get_device(self, device_id: str) -> dict[str, Any] | None:
        """Get a device by its ID.

        This addresses issue #306 - proper device lookup without
        'get_device_by_id' attribute errors.
        """
        return self._devices.get(device_id)

    def get_services_by_type(
        self, device_id: str, service_type: str
    ) -> list[dict[str, Any]]:
        """Get all services of a given type for a device."""
        device = self._devices.get(device_id)
        if not device:
            return []
        return [
            s
            for s in device.get("services", [])
            if s.get("type") == service_type
        ]

    def get_service_attribute(
        self,
        device_id: str,
        service_type: str,
        attribute: str,
        default: Any = None,
    ) -> Any:
        """Get an attribute value from a device service."""
        services = self.get_services_by_type(device_id, service_type)
        if not services:
            return default
        attrs = services[0].get("attributes", {})
        attr_data = attrs.get(attribute, {})
        return attr_data.get("value", default)

    async def async_setup(self) -> None:
        """Set up the coordinator - authenticate and fetch initial data."""
        self._session = async_get_clientsession(self.hass)
        self._auth = GardenaAuth(
            self._session,
            self._entry.data[CONF_CLIENT_ID],
            self._entry.data[CONF_CLIENT_SECRET],
        )
        self._client = GardenaClient(self._auth, self._session)

        # Authenticate
        await self._auth.authenticate()

        # Fetch locations
        self._locations = await self._client.get_locations()

        # Fetch devices for all locations
        for location in self._locations:
            location_id = location["id"]
            await self._fetch_location_devices(location_id)

        # Start WebSocket connections for all locations
        for location in self._locations:
            location_id = location["id"]
            await self._start_websocket(location_id)

    async def _fetch_location_devices(self, location_id: str) -> None:
        """Fetch all devices for a location."""
        try:
            location_data = await self._client.get_location(location_id)
            included = location_data.get("included", [])
            self._process_included_data(included)
        except (GardenaApiError, GardenaAuthError) as err:
            _LOGGER.error("Error fetching devices for location %s: %s", location_id, err)

    def _process_included_data(self, included: list[dict[str, Any]]) -> None:
        """Process included data from API response into device structure."""
        # First pass: collect devices
        devices: dict[str, dict[str, Any]] = {}
        services: list[dict[str, Any]] = []

        for item in included:
            item_type = item.get("type", "")
            item_id = item.get("id", "")

            if item_type == "DEVICE":
                devices[item_id] = {
                    "id": item_id,
                    "type": item_type,
                    "attributes": item.get("attributes", {}),
                    "relationships": item.get("relationships", {}),
                    "services": [],
                }
            else:
                services.append(item)

        # Second pass: attach services to devices
        for service in services:
            service_id = service.get("id", "")
            # Find which device this service belongs to
            for device_id, device in devices.items():
                device_services = (
                    device.get("relationships", {})
                    .get("services", {})
                    .get("data", [])
                )
                for ds in device_services:
                    if ds.get("id") == service_id:
                        device["services"].append(
                            {
                                "id": service_id,
                                "type": service.get("type", ""),
                                "attributes": service.get("attributes", {}),
                            }
                        )
                        break

        # Merge into existing devices
        self._devices.update(devices)

    async def _start_websocket(self, location_id: str) -> None:
        """Start a WebSocket connection for a location."""
        if self._session is None or self._auth is None or self._client is None:
            return

        @callback
        def on_message(data: dict[str, Any]) -> None:
            """Handle incoming WebSocket message."""
            self._handle_ws_message(data)

        @callback
        def on_connected() -> None:
            """Handle WebSocket connected."""
            self._ws_connected[location_id] = True
            _LOGGER.info("WebSocket connected for location %s", location_id)
            self.async_set_updated_data(self._devices)

        @callback
        def on_disconnected() -> None:
            """Handle WebSocket disconnected."""
            self._ws_connected[location_id] = False
            _LOGGER.warning("WebSocket disconnected for location %s", location_id)
            self.async_set_updated_data(self._devices)

        ws = GardenaWebSocket(
            auth=self._auth,
            client=self._client,
            session=self._session,
            location_id=location_id,
            on_message=on_message,
            on_connected=on_connected,
            on_disconnected=on_disconnected,
        )
        self._websockets[location_id] = ws
        await ws.connect()

    @callback
    def _handle_ws_message(self, data: dict[str, Any]) -> None:
        """Handle a WebSocket message and update device state."""
        msg_type = data.get("type", "")

        if msg_type in (
            SERVICE_MOWER,
            SERVICE_VALVE,
            SERVICE_VALVE_SET,
            SERVICE_SENSOR,
            SERVICE_COMMON,
            SERVICE_DEVICE,
        ):
            service_id = data.get("id", "")
            attributes = data.get("attributes", {})

            # Update the matching service in our device store
            for device in self._devices.values():
                for service in device.get("services", []):
                    if service["id"] == service_id:
                        service["attributes"].update(attributes)
                        _LOGGER.debug(
                            "Updated service %s (%s)", service_id, msg_type
                        )
                        self.async_set_updated_data(self._devices)
                        return

            _LOGGER.debug(
                "Received update for unknown service %s (%s)",
                service_id,
                msg_type,
            )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API (fallback when WebSocket is not connected)."""
        for location in self._locations:
            location_id = location["id"]
            if not self._ws_connected.get(location_id, False):
                await self._fetch_location_devices(location_id)
        return self._devices

    async def async_shutdown(self) -> None:
        """Shut down coordinator and close connections.

        Addresses issue #313 - connector is closed errors by
        properly cleaning up WebSocket connections.
        """
        for location_id, ws in self._websockets.items():
            _LOGGER.debug("Disconnecting WebSocket for location %s", location_id)
            await ws.disconnect()
        self._websockets.clear()
        self._ws_connected.clear()

        if self._auth:
            await self._auth.close()
