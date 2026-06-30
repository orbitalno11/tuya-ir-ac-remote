"""Tests for codes.state_key.build_state_key."""
import pytest

from custom_components.tuya_ir_ac.codes.state_key import build_state_key


def test_off_is_always_standalone():
    assert build_state_key("off", 24, "auto", "on") == "off"
    assert build_state_key("off", None, "low", "off") == "off"


@pytest.mark.parametrize(
    ("hvac_mode", "temperature", "fan_mode", "swing_mode", "expected"),
    [
        ("cool", 24, "auto", "off", "cool_24_auto_off"),
        ("heat", 22, "low", "on", "heat_22_low_on"),
        ("dry", 24.0, "auto", "off", "dry_24_auto_off"),
        ("cool", 24.6, "high", "off", "cool_25_high_off"),  # rounds to nearest int
    ],
)
def test_state_protocol_combinations(hvac_mode, temperature, fan_mode, swing_mode, expected):
    assert build_state_key(hvac_mode, temperature, fan_mode, swing_mode) == expected


def test_fan_only_with_no_temperature():
    assert build_state_key("fan_only", None, "high", "off") == "fan_only_none_high_off"
