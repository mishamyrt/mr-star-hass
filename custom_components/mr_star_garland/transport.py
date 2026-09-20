"""Write transport for MR Star garlands.

The vendor Android app writes every command through FastBLE with
WRITE_TYPE_DEFAULT, which is a write with response, and Android serialises GATT
operations so the next command is not issued until the previous one has been
acknowledged. mr_star_ble instead writes without response and does not
serialise, which leaves the firmware free to drop commands that arrive while it
is still busy with the previous one.

This adapter gives MrStarAPI the same semantics as the vendor app: one write at
a time, acknowledged, with a floor on the interval between commands. It exposes
only the two attributes MrStarAPI touches, so it can be handed to it in place of
a BleakClient.

See PROTOCOL.md for how this was established.
"""

from __future__ import annotations

import asyncio
from logging import Logger
from typing import Any

from bleak import BleakClient

from .const import MIN_WRITE_INTERVAL_SECONDS, WRITE_CHARACTERISTIC


class PacedWriter:
    """Serialises and paces writes to the garland."""

    def __init__(
        self,
        client: BleakClient,
        logger: Logger,
        min_interval: float = MIN_WRITE_INTERVAL_SECONDS,
    ) -> None:
        """Wrap a connected client."""
        self._client = client
        self._logger = logger
        self._min_interval = min_interval
        self._lock = asyncio.Lock()
        self._next_write_at = 0.0
        self._with_response = self._supports_write_with_response()

    @property
    def is_connected(self) -> bool:
        """Mirror the client's connection state, for MrStarAPI."""
        return self._client.is_connected

    def _supports_write_with_response(self) -> bool:
        """Check the characteristic advertises the plain write property."""
        try:
            characteristic = self._client.services.get_characteristic(
                WRITE_CHARACTERISTIC
            )
        except Exception:  # pylint: disable=broad-except
            return False
        if characteristic is None:
            return False
        return "write" in characteristic.properties

    async def write_gatt_char(
        self, char_specifier: Any, data: bytes, response: bool = False
    ) -> None:
        """Write one command, acknowledged and paced.

        The caller's `response` argument is ignored on purpose: mr_star_ble
        always passes False, and the vendor app always writes with response.
        """
        del response
        async with self._lock:
            loop = asyncio.get_running_loop()
            wait = self._next_write_at - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            await self._client.write_gatt_char(
                char_specifier, data, response=self._with_response
            )
            self._next_write_at = loop.time() + self._min_interval
