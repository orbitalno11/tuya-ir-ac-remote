"""Integration-level smoke tests for async_setup_entry/async_unload_entry."""
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_ir_ac.const import DOMAIN
from custom_components.tuya_ir_ac.tuya_ir import TuyaIrConnectionError

ENTRY_DATA = {
    "name": "Living Room AC",
    "host": "192.168.1.50",
    "device_id": "abc123",
    "local_key": "secretkey",
    "protocol_version": "3.3",
    "brand": "panasonic",
    "variant": "generic",
}

CHECK_CONNECTION_TARGET = (
    "custom_components.tuya_ir_ac.tuya_ir.TuyaIrHub.async_check_connection"
)


async def test_setup_entry_success_creates_climate_entity(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Living Room AC")
    entry.add_to_hass(hass)

    with patch(CHECK_CONNECTION_TARGET, return_value=None):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert DOMAIN in hass.data
    assert entry.entry_id in hass.data[DOMAIN]
    assert "hub" in hass.data[DOMAIN][entry.entry_id]

    state = hass.states.get("climate.living_room_ac")
    assert state is not None


async def test_setup_entry_connection_failure_retries(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Living Room AC")
    entry.add_to_hass(hass)

    with patch(CHECK_CONNECTION_TARGET, side_effect=TuyaIrConnectionError("down")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry_cleans_up_hass_data(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, title="Living Room AC")
    entry.add_to_hass(hass)

    with patch(CHECK_CONNECTION_TARGET, return_value=None):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert entry.entry_id not in hass.data[DOMAIN]
