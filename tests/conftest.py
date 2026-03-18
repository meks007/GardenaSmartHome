"""Test fixtures for Gardena Smart System."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.gardena_smart_system.api.auth import GardenaAuth
from custom_components.gardena_smart_system.api.client import GardenaClient


@pytest.fixture
def mock_session():
    """Create a mock aiohttp session."""
    session = AsyncMock()
    return session


@pytest.fixture
def mock_auth(mock_session):
    """Create a mock GardenaAuth."""
    auth = GardenaAuth(mock_session, "test_client_id", "test_client_secret")
    return auth


@pytest.fixture
def mock_client(mock_auth, mock_session):
    """Create a mock GardenaClient."""
    return GardenaClient(mock_auth, mock_session)


@pytest.fixture
def sample_location_response():
    """Return sample location API response."""
    return {
        "data": [
            {
                "id": "location-1",
                "type": "LOCATION",
                "attributes": {"name": "My Garden"},
            }
        ]
    }


@pytest.fixture
def sample_location_detail_response():
    """Return sample location detail response with devices.

    Matches real API: DEVICE objects have NO attributes.
    Device name, modelType, serial are in the COMMON service.
    """
    return {
        "data": {
            "id": "location-1",
            "type": "LOCATION",
        },
        "included": [
            {
                "id": "device-1",
                "type": "DEVICE",
                "relationships": {
                    "services": {
                        "data": [
                            {"id": "service-mower-1", "type": "MOWER"},
                            {"id": "service-common-1", "type": "COMMON"},
                        ]
                    }
                },
            },
            {
                "id": "service-mower-1",
                "type": "MOWER",
                "attributes": {
                    "activity": {"value": "OK_CHARGING"},
                    "state": {"value": "OK"},
                    "operatingHours": {"value": 150},
                    "lastErrorCode": {"value": "NO_MESSAGE"},
                },
            },
            {
                "id": "service-common-1",
                "type": "COMMON",
                "attributes": {
                    "name": {"value": "Sileno City"},
                    "modelType": {"value": "GARDENA smart Sileno City"},
                    "serial": {"value": "12345678"},
                    "batteryLevel": {"value": 85},
                    "rfLinkLevel": {"value": 90},
                    "rfLinkState": {"value": "ONLINE"},
                },
            },
            {
                "id": "device-2",
                "type": "DEVICE",
                "relationships": {
                    "services": {
                        "data": [
                            {"id": "service-sensor-1", "type": "SENSOR"},
                            {"id": "service-common-2", "type": "COMMON"},
                        ]
                    }
                },
            },
            {
                "id": "service-sensor-1",
                "type": "SENSOR",
                "attributes": {
                    "soilTemperature": {"value": 18.5},
                    "soilHumidity": {"value": 42},
                    "lightIntensity": {"value": 8500},
                },
            },
            {
                "id": "service-common-2",
                "type": "COMMON",
                "attributes": {
                    "name": {"value": "Soil Sensor"},
                    "modelType": {"value": "GARDENA smart Sensor"},
                    "serial": {"value": "87654321"},
                    "batteryLevel": {"value": 72},
                    "rfLinkLevel": {"value": 80},
                    "rfLinkState": {"value": "ONLINE"},
                },
            },
        ],
    }
