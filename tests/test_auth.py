"""Tests for Gardena Smart System authentication."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.gardena_smart_system.api.auth import (
    GardenaAuth,
    GardenaAuthError,
)
from custom_components.gardena_smart_system.const import TOKEN_REFRESH_BUFFER


@pytest.fixture
def auth():
    """Create a GardenaAuth instance with mock session."""
    session = AsyncMock()
    return GardenaAuth(session, "test_client_id", "test_secret")


@pytest.mark.asyncio
async def test_authenticate_success(auth):
    """Test successful authentication."""
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(
        return_value={"access_token": "test_token", "expires_in": 3600}
    )

    auth._session.post = MagicMock(return_value=AsyncContextManager(mock_resp))

    token = await auth.authenticate()

    assert token == "test_token"
    assert auth.is_token_valid
    assert auth.token == "test_token"


@pytest.mark.asyncio
async def test_authenticate_failure(auth):
    """Test authentication failure."""
    mock_resp = AsyncMock()
    mock_resp.status = 401
    mock_resp.text = AsyncMock(return_value="Unauthorized")

    auth._session.post = MagicMock(return_value=AsyncContextManager(mock_resp))

    with pytest.raises(GardenaAuthError, match="Authentication failed"):
        await auth.authenticate()


@pytest.mark.asyncio
async def test_token_needs_refresh(auth):
    """Test that needs_refresh returns True when token is about to expire."""
    auth._token = "test_token"
    auth._token_expiry = time.time() + (TOKEN_REFRESH_BUFFER - 10)

    assert auth.needs_refresh is True


@pytest.mark.asyncio
async def test_token_valid(auth):
    """Test that is_token_valid returns True for fresh token."""
    auth._token = "test_token"
    auth._token_expiry = time.time() + 3600

    assert auth.is_token_valid is True
    assert auth.needs_refresh is False


def test_get_headers(auth):
    """Test authorization headers."""
    auth._token = "test_token"
    headers = auth.get_headers()

    assert headers["Authorization"] == "Bearer test_token"
    assert headers["X-Api-Key"] == "test_client_id"
    assert "Content-Type" in headers


def test_client_id_property(auth):
    """Test client_id property."""
    assert auth.client_id == "test_client_id"


class AsyncContextManager:
    """Helper to mock async context managers."""

    def __init__(self, return_value):
        self.return_value = return_value

    async def __aenter__(self):
        return self.return_value

    async def __aexit__(self, *args):
        pass
