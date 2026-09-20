"""Shared entity base for MR Star garlands."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from mr_star_ble import MrStarAPI

from .coordinator import MrStarCoordinator


class MrStarEntity(CoordinatorEntity[MrStarCoordinator]):
    """Common wiring for every entity backed by a garland session."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MrStarCoordinator,
        device_info: DeviceInfo,
        address: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._address = address
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        """Availability follows the BLE session, not the device state."""
        return bool(self.coordinator.data.get("connected"))

    def assert_connected(self, api: MrStarAPI | None) -> MrStarAPI:
        """Return the borrowed API, or raise a user-visible error."""
        if api is None:
            raise HomeAssistantError(f"Garland {self._address} is not connected")
        return api
