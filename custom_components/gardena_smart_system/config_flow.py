"""Config flow for Gardena Smart System integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.auth import GardenaAuth, GardenaAuthError
from .api.client import GardenaApiError, GardenaClient
from .const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CLIENT_ID): str,
        vol.Required(CONF_CLIENT_SECRET): str,
    }
)


class GardenaSmartSystemConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Gardena Smart System."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client_id = user_input[CONF_CLIENT_ID]
            client_secret = user_input[CONF_CLIENT_SECRET]

            # Check for existing entry with same client_id
            await self.async_set_unique_id(client_id)
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            auth = GardenaAuth(session, client_id, client_secret)

            try:
                await auth.authenticate()
            except GardenaAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                # Verify we can access locations
                client = GardenaClient(auth, session)
                try:
                    locations = await client.get_locations()
                except GardenaApiError:
                    errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error fetching locations")
                    errors["base"] = "unknown"
                else:
                    if not locations:
                        errors["base"] = "no_locations"
                    else:
                        return self.async_create_entry(
                            title="Gardena Smart System",
                            data=user_input,
                        )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
