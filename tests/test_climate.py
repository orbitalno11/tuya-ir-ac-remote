"""Unit tests for the TuyaIrClimateEntity."""
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_ir_ac.climate import TuyaIrClimateEntity
from custom_components.tuya_ir_ac.codes.schema import CodeTable
from custom_components.tuya_ir_ac.const import DOMAIN
from custom_components.tuya_ir_ac.tuya_ir import TuyaIrConnectionError

FAKE_TABLE = CodeTable(
    brand="panasonic",
    variant="test",
    protocol="state",
    codes={
        "off": "OFFCODE",
        "cool_24_auto_off": "COOL24CODE",
        "cool_22_low_on": "COOL22LOWONCODE",
        "heat_22_auto_off": "HEAT22CODE",
    },
)


def _make_entity(hass, learned_codes=None, hub=None):
    entry = MockConfigEntry(domain=DOMAIN, data={"name": "Living Room AC"}, title="Living Room AC")
    entry.add_to_hass(hass)
    hub = hub or AsyncMock()
    entity = TuyaIrClimateEntity(entry, hub, FAKE_TABLE, learned_codes or {})
    entity.hass = hass
    entity.entity_id = "climate.living_room_ac"
    return entity, hub


async def test_hvac_modes_derived_from_code_table(hass):
    entity, _ = _make_entity(hass)
    assert HVACMode.OFF in entity.hvac_modes
    assert HVACMode.COOL in entity.hvac_modes
    assert HVACMode.HEAT in entity.hvac_modes
    # no "dry"/"fan_only"/"auto" codes in FAKE_TABLE -> not advertised
    assert HVACMode.DRY not in entity.hvac_modes
    assert HVACMode.FAN_ONLY not in entity.hvac_modes
    assert HVACMode.AUTO not in entity.hvac_modes


async def test_initial_optimistic_state(hass):
    entity, _ = _make_entity(hass)
    assert entity.hvac_mode == HVACMode.OFF
    assert entity.target_temperature == FAKE_TABLE.min_temp
    assert entity.fan_mode == FAKE_TABLE.fan_modes[0]
    assert entity.swing_mode == FAKE_TABLE.swing_modes[0]


async def test_set_hvac_mode_sends_matching_code(hass):
    entity, hub = _make_entity(hass)
    entity._attr_target_temperature = 24
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    await entity.async_set_hvac_mode(HVACMode.COOL)
    hub.async_send_code.assert_awaited_once_with("COOL24CODE")
    assert entity.hvac_mode == HVACMode.COOL


async def test_set_temperature_sends_matching_code(hass):
    entity, hub = _make_entity(hass)
    entity._attr_hvac_mode = HVACMode.COOL
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    await entity.async_set_temperature(temperature=24)
    hub.async_send_code.assert_awaited_once_with("COOL24CODE")
    assert entity.target_temperature == 24


async def test_set_fan_and_swing_mode_send_matching_code(hass):
    entity, hub = _make_entity(hass)
    entity._attr_hvac_mode = HVACMode.COOL
    entity._attr_target_temperature = 22
    entity._attr_swing_mode = "on"
    await entity.async_set_fan_mode("low")
    assert hub.async_send_code.await_args_list[-1].args == ("COOL22LOWONCODE",)


async def test_turn_off_sends_off_code(hass):
    entity, hub = _make_entity(hass)
    entity._attr_hvac_mode = HVACMode.COOL
    await entity.async_set_hvac_mode(HVACMode.OFF)
    hub.async_send_code.assert_awaited_once_with("OFFCODE")


async def test_learned_code_overrides_builtin(hass):
    entity, hub = _make_entity(hass, learned_codes={"cool_24_auto_off": "MY_LEARNED_CODE"})
    entity._attr_target_temperature = 24
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    await entity.async_set_hvac_mode(HVACMode.COOL)
    hub.async_send_code.assert_awaited_once_with("MY_LEARNED_CODE")


async def test_missing_code_raises_friendly_error(hass):
    entity, hub = _make_entity(hass)
    entity._attr_target_temperature = 19  # no code exists for cool_19_*
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    with pytest.raises(HomeAssistantError, match="Learn Command"):
        await entity.async_set_hvac_mode(HVACMode.COOL)
    hub.async_send_code.assert_not_awaited()


async def test_hub_failure_raises_home_assistant_error(hass):
    hub = AsyncMock()
    hub.async_send_code.side_effect = TuyaIrConnectionError("unreachable")
    entity, _ = _make_entity(hass, hub=hub)
    entity._attr_target_temperature = 24
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    with pytest.raises(HomeAssistantError, match="Failed to send IR command"):
        await entity.async_set_hvac_mode(HVACMode.COOL)
