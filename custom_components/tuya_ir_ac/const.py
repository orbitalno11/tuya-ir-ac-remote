"""Constants for the Tuya IR AC Remote integration."""
from __future__ import annotations

DOMAIN = "tuya_ir_ac"

# Config / options keys
CONF_DEVICE_ID = "device_id"
CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_BRAND = "brand"
CONF_VARIANT = "variant"

# Tuya Cloud API credentials -- setup-time only, used to look up devices
# during the config flow's "cloud discovery" path. Never used at runtime;
# see tuya_cloud.py.
CONF_ACCESS_ID = "access_id"
CONF_ACCESS_SECRET = "access_secret"
CONF_API_REGION = "api_region"

DEFAULT_PROTOCOL_VERSION = "3.3"
PROTOCOL_VERSIONS = ["3.1", "3.3", "3.4"]

DEFAULT_API_REGION = "us"
API_REGIONS = ["cn", "us", "us-e", "eu", "eu-w", "in", "sg"]

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

# Modes/temps/fans covered by the full Learn Command punch list below.
# Swing is fixed to "off" -- swinging louvers aren't part of this range on
# purpose (re-run the flow manually for swing "on" combinations if needed).
LEARN_HVAC_MODES = ["auto", "cool", "dry"]
LEARN_MIN_TEMP = 16
LEARN_MAX_TEMP = 30
LEARN_FAN_MODES = [FAN_MODE_AUTO, FAN_MODE_LOW, FAN_MODE_MEDIUM, FAN_MODE_HIGH]
LEARN_SWING_MODE = SWING_MODE_OFF

# Punch-list of state keys offered by the Learn Command flow: "off",
# fan-only, plus every (mode, temp, fan) combination above at swing "off".
# This is intentionally large (~180 entries covering auto/cool/dry across
# 16-30 degC and all four fan speeds) -- teaching all of it means pressing
# that many buttons on the real remote, one Learn Command step at a time.
LEARN_PUNCH_LIST = [
    STATE_KEY_OFF,
    "fan_only_none_high_off",
    *(
        f"{mode}_{temp}_{fan}_{LEARN_SWING_MODE}"
        for mode in LEARN_HVAC_MODES
        for temp in range(LEARN_MIN_TEMP, LEARN_MAX_TEMP + 1)
        for fan in LEARN_FAN_MODES
    ),
]

STORAGE_VERSION = 1
STORAGE_KEY_TEMPLATE = "tuya_ir_ac_{entry_id}_codes"
