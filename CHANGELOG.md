# Changelog

## 2.1.1

### Fixed

- A failed connection left the entities reporting themselves available. State
  was published only after a successful connect, so once a session had been up
  the light kept looking controllable after the garland went out of range, and
  every command raised instead of the device showing as unreachable. Through
  the HomeKit bridge that meant a light that looked fine in Apple Home,
  accepted a tap and did nothing. The outcome of every connection attempt is
  now published. The intentional session recycle stays invisible, because
  nothing is published between dropping the old session and opening the new
  one.

### Confirmed

- Colour control verified on hardware after the 2.1.0 protocol corrections:
  solid red and solid purple both render correctly on the garland.

## 2.1.0

Protocol corrections taken from the vendor Android app, com.frok.mrstar 1.0.0.
The app was decompiled and every command it sends was transcribed; the result
is documented in PROTOCOL.md.

### Fixed

- Brightness at 100 percent was sent as 1024. The firmware accepts 3 to 1000,
  which is what the app's own seekbar is capped at. Every level the
  integration sends is now inside that range.
- White was sent as saturation 0. The app never sends 0: it clamps the fully
  desaturated case away and its white preset is RGB 255,254,255, which lands
  on hue 300 with a saturation of 3. Zero saturation is now mapped to that.
- Commands were written without response and without pacing. The app writes
  every command with response, which Android serialises, so the next command
  is not issued until the previous one is acknowledged. Writes now go through
  a paced, serialised adapter with the same semantics.
- A restored effect was re-applied on every restart even when the user had
  never chosen one, because Home Assistant records the effect attribute
  whether or not it is in use. The light now records which of colour or effect
  it last drove the garland with, and restores only that.

### Changed

- The effect list is built from the app's own mode numbers and string
  resources: 75 modes with their real names, up from 62. Thirteen of them,
  modes 63 to 75, are absent from mr_star_ble's enum entirely. The six effect
  names this integration used before are kept as aliases, so existing
  automations and scenes keep working.
- Colour, brightness and effect frames are now built in the integration rather
  than through mr_star_ble, whose brightness scale and saturation handling do
  not match the firmware. Framing still comes from the library.

### Added

- PROTOCOL.md, a full reference for the garland's BLE protocol: transport,
  frame format, every command with its payload and ranges, the device's
  notification frames, and the mode table.
- tools/probe.py, an interactive probe that settles against a real garland
  what static analysis cannot: whether a colour write overrides a running
  effect, whether the write type and pacing matter, and how the firmware
  handles out-of-range values.

## 2.0.0

Compatibility and correctness release. Requires Home Assistant 2026.3 or newer.

### Fixed

- The integration no longer fails to load on Home Assistant 2026.3 and later.
  It imported `COLOR_MODE_HS`, which was removed along with the rest of the
  deprecated `COLOR_MODE_*` and `SUPPORT_*` light constants.
- The light declared three different colour mode answers: a class attribute of
  `{XY, BRIGHTNESS}`, a property returning `{HS}`, and a colour mode of `HS`. It
  now declares hue and saturation once, which is what the firmware accepts.
- Unloading or reloading a config entry no longer hangs when the garland is out
  of range. The session task ignored stop requests while it was in its
  reconnect backoff, and only signalled completion on the clean path.
- The config flow no longer reports success for a garland it could not reach.
  Its connection check swallowed every exception and returned a value the
  caller discarded, which made the error branches and their translated strings
  unreachable.
- Restoring a light after a restart now re-applies brightness, colour and
  effect. The restored values were parsed and then passed to the turn-on call
  as an empty dictionary.
- Turning off an already-off light no longer marks the entity unavailable.
  Availability follows the Bluetooth session, not the power state.
- The LED count entity no longer raises `TypeError` when it is restored with no
  previous value.
- Entity unique IDs are derived from the full Bluetooth address instead of a
  display name built from the last two bytes, which could collide between
  devices. Existing entities are migrated on upgrade, so history is kept.

### Changed

- Connections go through `bleak_retry_connector` instead of a bare
  `BleakClient`, which adds retries and support for ESPHome Bluetooth proxies.
  A device that is not in range is now detected before a connection is
  attempted.
- Connection state is pushed to the entities when it changes, replacing the
  five second poll. The integration is push-based, so there was nothing to poll.
- The full effect list reported by the firmware is exposed, 62 effects instead
  of 6. The six original effect names are preserved, so existing automations
  and scenes keep working.
- Colours are sent as hue and saturation directly, removing a lossy conversion
  through RGB.
- `mr_star_ble` updated to 0.4.1, in which `MrStarLight` became `MrStarAPI`.
- Config entry state moved to `entry.runtime_data`, and platform setup, device
  info and entity naming follow current Home Assistant patterns.
- Development requirements, the Makefile and CI target Python 3.14 and Home
  Assistant 2026.9.3. A test suite was added and runs in CI.
