"""Constants for the MR Star Garland integration."""

from typing import Final

DOMAIN: Final = "mr_star_garland"

# GATT characteristic the garland accepts commands on.
WRITE_CHARACTERISTIC: Final = "0000fff3-0000-1000-8000-00805f9b34fb"
# Minimum gap between two commands. The vendor app is paced by Android's
# acknowledged writes; this reproduces that floor. See PROTOCOL.md.
MIN_WRITE_INTERVAL_SECONDS: Final = 0.05

# How long a BLE session is held open before it is recycled, in seconds.
SESSION_TTL_SECONDS: Final = 120
# Timeout applied to a single connection attempt, in seconds.
CONNECTION_TIMEOUT_SECONDS: Final = 30
# Delay before retrying after a failed connection attempt, in seconds.
RECONNECT_BACKOFF_SECONDS: Final = 15
# Upper bound on how long unloading waits for the session task to finish.
STOP_TIMEOUT_SECONDS: Final = 10

# LED count limits accepted by the device firmware.
DEFAULT_LED_COUNT: Final = 40
MIN_LED_COUNT: Final = 8
MAX_LED_COUNT: Final = 300

# Brightness levels the firmware accepts, as used by the vendor app: its
# seekbar is capped at 1000 and it floors the value at 3 before sending.
MIN_DEVICE_BRIGHTNESS: Final = 3
MAX_DEVICE_BRIGHTNESS: Final = 1000

# Saturation is sent as 0-1000. The app never sends 0; its white preset is
# RGB 255,254,255, which lands on hue 300 with a saturation of 3.
MIN_DEVICE_SATURATION: Final = 1
WHITE_HUE: Final = 300
WHITE_SATURATION: Final = 3
