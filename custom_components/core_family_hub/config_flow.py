"""Config flow for CORE Family Hub."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import __version__ as HOME_ASSISTANT_VERSION
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .bridge_client import CoreBridgeAuthenticationError, CoreBridgeClient, CoreBridgeError
from .const import (
    CONF_BRIDGE_URL,
    CONF_CONNECTION_ID,
    CONF_CONNECTOR_SECRET,
    CONF_PAIRING_CODE,
    CONF_REALTIME_KEY,
    CONF_REALTIME_URL,
    CONF_TENANT_ID,
    CONF_WAKE_TOPIC,
    DEFAULT_BRIDGE_URL,
    DOMAIN,
    PROTOCOL_VERSION,
)


def _valid_bridge_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise vol.Invalid("CORE bridge URL must use HTTPS")
    return normalized


class CoreFamilyHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Pair a Home Assistant installation to one CORE household."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                bridge_url = _valid_bridge_url(str(user_input[CONF_BRIDGE_URL]))
            except (KeyError, TypeError, ValueError, vol.Invalid):
                errors[CONF_BRIDGE_URL] = "invalid_url"
            else:
                client = CoreBridgeClient(async_get_clientsession(self.hass), bridge_url)
                try:
                    paired = await client.async_pair(
                        str(user_input[CONF_PAIRING_CODE]).strip(),
                        PROTOCOL_VERSION,
                        HOME_ASSISTANT_VERSION,
                    )
                    connection_id = str(paired["connectionId"])
                    await self.async_set_unique_id(connection_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=str(paired.get("displayName") or "CORE Family Hub"),
                        data={
                            CONF_BRIDGE_URL: bridge_url,
                            CONF_CONNECTION_ID: connection_id,
                            CONF_CONNECTOR_SECRET: str(paired["connectorSecret"]),
                            CONF_TENANT_ID: str(paired["tenantId"]),
                            CONF_REALTIME_URL: str(paired["realtimeUrl"]),
                            CONF_REALTIME_KEY: str(paired["realtimeKey"]),
                            CONF_WAKE_TOPIC: str(paired["wakeTopic"]),
                        },
                    )
                except CoreBridgeAuthenticationError:
                    errors["base"] = "invalid_auth"
                except (CoreBridgeError, KeyError, TypeError, ValueError):
                    errors["base"] = "cannot_connect"

        # Home Assistant serializes this schema before sending it to the frontend.
        # Keep field validators serializable and perform strict HTTPS validation above.
        schema = vol.Schema(
            {
                vol.Required(CONF_BRIDGE_URL, default=DEFAULT_BRIDGE_URL): str,
                vol.Required(CONF_PAIRING_CODE): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
