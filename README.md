# MR Star Home Assistant Integration [![Quality assurance](https://github.com/mishamyrt/mr-star-hass/actions/workflows/qa.yaml/badge.svg)](https://github.com/mishamyrt/mr-star-hass/actions/workflows/qa.yaml)

Integration for [MR Star Garland](https://github.com/mishamyrt/mr-star-ble) devices.

It uses bluetooth to control the lights.

## Requirements

- Home Assistant 2026.3 or newer
- A Bluetooth adapter or an ESPHome Bluetooth proxy within range of the garland

## Installation

### [hapm](https://github.com/mishamyrt/hapm)

Add this repository to your `hapm.yaml` by running:

```sh
hapm add mishamyrt/mr-star-hass@latest
```

### HACS

Add this repo as HACS [custom repository](https://hacs.xyz/docs/faq/custom_repositories).

```
https://github.com/mishamyrt/mr-star-hass
```

Then find the integration in the list and press "Download".

### Manual

Copy `mr_star_garland` folder from latest release to `/config/custom_components` folder.

## Configuration

The garland is picked up by Home Assistant's Bluetooth discovery once it is in
range, and appears as a discovered device on the integrations page. To add it by
hand instead:

1. Go to the integrations page
2. Click "Add Integration"
3. Find MR Star Garland in the list and select it
4. Select the device address from the list

## Entities

Each garland provides two entities:

- a light, with brightness, hue and saturation, and the full effect list
  reported by the firmware
- a number, for the count of LEDs the controller should drive

Both are unavailable while the Bluetooth session is down, regardless of whether
the garland is switched on.

## Development

```sh
make configure   # create the venv from requirements.txt
make lint        # pylint and ruff
make test        # pytest
```

Requires Python 3.14, which is what current Home Assistant needs.
