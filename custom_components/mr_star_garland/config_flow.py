"""Config flow for the MR Star Garland integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from bluetooth_data_tools import human_readable_name
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS
from mr_star_ble.const import LIGHT_SERVICE

from .const import CONNECTION_TIMEOUT_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MrStarConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MR Star garlands."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a garland found by the Bluetooth integration."""
        if LIGHT_SERVICE not in discovery_info.service_uuids:
            return self.async_abort(reason="not_supported")

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": human_readable_name(
                None, discovery_info.name, discovery_info.address
            )
        }
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick a discovered garland."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            discovery_info = self._discovered_devices[address]
            await self.async_set_unique_id(
                discovery_info.address, raise_on_progress=False
            )
            self._abort_if_unique_id_configured()
            try:
                await self._async_assert_device(discovery_info.device)
            except BleakError as exc:
                _LOGGER.debug("Could not reach garland %s: %s", address, exc)
                errors["base"] = "device_not_found"
            except TimeoutError:
                errors["base"] = "device_not_found"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected error connecting to garland %s", address)
                errors["base"] = "unknown_error"
            else:
                return self.async_create_entry(
                    title=discovery_info.name,
                    data={CONF_ADDRESS: discovery_info.address},
                )

        if discovery := self._discovery_info:
            self._discovered_devices[discovery.address] = discovery
        else:
            current_addresses = self._async_current_ids()
            for discovery in async_discovered_service_info(self.hass):
                if (
                    discovery.address in current_addresses
                    or discovery.address in self._discovered_devices
                    or LIGHT_SERVICE not in discovery.service_uuids
                ):
                    continue
                self._discovered_devices[discovery.address] = discovery

        if not self._discovered_devices:
            return self.async_abort(reason="devices_not_found")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS): vol.In(
                    {
                        service_info.address: (
                            f"{service_info.name} ({service_info.address})"
                        )
                        for service_info in self._discovered_devices.values()
                    }
                ),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def _async_assert_device(self, device: BLEDevice) -> None:
        """Connect to the garland once to prove it is reachable.

        Errors are allowed to propagate so the form can report them. The
        original implementation swallowed them and always reported success.
        """
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            device.address,
            timeout=CONNECTION_TIMEOUT_SECONDS,
        )
        await client.disconnect()
