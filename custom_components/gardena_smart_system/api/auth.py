"""Authentication handler for Gardena Smart System API."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp

from ..const import AUTH_URL, TOKEN_REFRESH_BUFFER

_LOGGER = logging.getLogger(__name__)


class GardenaAuth:
    """Handle authentication with Husqvarna/Gardena OAuth2."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str,
        client_secret: str,
    ) -> None:
        """Initialize auth handler."""
        self._session = session
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expiry: float = 0
        self._refresh_lock = asyncio.Lock()

    @property
    def client_id(self) -> str:
        """Return the client ID (used as X-Api-Key)."""
        return self._client_id

    @property
    def token(self) -> str | None:
        """Return the current access token."""
        return self._token

    @property
    def is_token_valid(self) -> bool:
        """Check if the current token is still valid."""
        return self._token is not None and time.time() < self._token_expiry

    @property
    def needs_refresh(self) -> bool:
        """Check if token should be refreshed (within buffer period)."""
        return (
            self._token is None
            or time.time() >= self._token_expiry - TOKEN_REFRESH_BUFFER
        )

    async def authenticate(self) -> str:
        """Authenticate and return access token.

        Uses a lock to prevent concurrent token requests.
        """
        async with self._refresh_lock:
            if self.is_token_valid and not self.needs_refresh:
                return self._token  # type: ignore[return-value]

            return await self._request_token()

    async def _request_token(self) -> str:
        """Request a new access token from the OAuth2 endpoint."""
        data = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        try:
            async with self._session.post(AUTH_URL, data=data) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise GardenaAuthError(
                        f"Authentication failed ({resp.status}): {text}"
                    )

                result: dict[str, Any] = await resp.json()
                self._token = result["access_token"]
                expires_in = result.get("expires_in", 3600)
                self._token_expiry = time.time() + expires_in

                _LOGGER.debug(
                    "Token acquired, expires in %d seconds", expires_in
                )
                return self._token  # type: ignore[return-value]

        except aiohttp.ClientError as err:
            raise GardenaAuthError(f"Connection error during auth: {err}") from err

    async def ensure_valid_token(self) -> str:
        """Ensure we have a valid token, refreshing if needed.

        This is called proactively before token expiry to avoid
        interrupting WebSocket connections.
        """
        if self.needs_refresh:
            _LOGGER.debug("Token needs refresh, requesting new token")
            return await self.authenticate()
        return self._token  # type: ignore[return-value]

    def get_headers(self) -> dict[str, str]:
        """Return authorization headers for API requests."""
        return {
            "Authorization": f"Bearer {self._token}",
            "X-Api-Key": self._client_id,
            "Content-Type": "application/vnd.api+json",
        }

    async def close(self) -> None:
        """Clean up resources."""
        self._token = None
        self._token_expiry = 0


class GardenaAuthError(Exception):
    """Exception for authentication errors."""
