"""Unit tests for the TuyaIrClimateEntity."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tuya_ir_ac.climate import (
    TuyaIrClimateEntity,
    TuyaIrLastActiveModeData,
)
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
        "fan_only_none_high_off": "FANONLYCODE",
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
    # multi-word mode with a code is advertised (regression: previously the
    # key was split on the first "_" and "fan_only" was mistaken for "fan")
    assert HVACMode.FAN_ONLY in entity.hvac_modes
    # no "dry"/"auto" codes in FAKE_TABLE -> not advertised
    assert HVACMode.DRY not in entity.hvac_modes
    assert HVACMode.AUTO not in entity.hvac_modes


async def test_fan_only_sends_temperatureless_code(hass):
    # fan_only lookup must ignore the (always-set) target temperature and
    # match the "none" temp key in the table.
    entity, hub = _make_entity(hass)
    entity._attr_target_temperature = 16
    entity._attr_fan_mode = "high"
    entity._attr_swing_mode = "off"
    await entity.async_set_hvac_mode(HVACMode.FAN_ONLY)
    hub.async_send_code.assert_awaited_once_with("FANONLYCODE")


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


async def test_turn_off_uses_async_turn_off(hass):
    # Exercises the actual entry point Google Assistant / HA core calls for
    # "turn off", as opposed to test_turn_off_sends_off_code which calls
    # async_set_hvac_mode directly.
    entity, hub = _make_entity(hass)
    entity._attr_hvac_mode = HVACMode.COOL

    await entity.async_turn_off()

    hub.async_send_code.assert_awaited_once_with("OFFCODE")
    assert entity.hvac_mode == HVACMode.OFF


async def test_turn_on_resumes_last_active_mode_with_existing_temp_and_fan(hass):
    entity, hub = _make_entity(hass)
    entity._attr_target_temperature = 22
    entity._attr_fan_mode = "low"
    entity._attr_swing_mode = "on"
    await entity.async_set_hvac_mode(HVACMode.COOL)  # COOL22LOWONCODE
    await entity.async_set_hvac_mode(HVACMode.OFF)  # OFFCODE
    hub.async_send_code.reset_mock()

    await entity.async_turn_on()

    hub.async_send_code.assert_awaited_once_with("COOL22LOWONCODE")
    assert entity.hvac_mode == HVACMode.COOL
    assert entity.target_temperature == 22
    assert entity.fan_mode == "low"


async def test_turn_on_resumes_heat_not_default_priority_mode(hass):
    # HEAT is not first in CONTROLLABLE_HVAC_MODES priority order (COOL is);
    # this proves turn_on tracks the actual last-active mode rather than
    # falling back to a fixed priority pick.
    entity, hub = _make_entity(hass)
    entity._attr_target_temperature = 22
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    await entity.async_set_hvac_mode(HVACMode.HEAT)  # HEAT22CODE
    await entity.async_set_hvac_mode(HVACMode.OFF)
    hub.async_send_code.reset_mock()

    await entity.async_turn_on()

    hub.async_send_code.assert_awaited_once_with("HEAT22CODE")
    assert entity.hvac_mode == HVACMode.HEAT


async def test_turn_on_defaults_when_never_active_before(hass):
    # Fresh entity, never set to a non-off mode -- must pick a sane default.
    entity, hub = _make_entity(hass)
    entity._attr_fan_mode = "auto"
    entity._attr_swing_mode = "off"
    entity._attr_target_temperature = 24  # cool_24_* exists in FAKE_TABLE

    await entity.async_turn_on()

    hub.async_send_code.assert_awaited_once_with("COOL24CODE")
    assert entity.hvac_mode == HVACMode.COOL


async def test_last_active_mode_survives_restart(hass):
    entity, hub = _make_entity(hass)
    with patch.object(
        entity,
        "async_get_last_state",
        AsyncMock(
            return_value=State(
                entity.entity_id,
                HVACMode.OFF,
                {"temperature": 22, "fan_mode": "low", "swing_mode": "on"},
            )
        ),
    ), patch.object(
        entity,
        "async_get_last_extra_data",
        AsyncMock(return_value=TuyaIrLastActiveModeData(last_active_hvac_mode="cool")),
    ):
        await entity.async_added_to_hass()

    # Plain state restore alone (off + attrs) cannot recover "was cool
    # before off" -- that must come from the extra-data side-channel.
    assert entity.hvac_mode == HVACMode.OFF
    assert entity._attr_last_active_hvac_mode == HVACMode.COOL

    await entity.async_turn_on()

    hub.async_send_code.assert_awaited_once_with("COOL22LOWONCODE")
    assert entity.hvac_mode == HVACMode.COOL


async def test_turn_on_raises_when_no_controllable_modes(hass):
    # A code table with only "off" -- e.g. mid-setup before any Learn
    # Command codes exist -- must surface a clear error rather than
    # silently no-op'ing back to HVACMode.OFF.
    empty_table = CodeTable(
        brand="panasonic", variant="test", protocol="state", codes={"off": "OFFCODE"}
    )
    entity, hub = _make_entity(hass)
    entity._builtin_table = empty_table
    entity._attr_hvac_modes = entity._derive_supported_hvac_modes()

    with pytest.raises(HomeAssistantError, match="No controllable HVAC mode"):
        await entity.async_turn_on()
    hub.async_send_code.assert_not_awaited()


async def test_last_active_mode_defaults_on_fresh_install_extra_data_none(hass):
    # Fresh install: async_get_last_state()/async_get_last_extra_data() both
    # naturally resolve to None with no prior restore data.
    entity, _ = _make_entity(hass)
    await entity.async_added_to_hass()

    assert entity._attr_last_active_hvac_mode == HVACMode.COOL


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
