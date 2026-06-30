"""The Tuya IR AC Remote integration.

Turns a Tuya local-network IR hub into a climate entity for a Panasonic or
Carrier air conditioner. Each config entry represents one AC unit; see
config_flow.py for why hub fields (host/device_id/local_key) are stored per
entry rather than shared across a separate "hub" entry.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.storage import Store

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    DOMAIN,
    STORAGE_KEY_TEMPLATE,
    STORAGE_VERSION,
)
from .tuya_ir import TuyaIrError, TuyaIrHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CLIMATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Tuya IR AC Remote config entry."""
    hub = TuyaIrHub(
        hass,
        host=entry.data[CONF_HOST],
        device_id=entry.data[CONF_DEVICE_ID],
        local_key=entry.data[CONF_LOCAL_KEY],
        version=entry.data[CONF_PROTOCOL_VERSION],
    )

    try:
        await hub.async_check_connection()
    except TuyaIrError as err:
        raise ConfigEntryNotReady(
            f"Could not connect to the Tuya IR hub at {entry.data[CONF_HOST]}: {err}"
        ) from err

    store: Store = Store(
        hass, STORAGE_VERSION, STORAGE_KEY_TEMPLATE.format(entry_id=entry.entry_id)
    )
    learned_codes: dict[str, str] = await store.async_load() or {}

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "store": store,
        "learned_codes": learned_codes,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Tuya IR AC Remote config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
