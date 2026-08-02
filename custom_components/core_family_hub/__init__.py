"""CORE Family Hub companion integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .bridge_client import CoreBridgeAuthenticationError, CoreBridgeClient, CoreBridgeError
from .const import (
    CONF_BRIDGE_URL,
    CONF_CONNECTION_ID,
    CONF_CONNECTOR_SECRET,
    CONF_REALTIME_KEY,
    CONF_REALTIME_URL,
    CONF_WAKE_TOPIC,
    DOMAIN,
)
from .coordinator import CoreBridgeRuntime


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Start a paired CORE companion."""
    client = CoreBridgeClient(
        async_get_clientsession(hass),
        entry.data[CONF_BRIDGE_URL],
        entry.data[CONF_CONNECTION_ID],
        entry.data[CONF_CONNECTOR_SECRET],
        entry.data[CONF_REALTIME_URL],
        entry.data[CONF_REALTIME_KEY],
        entry.data[CONF_WAKE_TOPIC],
    )
    runtime = CoreBridgeRuntime(hass, entry.entry_id, client)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime
    try:
        await runtime.async_start()
    except CoreBridgeAuthenticationError as err:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryAuthFailed(str(err)) from err
    except CoreBridgeError as err:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise ConfigEntryNotReady(str(err)) from err
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop the companion and all outbound tasks."""
    runtime: CoreBridgeRuntime | None = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime:
        await runtime.async_stop()
    return True
