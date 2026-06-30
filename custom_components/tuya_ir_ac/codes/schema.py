"""Schema and validation for bundled/learned IR code tables."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..const import (
    DEFAULT_FAN_MODES,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_TEMP,
    DEFAULT_SWING_MODES,
    DEFAULT_TEMP_STEP,
    STATE_KEY_OFF,
)

REQUIRED_FIELDS = ("brand", "variant", "protocol", "codes")

# Only "state" protocol AC's (every press encodes the complete device state)
# are supported by built-in tables in this version. "toggle" protocols
# (older Panasonic CKP-style temp+/temp-/power-toggle remotes) would need
# stateful sequencing logic and are out of scope -- see README limitations.
SUPPORTED_PROTOCOLS = ("state",)


class CodeTableValidationError(ValueError):
    """Raised when a code table JSON file fails validation."""


@dataclass
class CodeTable:
    """A validated brand/variant IR code table."""

    brand: str
    variant: str
    protocol: str
    codes: dict[str, str]
    min_temp: int = DEFAULT_MIN_TEMP
    max_temp: int = DEFAULT_MAX_TEMP
    temp_step: int = DEFAULT_TEMP_STEP
    fan_modes: list[str] = field(default_factory=lambda: list(DEFAULT_FAN_MODES))
    swing_modes: list[str] = field(default_factory=lambda: list(DEFAULT_SWING_MODES))
    description: str = ""


def validate_code_table(data: dict, source: str = "<unknown>") -> CodeTable:
    """Validate a raw dict (as loaded from JSON) and return a CodeTable."""
    if not isinstance(data, dict):
        raise CodeTableValidationError(f"{source}: code table must be a JSON object")

    missing = [field_name for field_name in REQUIRED_FIELDS if field_name not in data]
    if missing:
        raise CodeTableValidationError(
            f"{source}: missing required field(s): {', '.join(missing)}"
        )

    codes = data["codes"]
    if not isinstance(codes, dict) or not codes:
        raise CodeTableValidationError(f"{source}: 'codes' must be a non-empty object")

    if STATE_KEY_OFF not in codes:
        raise CodeTableValidationError(
            f"{source}: 'codes' must include a {STATE_KEY_OFF!r} entry"
        )

    for key, code in codes.items():
        if not isinstance(key, str) or not key:
            raise CodeTableValidationError(f"{source}: code keys must be non-empty strings")
        if not isinstance(code, str) or not code:
            raise CodeTableValidationError(
                f"{source}: code value for {key!r} must be a non-empty string"
            )

    if data["protocol"] not in SUPPORTED_PROTOCOLS:
        raise CodeTableValidationError(
            f"{source}: unsupported protocol {data['protocol']!r}, only "
            f"{SUPPORTED_PROTOCOLS} is supported by built-in tables in this version"
        )

    return CodeTable(
        brand=data["brand"],
        variant=data["variant"],
        protocol=data["protocol"],
        codes=dict(codes),
        min_temp=int(data.get("min_temp", DEFAULT_MIN_TEMP)),
        max_temp=int(data.get("max_temp", DEFAULT_MAX_TEMP)),
        temp_step=int(data.get("temp_step", DEFAULT_TEMP_STEP)),
        fan_modes=list(data.get("fan_modes", DEFAULT_FAN_MODES)),
        swing_modes=list(data.get("swing_modes", DEFAULT_SWING_MODES)),
        description=str(data.get("description", "")),
    )
