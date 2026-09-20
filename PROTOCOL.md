# MR Star garland BLE protocol

Reverse engineered from the official Android app, `com.frok.mrstar` version
1.0.0 (versionCode 104), by decompiling `classes.dex` with jadx and reading
`com.findn.MyApplication`, the fragments under `com.findn.ui.fragment` and the
helpers under `com.findn.utils`. Byte layouts below are transcribed from the
literal `byte[]` arrays the app passes to `MyApplication.sendDataToBle`, so they
are what the app actually puts on the wire rather than an interpretation of it.

## Transport

| Property | Value |
|---|---|
| Advertised service filter | `0x2022`, matched by the app on the two scan-record bytes `0x22 0x20` |
| GATT service | `0000FFF0-0000-1000-8000-00805F9B34FB` |
| Write characteristic | `0000FFF3-0000-1000-8000-00805F9B34FB` |
| Notify characteristic | `0000FFF4-0000-1000-8000-00805F9B34FB` |

The app writes through FastBLE with `split = true`,
`sendNextWhenLastSuccess = true` and a 200 ms inter-packet interval. FastBLE
uses `WRITE_TYPE_DEFAULT`, so every command is a **write with response** and
Android serialises them: the next command is not issued until the previous one
has been acknowledged by the device. There is no pairing, no authentication and
no handshake. Nothing is sent on connect.

Note that `mr_star_ble` writes to FFF3 with `response=False` and does not
serialise or pace. That is a deviation from the reference client.

## Frame format

```
BC <cmd> <len> <payload ...> 55
```

`0xBC` prefix, one command byte, one length byte counting only the payload,
the payload, then the `0x55` suffix. Multi-byte values are big endian. The app
builds them as `(v / 256, v % 256)`, except the effect command which uses
`(v / 255, v % 255)`, an inconsistency with no practical effect because mode
numbers stay below 255.

## Commands

| Cmd | Len | Payload | Meaning |
|---|---|---|---|
| `0x01` | 1 | `00` off, `01` on | Power |
| `0x02` | 1 | `01`..`06` | Channel order: RGB, RBG, GRB, GBR, BRG, BGR |
| `0x03` | 2 | count, 8 to 300 | LED count |
| `0x04` | 6 | hue hi, hue lo, sat hi, sat lo, `00`, `00` | Static colour |
| `0x05` | 6 | level hi, level lo, `00`, `00`, `00`, `00` | Brightness, 3 to 1000 |
| `0x06` | 2 | mode hi, mode lo | Effect, see the mode table |
| `0x07` | 1 | `00` forward, `01` reverse | Effect direction |
| `0x08` | 1 | `00`..`64` | Effect speed, 0 to 100 |
| `0x09` | 6 | hue hi, hue lo, sat hi, sat lo, `00`, `00` | Colour while in music mode |
| `0x0B` | 7 | year hi, year lo, month, day, hour, minute, second | Clock sync, see the quirk below |
| `0x0C` | 1 | `01` | Read back the timer settings |
| `0x0D` | 6 | `01`, on/off slot, enabled, weekday mask, hour, minute | Timer schedule entry |
| `0x0F` | 1 | `00` phone mic, `01` device mic | Microphone source |
| `0x11` | 1 | `01` classic, `02` soft, `03` dynamic, `04` disco | Microphone mode |
| `0x12` | 1 | `00`..`64` | Microphone sensitivity |
| `0x13` | 2 | angle hi, angle lo, 0 to 360 | Angle from the app's secondary colour wheel, purpose not established |

### Colour, `0x04`

Hue and saturation, not RGB. Hue is 0 to 360. Saturation is 0 to 1000, which is
the HSV saturation multiplied by 1000. The app derives both with
`Color.RGBToHSV` and then applies this clamp in `RgbUtils.getHsvFromRgb`:

```java
if (saturation > 1.0f || (hue == 0.0f && saturation == 0.0f)) {
    saturation = 1.0f;
}
```

So the app never sends saturation 0. White is sent as hue 0, saturation 1000,
not as saturation 0. Treat saturation 0 as a value the firmware is not known to
accept.

Worked examples, taken byte for byte from the app:

| Colour | Frame |
|---|---|
| Red | `BC 04 06 00 00 03 E8 00 00 55` |
| Green | `BC 04 06 00 78 03 E8 00 00 55` |
| Blue | `BC 04 06 00 F0 03 E8 00 00 55` |
| White | `BC 04 06 00 00 03 E8 00 00 55` |

The app sends this command on touch-down, on every touch-move and on touch-up
while the colour wheel is being dragged, so the firmware tolerates a rapid
stream of colour writes.

### Brightness, `0x05`

The seekbar in `fragment_adjust.xml` is `android:max="1000"` and the app floors
the value at 3 before sending:

```java
int progress = seekBar.getProgress();
if (progress < 3) progress = 3;
```

So the valid range is 3 to 1000. `mr_star_ble` computes `int(1024 * brightness)`
and therefore sends 1024 at full brightness, which is above anything the
reference client ever sends.

### Clock sync, `0x0B`

This frame is malformed in the app itself and is reproduced here as-is, because
the firmware evidently accepts it:

```java
{ -68, 11, 7, yearHi, yearLo, month, day, hour, minute, second, 85, weekday }
```

The `0x55` suffix sits at index 10 and a weekday byte, 1 for Monday through 7
for Sunday, follows it. Either the firmware ignores trailing bytes or the length
field is what it actually parses.

## Device notifications

The device pushes frames on FFF4 with the same `BC <cmd> <len> ... 55` shape.
The app reads three of them in `MainActivity.onMessageEvent`, keying on byte 1:

| Byte 1 | Meaning |
|---|---|
| `0x05` | Current brightness, big-endian uint16 at offset 3 |
| `0x08` | Current speed, byte at offset 3 |
| `0x10` | Current microphone sensitivity, byte at offset 3 |

The app ignores every other notification. There is no known query that returns
the current mode or colour.

## Effect modes

Mode numbers are sent with command `0x06`. The app builds its Mode tab from
seven groups:

| Tab | Modes |
|---|---|
| 1 | 1, 2, 3, 4, 7, 10, 26, 27, 29, 30, 31, 32 |
| 2 | 35 to 44 |
| 3 | 45 to 54 |
| 4 | 55 to 62 |
| 5 | 63 to 75 |
| 6 | 76 to 83 |
| 7 | 84 to 93 |

That is 71 modes. The app skips 5, 6, 8, 9 and 28 even though its own string
resources name them, and `mr_star_ble` enumerates 9, 28, 94 and 95 which the app
does not offer. String resources exist for `cmode1` through `cmode117`, so the
firmware probably answers to more modes than either client uses.

Names for every mode are in `custom_components/mr_star_garland/effects.py`,
taken from the app's own string resources.

There is no mode number that the app documents as "static" or "solid". The
Adjust tab sends `0x04` on its own with no preceding mode change, so on the
app's evidence a colour write is expected to take effect by itself.

## What this does not answer

Whether the firmware honours `0x04` while an effect from `0x06` is running. The
app gives no evidence either way, because it never sends a mode command when the
user moves to the colour tab. `tools/probe.py` tests this against a real device.
