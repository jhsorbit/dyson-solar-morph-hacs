"""Constants for the Dyson Lightcycle Morph integration."""

from __future__ import annotations

DOMAIN = "dyson_lamp"

# Integration version, surfaced in config-flow error messages so the user
# knows which build is being validated.
INTEGRATION_VERSION = "0.2.6"

# Configuration flow / entry keys
CONF_SERIAL = "serial"
CONF_ADDRESS = "address"
CONF_USER_ID = "user_id"
CONF_LTK = "ltk"
CONF_MODE = "mode"

# Connection modes
MODE_PERSISTENT = "persistent"
MODE_APP_COMPATIBLE = "app_compatible"

CONNECTION_MODES = [
    MODE_PERSISTENT,
    MODE_APP_COMPATIBLE,
]

# Defaults
CONF_SERIAL_DEFAULT = ""
CONF_ADDRESS_DEFAULT = ""
CONF_USER_ID_DEFAULT = ""
CONF_LTK_DEFAULT = ""

# Brightness / color temperature limits (raw GATT)
BRIGHT_MIN = 100
BRIGHT_MAX = 1000
COLOR_TEMP_MIN = 2700
COLOR_TEMP_MAX = 6500

# Preset modes (mapped to PRESET_MODE_PACKETS in lamp.py)
PRESET_MODE_SYNC = "synchronised"
PRESET_MODE_STUDY = "study"
PRESET_MODE_RELAX = "relax"
PRESET_MODE_PRECISION = "precision"

EFFECTS = {
    "Synchronised": PRESET_MODE_SYNC,
    "Study": PRESET_MODE_STUDY,
    "Relax": PRESET_MODE_RELAX,
    "Precision": PRESET_MODE_PRECISION,
}

# Friendly display name of the brand/device
DEVICE_NAME = "Dyson Lightcycle Morph"
DEVICE_MODEL = "Lightcycle Morph (552)"
DEVICE_MANUFACTURER = "Dyson"

# Service names (platforms) this integration provides
PLATFORMS = ["light", "switch", "select"]

SCAN_INTERVAL_SECONDS = 30
CONNECT_TIMEOUT_SECONDS = 15
