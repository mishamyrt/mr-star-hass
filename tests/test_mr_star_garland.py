"""Tests for the MR Star Garland integration.

These cover the pure logic, the command encodings that PROTOCOL.md pins down,
and the coordinator shutdown path, which previously blocked forever when the
garland was unreachable.
"""

import asyncio
import logging
import time
from types import SimpleNamespace

import pytest
from mr_star_ble import Effect
from mr_star_ble.commands import format_command
from mr_star_ble.const import Command

from custom_components.mr_star_garland import coordinator as coordinator_module
from custom_components.mr_star_garland import short_id
from custom_components.mr_star_garland.const import (
    MAX_DEVICE_BRIGHTNESS,
    MIN_DEVICE_BRIGHTNESS,
    WHITE_HUE,
    WHITE_SATURATION,
)
from custom_components.mr_star_garland.coordinator import MrStarCoordinator
from custom_components.mr_star_garland.effects import (
    EFFECT_DEFS,
    EFFECT_LIST,
    EFFECTS,
    LEGACY_EFFECT_ALIASES,
)
from custom_components.mr_star_garland.light import (
    MODE_COLOR,
    MODE_EFFECT,
    MrStarLightEntity,
    _device_brightness,
    _device_color,
    _resolve_effect,
)
from custom_components.mr_star_garland.number import LEDCountEntity

ADDRESS = "AA:BB:CC:DD:EE:FF"


# --- effect table ---------------------------------------------------------


def test_effect_names_are_unique():
    """Two modes must not collapse onto the same display name."""
    assert len(EFFECT_LIST) == len(set(EFFECT_LIST)) == len(EFFECT_DEFS)


def test_effect_table_covers_the_library_enum():
    """Every mode mr_star_ble knows about must still be selectable."""
    assert set(e.value for e in Effect) <= set(EFFECTS.values())


def test_effect_table_adds_the_modes_the_library_is_missing():
    """The app lists modes 63-75, which the library enum does not have."""
    library_modes = {e.value for e in Effect}
    assert set(range(63, 76)) <= set(EFFECTS.values()) - library_modes


def test_legacy_effect_names_still_resolve():
    """Automations selecting the original names must keep working."""
    for name, mode in LEGACY_EFFECT_ALIASES.items():
        assert _resolve_effect(name) == mode
    assert _resolve_effect("Automatic loop") == 1
    assert _resolve_effect("no such effect") is None


# --- command encoding, against PROTOCOL.md --------------------------------


def test_brightness_never_exceeds_what_the_firmware_accepts():
    """The vendor app's seekbar maxes at 1000 and floors at 3."""
    assert _device_brightness(255) == MAX_DEVICE_BRIGHTNESS
    assert _device_brightness(1) >= MIN_DEVICE_BRIGHTNESS
    assert _device_brightness(0) == MIN_DEVICE_BRIGHTNESS
    for value in range(0, 256):
        level = _device_brightness(value)
        assert MIN_DEVICE_BRIGHTNESS <= level <= MAX_DEVICE_BRIGHTNESS


def _colour_frame(hue: float, saturation: float) -> bytes:
    """Build the frame exactly as the light platform builds it."""
    device_hue, device_saturation = _device_color(hue, saturation)
    return format_command(
        Command.SET_COLOR,
        bytes(
            [
                device_hue // 256,
                device_hue % 256,
                device_saturation // 256,
                device_saturation % 256,
                0x00,
                0x00,
            ]
        ),
    )


def _brightness_frame(brightness: int) -> bytes:
    """Build the frame exactly as the light platform builds it."""
    level = _device_brightness(brightness)
    return format_command(
        Command.SET_BRIGHTNESS,
        bytes([level // 256, level % 256, 0x00, 0x00, 0x00, 0x00]),
    )


def test_saturated_colours_match_the_vendor_app():
    """Red, green and blue must encode exactly as the app encodes them.

    These are the literal bytes the app's sendColorByRGB produces, taken from
    the decompiled source. See PROTOCOL.md.
    """
    assert _device_color(0, 100) == (0, 1000)
    assert _device_color(120, 100) == (120, 1000)
    assert _device_color(240, 100) == (240, 1000)

    assert _colour_frame(0, 100) == bytes.fromhex("bc0406000003e8000055")
    assert _colour_frame(120, 100) == bytes.fromhex("bc0406007803e8000055")
    assert _colour_frame(240, 100) == bytes.fromhex("bc040600f003e8000055")


def test_brightness_frame_stays_inside_the_app_range():
    """Full brightness must be 1000, not the 1024 mr_star_ble sends."""
    assert _brightness_frame(255) == bytes.fromhex("bc050603e80000000055")
    for value in range(0, 256):
        frame = _brightness_frame(value)
        level = (frame[3] << 8) | frame[4]
        assert MIN_DEVICE_BRIGHTNESS <= level <= MAX_DEVICE_BRIGHTNESS


def test_white_frame_matches_the_app_preset():
    """The app's white preset is hue 300, saturation 3."""
    assert _colour_frame(0, 0) == bytes.fromhex("bc0406012c0003000055")


def test_zero_saturation_is_never_sent():
    """The app clamps the fully desaturated case away; so must we."""
    hue, saturation = _device_color(0, 0)
    assert (hue, saturation) == (WHITE_HUE, WHITE_SATURATION)
    assert saturation > 0
    for test_hue in (0, 90, 200, 359):
        assert _device_color(test_hue, 0)[1] > 0


def test_colour_stays_in_range():
    """Hue and saturation must stay inside what the frame can carry."""
    for hue in range(0, 361, 7):
        for saturation in (0, 1, 33.3, 99.9, 100):
            device_hue, device_saturation = _device_color(hue, saturation)
            assert 0 <= device_hue <= 360
            assert 1 <= device_saturation <= 1000


# --- identity and availability -------------------------------------------


def test_short_id_matches_the_original_algorithm():
    """Device and entity names must not change for existing installs."""
    assert short_id(ADDRESS) == ADDRESS[len(ADDRESS) - 5 :].replace(":", "")
    assert short_id(ADDRESS) == "EEFF"


def _fake_entry(coordinator):
    """Build the minimum config entry shape the entities read."""
    return SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=coordinator,
            device_info={"identifiers": {("mr_star_garland", ADDRESS)}},
            address=ADDRESS,
        )
    )


def _bare_coordinator():
    """Build a coordinator without going through DataUpdateCoordinator."""
    coordinator = MrStarCoordinator.__new__(MrStarCoordinator)
    coordinator.hass = SimpleNamespace(
        async_create_background_task=lambda coro, name=None: asyncio.ensure_future(coro)
    )
    coordinator.logger = logging.getLogger("test")
    coordinator.async_set_updated_data = lambda data: setattr(coordinator, "data", data)
    coordinator._address = ADDRESS
    coordinator._ttl = 120
    coordinator._connection_timeout = 30
    coordinator._client = None
    coordinator._writer = None
    coordinator._lock = asyncio.Lock()
    coordinator._stopping = asyncio.Event()
    coordinator._connected = asyncio.Event()
    coordinator._session_task = None
    coordinator._pending_tasks = set()
    coordinator.data = {"connected": False}
    return coordinator


def test_entities_use_address_based_unique_ids():
    """Unique IDs must be derived from the full address, not a display name."""
    coordinator = _bare_coordinator()
    entry = _fake_entry(coordinator)

    lamp = MrStarLightEntity(entry)
    counter = LEDCountEntity(entry)

    assert lamp.unique_id == f"{ADDRESS}_light"
    assert counter.unique_id == f"{ADDRESS}_led_count"
    assert lamp.unique_id != counter.unique_id


def test_availability_follows_the_session_not_the_power_state():
    """An off garland on a live session is available, not unavailable."""
    coordinator = _bare_coordinator()
    lamp = MrStarLightEntity(_fake_entry(coordinator))

    coordinator.data = {"connected": False}
    assert lamp.available is False

    coordinator.data = {"connected": True}
    assert lamp.available is True
    assert lamp.is_on is False


def test_a_fresh_light_never_restores_an_effect():
    """A light that was never put into effect mode must not push one."""
    lamp = MrStarLightEntity(_fake_entry(_bare_coordinator()))
    assert lamp._mode == MODE_COLOR
    assert lamp.effect is None
    assert lamp.extra_restore_state_data.as_dict() == {"mode": MODE_COLOR}


def test_mode_is_recorded_for_restore():
    """The restore store has to carry which of the two modes is live."""
    lamp = MrStarLightEntity(_fake_entry(_bare_coordinator()))
    lamp._mode = MODE_EFFECT
    assert lamp.extra_restore_state_data.as_dict() == {"mode": MODE_EFFECT}


# --- shutdown -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_connection_marks_the_light_unavailable(monkeypatch):
    """A lost device has to reach the entities.

    Connection state was only published after a successful connect, so once a
    session was up the entities kept reporting themselves available even after
    the garland went out of range. Every command then raised instead of the
    device showing as unreachable, which in the HomeKit bridge means a light
    that looks fine, accepts a tap and does nothing.
    """
    monkeypatch.setattr(
        coordinator_module.bluetooth,
        "async_ble_device_from_address",
        lambda hass, address, connectable=True: None,
    )

    coordinator = _bare_coordinator()
    lamp = MrStarLightEntity(_fake_entry(coordinator))

    # A session that was up a moment ago.
    coordinator.data = {"connected": True}
    assert lamp.available is True

    assert await coordinator._async_connect() is False
    assert coordinator.data == {"connected": False}
    assert lamp.available is False


@pytest.mark.asyncio
async def test_stop_returns_while_the_garland_is_unreachable(monkeypatch):
    """Unloading must not block on a device that cannot be connected to.

    The session task spends most of its time in the reconnect backoff when
    the garland is out of range. Stopping has to interrupt that wait.
    """
    monkeypatch.setattr(
        coordinator_module.bluetooth,
        "async_ble_device_from_address",
        lambda hass, address, connectable=True: None,
    )

    coordinator = _bare_coordinator()
    await coordinator.start()
    await asyncio.sleep(0.2)

    started = time.monotonic()
    await coordinator.stop()
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"stop() took {elapsed:.1f}s"
    assert coordinator.data == {"connected": False}
