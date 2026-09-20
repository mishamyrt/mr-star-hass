"""LED count entity for MR Star garlands."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, RestoreNumber
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MrStarConfigEntry
from .const import DEFAULT_LED_COUNT, MAX_LED_COUNT, MIN_LED_COUNT
from .entity import MrStarEntity


async def async_setup_entry(
    hass: HomeAssistant,  # pylint: disable=unused-argument
    entry: MrStarConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the LED count entity."""
    async_add_entities([LEDCountEntity(entry)])


class LEDCountEntity(MrStarEntity, RestoreNumber, NumberEntity):
    """Number of LEDs the garland firmware should drive."""

    _attr_name = "LED count"
    _attr_icon = "mdi:counter"
    _attr_native_step = 1
    _attr_native_min_value = MIN_LED_COUNT
    _attr_native_max_value = MAX_LED_COUNT

    def __init__(self, entry: MrStarConfigEntry) -> None:
        """Initialise the entity."""
        data = entry.runtime_data
        super().__init__(data.coordinator, data.device_info, data.address)
        self._attr_unique_id = f"{data.address}_led_count"
        self._attr_native_value = float(DEFAULT_LED_COUNT)

    async def async_set_native_value(self, value: float) -> None:
        """Write the LED count to the device."""
        async with self.coordinator as api:
            light = self.assert_connected(api)
            await light.set_length(int(value))
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previous value and re-apply it once connected."""
        await super().async_added_to_hass()

        data = await self.async_get_last_number_data()
        if data is None or data.native_value is None:
            return

        value = min(max(float(data.native_value), MIN_LED_COUNT), MAX_LED_COUNT)
        self._attr_native_value = value
        self.async_write_ha_state()
        self.coordinator.run_when_connected(
            lambda: self.async_set_native_value(value)
        )
