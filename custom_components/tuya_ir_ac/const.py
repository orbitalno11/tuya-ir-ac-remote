"""Constants for the Tuya IR AC Remote integration."""
from __future__ import annotations

DOMAIN = "tuya_ir_ac"

# Config / options keys
CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_BRAND = "brand"
CONF_VARIANT = "variant"

DEFAULT_PROTOCOL_VERSION = "3.3"
PROTOCOL_VERSIONS = ["3.1", "3.3", "3.4"]

BRAND_PANASONIC = "panasonic"
BRAND_CARRIER = "carrier"
BRAND_GENERIC = "generic"
BRANDS = [BRAND_PANASONIC, BRAND_CARRIER, BRAND_GENERIC]

# Climate defaults, used when a code table doesn't specify its own metadata.
DEFAULT_MIN_TEMP = 16
DEFAULT_MAX_TEMP = 30
DEFAULT_TEMP_STEP = 1

FAN_MODE_AUTO = "auto"
FAN_MODE_LOW = "low"
FAN_MODE_MEDIUM = "medium"
FAN_MODE_HIGH = "high"
DEFAULT_FAN_MODES = [FAN_MODE_AUTO, FAN_MODE_LOW, FAN_MODE_MEDIUM, FAN_MODE_HIGH]

SWING_MODE_OFF = "off"
SWING_MODE_ON = "on"
DEFAULT_SWING_MODES = [SWING_MODE_OFF, SWING_MODE_ON]

# State-key for the "power off" command. Always standalone (see codes/state_key.py).
STATE_KEY_OFF = "off"

# IR learning
LEARN_TIMEOUT = 15  # seconds to wait for a button press during a Learn Command step
CONNECT_RETRIES = 2

# Curated punch-list of state keys offered by the Learn Command flow.
# Kept short on purpose -- learning every possible combination is impractical;
# users can re-run the flow for additional combinations as needed.
LEARN_PUNCH_LIST = [
    STATE_KEY_OFF,
    "cool_24_auto_off",
    "cool_22_auto_off",
    "cool_26_auto_off",
    "heat_22_auto_off",
    "dry_24_auto_off",
    "fan_only_none_high_off",
]

STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = "tuya_ir_ac_{entry_id}_codes"
