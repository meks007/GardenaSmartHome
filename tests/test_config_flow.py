"""Tests for Gardena Smart System config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.gardena_smart_system.const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_config_flow_user_input_schema():
    """Test that the config flow schema has required fields."""
    from custom_components.gardena_smart_system.config_flow import (
        STEP_USER_DATA_SCHEMA,
    )

    schema = STEP_USER_DATA_SCHEMA.schema
    keys = {str(k) for k in schema}
    assert CONF_CLIENT_ID in keys
    assert CONF_CLIENT_SECRET in keys


@pytest.mark.asyncio
async def test_config_flow_domain():
    """Test that config flow has correct domain."""
    from custom_components.gardena_smart_system.config_flow import (
        GardenaSmartSystemConfigFlow,
    )

    # The domain should match our integration
    assert DOMAIN == "gardena_smart_system"
