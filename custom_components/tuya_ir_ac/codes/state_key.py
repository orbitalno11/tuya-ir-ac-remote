"""Canonical state-key scheme shared by built-in and learned IR code tables.

A "state" protocol AC remote sends the entire device state (mode, temp, fan,
swing, power) in a single IR frame on every press. We mirror that: every
unique (mode, temp, fan, swing) combination is looked up as one code, and
"off" is always its own standalone key since power-off frames are typically
protocol-distinct rather than "current mode with the power bit cleared".
"""
from __future__ import annotations

from ..const import STATE_KEY_OFF

HVAC_MODE_OFF = "off"
HVAC_MODE_FAN_ONLY = "fan_only"

# Modes that do not carry a target temperature -- their state keys use the
# "none" temperature part so they match the bundled/learned code tables.
TEMPERATURELESS_MODES = frozenset({HVAC_MODE_FAN_ONLY})


def build_state_key(
    hvac_mode: str,
    temperature: float | int | None,
    fan_mode: str,
    swing_mode: str,
) -> str:
    """Build the canonical lookup key for a given climate state."""
    if hvac_mode == HVAC_MODE_OFF:
        return STATE_KEY_OFF

    if hvac_mode in TEMPERATURELESS_MODES or temperature is None:
        temp_part = "none"
    else:
        temp_part = str(int(round(temperature)))
    return f"{hvac_mode}_{temp_part}_{fan_mode}_{swing_mode}"
