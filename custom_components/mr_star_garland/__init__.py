"""The MR Star Garland integration."""

from __future__ import annotations

from dataclasses import dataclass
from logging import getLogger

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo

from .const import CONNECTION_TIMEOUT_SECONDS, DOMAIN
from .coordinator import MrStarCoordinator

_LOGGER = getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.NUMBER]


@dataclass
class MrStarRuntimeData:
    """Everything the platforms need from the config entry."""

    coordinator: MrStarCoordinator
    device_info: DeviceInfo
    address: str


type MrStarConfigEntry = ConfigEntry[MrStarRuntimeData]


def short_id(address: str) -> str:
    """Return the short device label derived from the address.

    Kept identical to the original implementation so device and entity
    names do not change for existing installations.
    """
    return address[len(address) - 5 :].replace(":", "")


async def async_setup_entry(hass: HomeAssistant, entry: MrStarConfigEntry) -> bool:
    """Set up a garland from a config entry."""
    address: str = entry.data[CONF_ADDRESS]

    _async_migrate_unique_ids(hass, entry, address)

    coordinator = MrStarCoordinator(hass, _LOGGER, address)
    await coordinator.start(
        await_connected=False, connection_timeout=CONNECTION_TIMEOUT_SECONDS
    )

    entry.runtime_data = MrStarRuntimeData(
        coordinator=coordinator,
        device_info=DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            name=f"Garland {short_id(address)}",
            manufacturer="MR Star",
            model="Curtain",
        ),
        address=address,
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MrStarConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.coordinator.stop()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: MrStarConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_migrate_unique_ids(
    hass: HomeAssistant, entry: MrStarConfigEntry, address: str
) -> None:
    """Move entities off the old name-based unique IDs.

    The original unique IDs were display names built from the last two
    bytes of the address, which collide between devices. Registered
    entities are rewritten to address-based IDs so history is preserved.
    """
    device_id = short_id(address)
    migrations = {
        f"Garland {device_id} Light": f"{address}_light",
        f"Garland {device_id} LED count": f"{address}_led_count",
    }

    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        new_unique_id = migrations.get(registry_entry.unique_id)
        if new_unique_id is None:
            continue
        if registry.async_get_entity_id(
            registry_entry.domain, DOMAIN, new_unique_id
        ):
            _LOGGER.debug(
                "Skipping unique ID migration for %s, target ID already exists",
                registry_entry.entity_id,
            )
            continue
        _LOGGER.debug(
            "Migrating unique ID of %s from %s to %s",
            registry_entry.entity_id,
            registry_entry.unique_id,
            new_unique_id,
        )
        registry.async_update_entity(
            registry_entry.entity_id, new_unique_id=new_unique_id
        )
