"""Tests for Gardena Smart System coordinator."""

from __future__ import annotations

import pytest

from custom_components.gardena_smart_system.coordinator import GardenaDataCoordinator


class TestDeviceProcessing:
    """Test device data processing logic."""

    def test_process_included_data(self, sample_location_detail_response):
        """Test processing API response into device structure."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._devices = {}

        included = sample_location_detail_response["included"]
        coordinator._process_included_data(included)

        # Should have 2 devices
        assert len(coordinator._devices) == 2
        assert "device-1" in coordinator._devices
        assert "device-2" in coordinator._devices

    def test_process_included_data_services_attached(
        self, sample_location_detail_response
    ):
        """Test that services are correctly attached to devices."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._devices = {}

        included = sample_location_detail_response["included"]
        coordinator._process_included_data(included)

        device1 = coordinator._devices["device-1"]
        service_types = {s["type"] for s in device1["services"]}
        assert "MOWER" in service_types
        assert "COMMON" in service_types

    def test_get_device(self, sample_location_detail_response):
        """Test device lookup by ID (addresses issue #306)."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._devices = {}

        included = sample_location_detail_response["included"]
        coordinator._process_included_data(included)

        device = coordinator.get_device("device-1")
        assert device is not None
        assert device["id"] == "device-1"

        # Non-existent device
        assert coordinator.get_device("nonexistent") is None

    def test_get_service_attribute(self, sample_location_detail_response):
        """Test getting service attribute values."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._devices = {}

        included = sample_location_detail_response["included"]
        coordinator._process_included_data(included)

        activity = coordinator.get_service_attribute(
            "device-1", "MOWER", "activity"
        )
        assert activity == "OK_CHARGING"

    def test_get_service_attribute_default(
        self, sample_location_detail_response
    ):
        """Test default value for missing attribute."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._devices = {}

        included = sample_location_detail_response["included"]
        coordinator._process_included_data(included)

        result = coordinator.get_service_attribute(
            "device-1", "MOWER", "nonexistent", "default_val"
        )
        assert result == "default_val"

    def test_get_services_by_type(self, sample_location_detail_response):
        """Test getting services filtered by type."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._devices = {}

        included = sample_location_detail_response["included"]
        coordinator._process_included_data(included)

        mower_services = coordinator.get_services_by_type("device-1", "MOWER")
        assert len(mower_services) == 1
        assert mower_services[0]["type"] == "MOWER"

    def test_ws_connected_tracking(self):
        """Test WebSocket connection tracking."""
        coordinator = GardenaDataCoordinator.__new__(GardenaDataCoordinator)
        coordinator._ws_connected = {}

        assert coordinator.is_ws_connected("loc-1") is False
        assert coordinator.is_ws_connected() is False

        coordinator._ws_connected["loc-1"] = True
        assert coordinator.is_ws_connected("loc-1") is True
        assert coordinator.is_ws_connected() is True
