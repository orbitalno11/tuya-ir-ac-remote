"""Tests for the config flow and Learn Command options flow."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_ir_ac.const import DOMAIN
from custom_components.tuya_ir_ac.tuya_ir import (
    TuyaIrAuthError,
    TuyaIrConnectionError,
    TuyaIrTimeoutError,
)

USER_INPUT = {
    "name": "Living Room AC",
    "host": "192.168.1.50",
    "device_id": "abc123",
    "local_key": "secretkey",
    "protocol_version": "3.3",
}

CHECK_CONNECTION_TARGET = "custom_components.tuya_ir_ac.config_flow.TuyaIrHub.async_check_connection"


async def _drive_to_create_entry(hass, user_input=None):
    # The whole flow -- including the real async_setup_entry that HA
    # triggers automatically once the entry is created -- must stay inside
    # the patch context, otherwise post-creation setup hits a real socket.
    with patch(CHECK_CONNECTION_TARGET, return_value=None):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input or USER_INPUT
        )
        if result["type"] == FlowResultType.ABORT:
            return result
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "brand"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"brand": "panasonic"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "variant"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"variant": "generic"}
        )
    return result


async def test_full_flow_creates_entry(hass):
    result = await _drive_to_create_entry(hass)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Living Room AC"
    assert result["data"]["brand"] == "panasonic"
    assert result["data"]["variant"] == "generic"
    assert result["data"]["device_id"] == "abc123"


async def test_user_step_invalid_auth_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(CHECK_CONNECTION_TARGET, side_effect=TuyaIrAuthError("bad key")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_step_cannot_connect_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(CHECK_CONNECTION_TARGET, side_effect=TuyaIrConnectionError("down")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_entry_aborts(hass):
    first = await _drive_to_create_entry(hass)
    assert first["type"] == FlowResultType.CREATE_ENTRY
    result = await _drive_to_create_entry(hass)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_no_keys_selected_aborts(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, title="Living Room AC")
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": AsyncMock(),
        "store": AsyncMock(),
        "learned_codes": {},
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keys": []}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_keys_selected"


async def test_options_flow_learns_and_saves_codes(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, title="Living Room AC")
    entry.add_to_hass(hass)
    hub = AsyncMock()
    hub.async_learn_code.return_value = "LEARNEDCODE=="
    store = AsyncMock()
    learned_codes: dict[str, str] = {}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "store": store,
        "learned_codes": learned_codes,
    }
    hass.config_entries.async_reload = AsyncMock(return_value=True)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keys": ["off", "cool_24_auto_off"]}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "capture"
    assert result["description_placeholders"]["state_key"] == "off"

    # capture "off"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["description_placeholders"]["state_key"] == "cool_24_auto_off"

    # capture "cool_24_auto_off" -> flow completes
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert learned_codes == {"off": "LEARNEDCODE==", "cool_24_auto_off": "LEARNEDCODE=="}
    store.async_save.assert_awaited_once_with(learned_codes)
    hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)


async def test_options_flow_learn_timeout_shows_retry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=USER_INPUT, title="Living Room AC")
    entry.add_to_hass(hass)
    hub = AsyncMock()
    hub.async_learn_code.side_effect = TuyaIrTimeoutError("no button pressed")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "hub": hub,
        "store": AsyncMock(),
        "learned_codes": {},
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keys": ["off"]}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "capture"
    assert result["errors"] == {"base": "learn_timeout"}
