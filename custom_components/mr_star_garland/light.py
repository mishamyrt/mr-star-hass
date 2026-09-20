"""Light platform for MR Star garlands.

Command encodings here follow PROTOCOL.md, which was derived from the vendor
Android app. Where mr_star_ble and the app disagree, the app wins: it is the
client the firmware was shipped against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from mr_star_ble import MrStarAPI
from mr_star_ble.commands import format_command
from mr_star_ble.const import Command

from . import MrStarConfigEntry
from .const import (
    MAX_DEVICE_BRIGHTNESS,
    MIN_DEVICE_BRIGHTNESS,
    MIN_DEVICE_SATURATION,
    WHITE_HUE,
    WHITE_SATURATION,
)
from .effects import EFFECT_LIST, EFFECTS, LEGACY_EFFECT_ALIASES
from .entity import MrStarEntity

MODE_COLOR = "color"
MODE_EFFECT = "effect"


@dataclass
class MrStarLightExtraData(ExtraStoredData):
    """What the light last drove the garland with.

    Home Assistant always records both the colour and the effect attribute, so
    the restored state alone cannot say which of the two the garland is
    actually showing. Recording it explicitly keeps the integration from
    pushing an effect the user never asked for on every restart.
    """

    mode: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the restore store."""
        return {"mode": self.mode}


def _device_brightness(brightness: int) -> int:
    """Convert Home Assistant's 1-255 to the firmware's 3-1000.

    mr_star_ble computes int(1024 * fraction) and so sends 1024 at full
    brightness, which is above anything the vendor app sends.
    """
    level = round(brightness / 255 * MAX_DEVICE_BRIGHTNESS)
    return min(max(level, MIN_DEVICE_BRIGHTNESS), MAX_DEVICE_BRIGHTNESS)


def _device_color(hue: float, saturation: float) -> tuple[int, int]:
    """Convert Home Assistant's hue and saturation to the firmware's units.

    Saturation goes out as 0-1000. The vendor app never sends 0: its white
    preset is RGB 255,254,255, which lands on hue 300 with a saturation of 3,
    and it explicitly clamps the fully desaturated case away. Zero saturation
    is therefore treated as a value the firmware is not known to accept.
    """
    device_hue = int(round(hue)) % 361
    device_saturation = int(round(saturation * 10))
    if device_saturation < MIN_DEVICE_SATURATION:
        return WHITE_HUE, WHITE_SATURATION
    return device_hue, min(device_saturation, 1000)


async def _write_color(api: MrStarAPI, hue: int, saturation: int) -> None:
    """Send a colour command in the firmware's own units.

    Built here rather than through MrStarAPI.set_hs_color, which takes
    saturation as 0-100 and scales it internally. Going through the frame
    directly keeps the encoding in one place, next to the clamp it depends on.
    """
    await api.write(
        format_command(
            Command.SET_COLOR,
            bytes(
                [
                    hue // 256,
                    hue % 256,
                    saturation // 256,
                    saturation % 256,
                    0x00,
                    0x00,
                ]
            ),
        )
    )


async def _write_brightness(api: MrStarAPI, level: int) -> None:
    """Send a brightness command with the firmware's own scale."""
    await api.write(
        format_command(
            Command.SET_BRIGHTNESS,
            bytes([level // 256, level % 256, 0x00, 0x00, 0x00, 0x00]),
        )
    )


async def _write_effect(api: MrStarAPI, mode: int) -> None:
    """Send an effect command by raw mode number.

    Raw numbers rather than mr_star_ble's Effect enum, because the enum is
    missing thirteen modes the vendor app offers.
    """
    await api.write(
        format_command(Command.SET_EFFECT, bytes([mode // 256, mode % 256]))
    )


def _resolve_effect(name: str) -> int | None:
    """Map a display name, current or legacy, to a firmware mode number."""
    if name in EFFECTS:
        return EFFECTS[name]
    return LEGACY_EFFECT_ALIASES.get(name)


async def async_setup_entry(
    hass: HomeAssistant,  # pylint: disable=unused-argument
    entry: MrStarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the garland light."""
    async_add_entities([MrStarLightEntity(entry)])


class MrStarLightEntity(MrStarEntity, LightEntity, RestoreEntity):
    """The garland itself, as a light."""

    _attr_name = "Light"
    _attr_icon = "mdi:led-strip-variant"
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = {ColorMode.HS}
    _attr_supported_features = LightEntityFeature.EFFECT
    _attr_effect_list = EFFECT_LIST

    def __init__(self, entry: MrStarConfigEntry) -> None:
        """Initialise the light."""
        data = entry.runtime_data
        super().__init__(data.coordinator, data.device_info, data.address)
        self._attr_unique_id = f"{data.address}_light"
        self._attr_is_on = False
        self._attr_brightness = 255
        self._attr_hs_color = (0.0, 0.0)
        self._attr_effect = None
        self._mode = MODE_COLOR

    @property
    def extra_restore_state_data(self) -> MrStarLightExtraData:
        """Record whether the garland is showing a colour or an effect."""
        return MrStarLightExtraData(self._mode)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the garland on and apply any requested attributes."""
        async with self.coordinator as api:
            light = self.assert_connected(api)
            if not self._attr_is_on:
                await light.set_power(True)
                self._attr_is_on = True

            if ATTR_BRIGHTNESS in kwargs:
                brightness = int(kwargs[ATTR_BRIGHTNESS])
                await _write_brightness(light, _device_brightness(brightness))
                self._attr_brightness = brightness

            if ATTR_HS_COLOR in kwargs:
                hue, saturation = kwargs[ATTR_HS_COLOR]
                await _write_color(light, *_device_color(hue, saturation))
                self._attr_hs_color = (float(hue), float(saturation))
                self._attr_effect = None
                self._mode = MODE_COLOR

            if ATTR_EFFECT in kwargs:
                name = kwargs[ATTR_EFFECT]
                mode = _resolve_effect(name)
                if mode is None:
                    raise HomeAssistantError(f"Unknown effect: {name}")
                await _write_effect(light, mode)
                self._attr_effect = name
                self._mode = MODE_EFFECT

        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the garland off."""
        async with self.coordinator as api:
            light = self.assert_connected(api)
            await light.set_power(False)
        self._attr_is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previous state and re-apply it once connected."""
        await super().async_added_to_hass()

        state = await self.async_get_last_state()
        if state is None:
            return

        extra = await self.async_get_last_extra_data()
        stored = extra.as_dict() if extra else {}
        self._mode = stored.get("mode", MODE_COLOR)

        attributes: dict[str, Any] = {}
        if brightness := state.attributes.get(ATTR_BRIGHTNESS):
            self._attr_brightness = int(brightness)
            attributes[ATTR_BRIGHTNESS] = self._attr_brightness

        if self._mode == MODE_EFFECT:
            effect = state.attributes.get(ATTR_EFFECT)
            if effect and _resolve_effect(effect) is not None:
                self._attr_effect = effect
                attributes[ATTR_EFFECT] = effect
            else:
                self._mode = MODE_COLOR
        if self._mode == MODE_COLOR:
            self._attr_effect = None
            if hs_color := state.attributes.get(ATTR_HS_COLOR):
                self._attr_hs_color = (float(hs_color[0]), float(hs_color[1]))
                attributes[ATTR_HS_COLOR] = self._attr_hs_color

        if state.state == "on":
            self._attr_is_on = True
            self.coordinator.run_when_connected(
                lambda: self._async_restore_on(attributes)
            )
        else:
            self._attr_is_on = False
            self.coordinator.run_when_connected(self.async_turn_off)

        self.async_write_ha_state()

    async def _async_restore_on(self, attributes: dict[str, Any]) -> None:
        """Re-apply the restored on-state to the device."""
        self._attr_is_on = False
        await self.async_turn_on(**attributes)
