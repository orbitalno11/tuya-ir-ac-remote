"""Tests for the config flow and Learn Command options flow."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_ir_ac.const import DOMAIN
from custom_components.tuya_ir_ac.tuya_cloud import (
    TuyaCloudAuthError,
    TuyaCloudDevice,
    TuyaCloudError,
)
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

CLOUD_INPUT = {
    "access_id": "myaccessid",
    "access_secret": "myaccesssecret",
    "api_region": "us",
}

CHECK_CONNECTION_TARGET = "custom_components.tuya_ir_ac.config_flow.TuyaIrHub.async_check_connection"
LIST_DEVICES_TARGET = (
    "custom_components.tuya_ir_ac.config_flow.TuyaCloudClient.async_list_devices"
)


async def _select_menu(hass, next_step_id):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": next_step_id}
    )


async def _drive_to_create_entry(hass, user_input=None):
    # The whole flow -- including the real async_setup_entry that HA
    # triggers automatically once the entry is created -- must stay inside
    # the patch context, otherwise post-creation setup hits a real socket.
    with patch(CHECK_CONNECTION_TARGET, return_value=None):
        result = await _select_menu(hass, "manual")
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "manual"

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


async def test_manual_step_invalid_auth_shows_error(hass):
    result = await _select_menu(hass, "manual")
    with patch(CHECK_CONNECTION_TARGET, side_effect=TuyaIrAuthError("bad key")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_manual_step_cannot_connect_shows_error(hass):
    result = await _select_menu(hass, "manual")
    with patch(CHECK_CONNECTION_TARGET, side_effect=TuyaIrConnectionError("down")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "manual"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_entry_aborts(hass):
    first = await _drive_to_create_entry(hass)
    assert first["type"] == FlowResultType.CREATE_ENTRY
    result = await _drive_to_create_entry(hass)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


HUB_DEVICE = TuyaCloudDevice(
    device_id="hub123",
    name="Living Room IR Hub",
    local_key="hublocalkey==",
    gateway_id=None,
    category="wnykq",
    product_name="Universal Smart IR Remote",
)
SUBDEVICE = TuyaCloudDevice(
    device_id="sub456",
    name="Living Room AC",
    local_key="subkey==",
    gateway_id="hub123",
    category="infrared_ac",
    product_name="Panasonic AC Remote",
)


async def test_cloud_step_invalid_auth_shows_error(hass):
    result = await _select_menu(hass, "cloud")
    with patch(LIST_DEVICES_TARGET, side_effect=TuyaCloudAuthError("bad creds")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cloud_step_cannot_connect_shows_error(hass):
    result = await _select_menu(hass, "cloud")
    with patch(LIST_DEVICES_TARGET, side_effect=TuyaCloudError("down")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_cloud_step_no_devices_found_shows_error(hass):
    result = await _select_menu(hass, "cloud")
    with patch(LIST_DEVICES_TARGET, return_value=[]):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CLOUD_INPUT
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    assert result["errors"] == {"base": "no_devices_found"}


async def test_cloud_flow_hub_only_creates_entry(hass):
    with patch(CHECK_CONNECTION_TARGET, return_value=None):
        result = await _select_menu(hass, "cloud")
        with patch(LIST_DEVICES_TARGET, return_value=[HUB_DEVICE]):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], CLOUD_INPUT
            )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cloud_hub"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device_id": "hub123"}
        )
        # no sub-devices for this hub -> straight to cloud_host
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cloud_host"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Living Room IR Hub", "host": "192.168.1.60", "protocol_version": "3.3"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "brand"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"brand": "carrier"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"variant": "generic"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["device_id"] == "hub123"
    assert result["data"]["local_key"] == "hublocalkey=="
    assert result["data"]["host"] == "192.168.1.60"
    assert result["data"]["access_id"] == "myaccessid"
    assert result["data"]["access_secret"] == "myaccesssecret"
    assert result["data"]["api_region"] == "us"


async def test_cloud_flow_with_subdevice_prefills_name_and_brand(hass):
    with patch(CHECK_CONNECTION_TARGET, return_value=None):
        result = await _select_menu(hass, "cloud")
        with patch(LIST_DEVICES_TARGET, return_value=[HUB_DEVICE, SUBDEVICE]):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], CLOUD_INPUT
            )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"device_id": "hub123"}
        )
        # this hub has a matching sub-device -> offered before cloud_host
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cloud_subdevice"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"subdevice": "sub456"}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "cloud_host"
        # name field should default to the sub-device's cloud name
        assert result["data_schema"]({"host": "192.168.1.60", "protocol_version": "3.3"})[
            "name"
        ] == "Living Room AC"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Living Room AC", "host": "192.168.1.60", "protocol_version": "3.3"},
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "brand"
        # brand should default to panasonic since the sub-device's product
        # name mentioned it
        assert result["data_schema"]({})["brand"] == "panasonic"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"brand": "panasonic"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"variant": "generic"}
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # device_id/local_key must always be the physical hub's, never the sub-device's
    assert result["data"]["device_id"] == "hub123"
    assert result["data"]["local_key"] == "hublocalkey=="


async def test_cloud_step_prefills_saved_credentials_from_existing_entry(hass):
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={**USER_INPUT, **CLOUD_INPUT},
        title="Living Room AC",
    )
    existing.add_to_hass(hass)

    result = await _select_menu(hass, "cloud")
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "cloud"
    # defaults should be pre-filled from the existing entry's saved creds
    assert result["data_schema"]({})["access_id"] == "myaccessid"
    assert result["data_schema"]({})["access_secret"] == "myaccesssecret"
    assert result["data_schema"]({})["api_region"] == "us"


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
