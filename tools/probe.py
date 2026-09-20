#!/usr/bin/env python3
"""Interactive protocol probe for MR Star garlands.

Sends one carefully chosen frame at a time and asks what the garland did. It
exists to settle, against a real device, the questions that decompiling the
Android app cannot answer: whether a colour write takes effect while an effect
is running, whether the write type and pacing matter, and what the firmware
does with values outside the ranges the app uses.

Run it from a machine with a Bluetooth adapter in range of the garland, with
the Home Assistant integration disabled or the garland out of its reach, so
that nothing else is writing to the device at the same time:

    pip install bleak
    python3 probe.py

Nothing here writes to Home Assistant or changes any stored state. The garland
is left in a known state at the end.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

SERVICE_FILTER = "00002022-0000-1000-8000-00805f9b34fb"
GATT_SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
WRITE_CHAR = "0000fff3-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "0000fff4-0000-1000-8000-00805f9b34fb"


def frame(command: int, payload: list[int]) -> bytes:
    """Build a BC <cmd> <len> <payload> 55 frame."""
    return bytes([0xBC, command, len(payload), *payload, 0x55])


def power(on: bool) -> bytes:
    return frame(0x01, [1 if on else 0])


def colour(hue: int, saturation: int) -> bytes:
    """Hue 0-360, saturation 0-1000, exactly as the app encodes them."""
    return frame(0x04, [hue // 256, hue % 256, saturation // 256, saturation % 256, 0, 0])


def brightness(level: int) -> bytes:
    """Level 3-1000 in the app. Out-of-range values are deliberately testable."""
    return frame(0x05, [level // 256, level % 256, 0, 0, 0, 0])


def effect(mode: int) -> bytes:
    return frame(0x06, [mode // 256, mode % 256])


RED = colour(0, 1000)
GREEN = colour(120, 1000)
WHITE_APP = colour(0, 1000)
WHITE_SAT_ZERO = colour(0, 0)


class Probe:
    """Drives the garland and records what the operator reports."""

    def __init__(self, client: BleakClient, delay: float) -> None:
        self.client = client
        self.delay = delay
        self.results: list[tuple[str, str]] = []
        self.notifications: list[bytes] = []

    async def send(self, payload: bytes, *, response: bool, pace: bool = True) -> None:
        print(f"    -> {payload.hex(' ')}  (write {'with' if response else 'without'} response)")
        await self.client.write_gatt_char(WRITE_CHAR, payload, response=response)
        if pace:
            await asyncio.sleep(self.delay)

    def ask(self, label: str, question: str) -> str:
        print(f"\n  {question}")
        print("    [s] solid colour, as asked      [e] effect or colour cycling")
        print("    [n] nothing changed             [o] something else")
        while True:
            answer = input("    > ").strip().lower()[:1]
            if answer in ("s", "e", "n", "o"):
                self.results.append((label, answer))
                return answer
            print("    please answer s, e, n or o")

    async def reset_to_known_state(self) -> None:
        """Solid green at a sane brightness, so each test starts comparable."""
        await self.send(power(True), response=True)
        await self.send(brightness(1000), response=True)
        await self.send(GREEN, response=True)
        await asyncio.sleep(1.0)


TESTS: list[tuple[str, str]] = [
    ("T1", "colour written the way the integration writes it now"),
    ("T2", "the same colour, written with response"),
    ("T3", "colour on its own, nothing sent before it"),
    ("T4", "colour sent while effect 1, automatic loop, is running"),
    ("T5", "mode 0 sent first, to test whether 0 means static"),
    ("T6", "brightness 1000 then colour, the app's maximum"),
    ("T7", "brightness 1024 then colour, what mr_star_ble sends at 100 percent"),
    ("T8", "white as saturation 1000, the way the app sends it"),
    ("T9", "white as saturation 0, the way the integration sends it"),
]


async def run(probe: Probe) -> None:
    print("\nBaseline. The garland should come on.")
    await probe.send(power(True), response=True)
    if probe.ask("T0", "Did the garland turn on?") == "n":
        print("\n  The garland is not accepting power commands. Stop here; nothing")
        print("  below will mean anything.")
        return

    print("\n--- T1: colour the way the integration writes it now ---")
    print("  Power then colour, back to back, write without response, no pacing.")
    await probe.send(power(True), response=False, pace=False)
    await probe.send(RED, response=False, pace=False)
    await asyncio.sleep(1.5)
    probe.ask("T1", "Is the garland solid red?")

    print("\n--- T2: the same, but written with response ---")
    await probe.reset_to_known_state()
    await probe.send(power(True), response=True, pace=False)
    await probe.send(RED, response=True, pace=False)
    await asyncio.sleep(1.5)
    probe.ask("T2", "Is the garland solid red?")

    print("\n--- T3: colour on its own, paced, nothing sent before it ---")
    await probe.reset_to_known_state()
    await probe.send(RED, response=True)
    await asyncio.sleep(1.5)
    probe.ask("T3", "Is the garland solid red?")

    print("\n--- T4: does a colour override a running effect? ---")
    print("  Starting automatic loop, then asking for red.")
    await probe.send(effect(1), response=True)
    await asyncio.sleep(3.0)
    await probe.send(RED, response=True)
    await asyncio.sleep(2.0)
    probe.ask("T4", "Is the garland solid red, or still cycling?")

    print("\n--- T5: is mode 0 a static mode? ---")
    await probe.send(effect(1), response=True)
    await asyncio.sleep(2.0)
    await probe.send(effect(0), response=True)
    await probe.send(RED, response=True)
    await asyncio.sleep(1.5)
    probe.ask("T5", "Is the garland solid red?")

    print("\n--- T6: brightness 1000 then colour ---")
    await probe.reset_to_known_state()
    await probe.send(brightness(1000), response=True)
    await probe.send(RED, response=True)
    await asyncio.sleep(1.5)
    probe.ask("T6", "Is the garland solid red?")

    print("\n--- T7: brightness 1024 then colour ---")
    print("  1024 is above the app's maximum of 1000. This is what the")
    print("  library sends at 100 percent brightness.")
    await probe.reset_to_known_state()
    await probe.send(brightness(1024), response=True)
    await probe.send(RED, response=True)
    await asyncio.sleep(1.5)
    probe.ask("T7", "Is the garland solid red?")

    print("\n--- T8: white, the app's way, saturation 1000 ---")
    await probe.reset_to_known_state()
    await probe.send(WHITE_APP, response=True)
    await asyncio.sleep(1.5)
    probe.ask("T8", "Is the garland solid white?")

    print("\n--- T9: white, saturation 0 ---")
    await probe.reset_to_known_state()
    await probe.send(WHITE_SAT_ZERO, response=True)
    await asyncio.sleep(1.5)
    probe.ask("T9", "Is the garland solid white?")

    print("\nLeaving the garland on solid green.")
    await probe.reset_to_known_state()


def verdict(results: dict[str, str]) -> None:
    print("\n" + "=" * 68)
    print("RESULTS")
    print("=" * 68)
    labels = dict(TESTS)
    for key, answer in results.items():
        if key == "T0":
            continue
        word = {"s": "solid colour", "e": "effect or cycling", "n": "no change", "o": "other"}[answer]
        print(f"  {key}  {labels.get(key, ''):<58} {word}")

    print("\nREADING")
    solid = {k for k, v in results.items() if v == "s"}

    if "T1" in solid:
        print("  T1 worked, so the transport is not the problem and the colour")
        print("  frame is correct. Whatever you saw in Home Assistant is coming")
        print("  from somewhere else in the integration, not from the protocol.")
    elif "T2" in solid or "T3" in solid:
        print("  The colour frame is right but the way it is written matters.")
        if "T2" in solid:
            print("  T2 passing means the write must be a write with response.")
        if "T3" in solid and "T2" not in solid:
            print("  T3 passing while T2 failed means commands must be spaced out;")
            print("  the device is dropping a command that arrives too soon after")
            print("  the previous one.")
        print("  Fix: write with response and serialise commands in the coordinator.")
    if "T4" not in solid and ("T2" in solid or "T3" in solid):
        print("  T4 failing is the important one: a colour write does NOT stop a")
        print("  running effect. The integration must leave effect mode before")
        print("  setting a colour.")
        if "T5" in solid:
            print("  T5 passing gives us the way out: mode 0 is the static mode.")
        else:
            print("  T5 failed too, so mode 0 is not the way out. The integration")
            print("  should instead avoid entering effect mode unless asked, and")
            print("  power cycle the garland to clear one.")
    if "T6" in solid and "T7" not in solid:
        print("  Brightness 1024 breaks the device where 1000 does not. The")
        print("  library's int(1024 * brightness) is out of range at full")
        print("  brightness and has to be clamped to 1000.")
    if "T8" in solid and "T9" not in solid:
        print("  Saturation 0 is not a valid white. Clamp saturation to at least")
        print("  1, the way the app does.")
    print("\nPaste this whole output back and the fix follows from it.")


async def pick_device(address: str | None) -> BLEDevice | None:
    if address:
        print(f"Looking for {address} ...")
        return await BleakScanner.find_device_by_address(address, timeout=15.0)

    print("Scanning for MR Star garlands, 10 seconds ...")
    found = await BleakScanner.discover(timeout=10.0, return_adv=True)
    candidates = [
        (d, adv)
        for d, adv in found.values()
        if SERVICE_FILTER in [u.lower() for u in adv.service_uuids]
    ]
    if not candidates:
        print("\nNo garland found. Check it is powered and not already connected")
        print("to your phone or to Home Assistant.")
        return None
    if len(candidates) == 1:
        device, adv = candidates[0]
        print(f"Found {device.name or 'unnamed'} at {device.address}, rssi {adv.rssi}")
        return device
    for index, (device, adv) in enumerate(candidates, 1):
        print(f"  {index}. {device.name or 'unnamed'}  {device.address}  rssi {adv.rssi}")
    choice = input("Which one? ").strip()
    try:
        return candidates[int(choice) - 1][0]
    except (ValueError, IndexError):
        return None


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="skip scanning and connect to this address")
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="seconds to wait after a paced write (default 0.25)",
    )
    args = parser.parse_args()

    device = await pick_device(args.address)
    if device is None:
        return 1

    print(f"\nConnecting to {device.address} ...")
    async with BleakClient(device, timeout=30.0) as client:
        print("Connected.\n")
        services = [s.uuid.lower() for s in client.services]
        print(f"  services: {', '.join(services)}")
        if GATT_SERVICE not in services:
            print(f"  warning: {GATT_SERVICE} not present, this may not be a garland")

        probe = Probe(client, args.delay)

        def on_notify(_sender, data: bytearray) -> None:
            probe.notifications.append(bytes(data))
            print(f"    <- {bytes(data).hex(' ')}")

        try:
            await client.start_notify(NOTIFY_CHAR, on_notify)
            print(f"  listening on {NOTIFY_CHAR}")
        except Exception as exc:  # noqa: BLE001
            print(f"  no notifications available: {exc}")

        print("\nWatch the garland and answer each question.")
        await run(probe)

    verdict(dict(probe.results))
    if probe.notifications:
        print("\nNotifications seen:")
        for data in probe.notifications:
            print(f"  {data.hex(' ')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted. The garland may be left mid-test.")
        sys.exit(130)
