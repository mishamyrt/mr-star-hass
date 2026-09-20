"""BLE session coordinator for MR Star garlands.

The coordinator owns a single Bluetooth session per device. It keeps that
session alive, recycles it once the TTL expires, and publishes connection
state to the entities. Entities borrow the API object through the async
context manager, which serialises access with a lock.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from contextlib import suppress
from logging import Logger
from typing import Any

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    close_stale_connections_by_address,
    establish_connection,
)
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from mr_star_ble import MrStarAPI

from .const import (
    CONNECTION_TIMEOUT_SECONDS,
    RECONNECT_BACKOFF_SECONDS,
    SESSION_TTL_SECONDS,
    STOP_TIMEOUT_SECONDS,
)
from .transport import PacedWriter


class MrStarCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns the BLE session to a single MR Star garland."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: Logger,
        address: str,
        ttl: float = SESSION_TTL_SECONDS,
    ) -> None:
        """Initialise the coordinator.

        No polling interval is set: connection state is pushed from the
        session task, so there is nothing to poll for.
        """
        super().__init__(hass, logger, name=f"mr_star {address}", update_interval=None)
        self._address = address
        self._ttl = ttl
        self._connection_timeout: float = CONNECTION_TIMEOUT_SECONDS
        self._client: BleakClientWithServiceCache | None = None
        self._writer: PacedWriter | None = None
        self._lock = asyncio.Lock()
        self._stopping = asyncio.Event()
        self._connected = asyncio.Event()
        self._session_task: asyncio.Task[None] | None = None
        self._pending_tasks: set[asyncio.Task[None]] = set()
        self.data = {"connected": False}

    @property
    def address(self) -> str:
        """Return the Bluetooth address of the garland."""
        return self._address

    @property
    def is_connected(self) -> bool:
        """Return whether a usable session to the garland exists."""
        return (
            self._client is not None
            and self._client.is_connected
            and self._connected.is_set()
        )

    async def __aenter__(self) -> MrStarAPI | None:
        """Borrow the device API, or None when there is no session."""
        await self._lock.acquire()
        if not self.is_connected or self._writer is None:
            self.logger.debug("No session to garland %s", self._address)
            return None
        return MrStarAPI(self._writer)

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Return the device API."""
        self._lock.release()

    async def start(
        self,
        await_connected: bool = False,
        connection_timeout: float = CONNECTION_TIMEOUT_SECONDS,
    ) -> None:
        """Start the session task."""
        self._connection_timeout = connection_timeout
        self._stopping.clear()
        self._session_task = self.hass.async_create_background_task(
            self._run_session(), name=f"mr_star_garland session {self._address}"
        )
        if await_connected:
            await self._connected.wait()

    async def stop(self) -> None:
        """Stop the session task and drop the connection.

        Always returns within STOP_TIMEOUT_SECONDS so that unloading or
        reloading the config entry cannot hang on an unreachable device.
        """
        self._stopping.set()
        for task in list(self._pending_tasks):
            task.cancel()
        self._pending_tasks.clear()

        task, self._session_task = self._session_task, None
        if task is None:
            return
        try:
            async with asyncio.timeout(STOP_TIMEOUT_SECONDS):
                await task
        except TimeoutError:
            self.logger.warning(
                "Session task for garland %s did not stop in time, cancelling",
                self._address,
            )
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    def run_when_connected(
        self, factory: Callable[[], Coroutine[Any, Any, None]]
    ) -> None:
        """Run a coroutine once the garland is connected.

        The coroutine is built only when it is about to run, so nothing is
        left un-awaited if the device is never reached.
        """

        async def runner() -> None:
            await self._connected.wait()
            await factory()

        task = self.hass.async_create_background_task(
            runner(), name=f"mr_star_garland restore {self._address}"
        )
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

    async def _run_session(self) -> None:
        """Hold a session open, reconnecting and recycling as needed."""
        try:
            while not self._stopping.is_set():
                if not await self._async_connect():
                    if await self._async_wait_for_stop(RECONNECT_BACKOFF_SECONDS):
                        break
                    continue
                if await self._async_wait_for_stop(self._ttl):
                    break
                self.logger.debug(
                    "Session TTL reached for garland %s, recycling", self._address
                )
        finally:
            await self._async_disconnect()

    async def _async_wait_for_stop(self, timeout: float) -> bool:
        """Wait up to timeout seconds for a stop request.

        Returns True when a stop was requested, False on timeout. This is
        what makes stop() responsive while the task is idling or backing off.
        """
        try:
            async with asyncio.timeout(timeout):
                await self._stopping.wait()
        except TimeoutError:
            return False
        return True

    async def _async_connect(self) -> bool:
        """Establish a session and publish the outcome.

        The outcome is published whether or not the attempt succeeded. A
        failed attempt has to reach the entities, otherwise they keep
        reporting themselves available on the strength of a session that is
        gone and every command raises instead of the device showing as
        unreachable.

        The intentional TTL recycle stays invisible: nothing is published
        between dropping the old session and opening the new one, so a
        recycle that succeeds publishes the same state it started from.
        """
        connected = await self._async_open_session()
        self._publish_state()
        return connected

    async def _async_open_session(self) -> bool:
        """Open a session. Returns True on success. Publishes nothing."""
        async with self._lock:
            await self._async_disconnect_locked()
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self._address.upper(), connectable=True
            )
            if ble_device is None:
                self.logger.debug(
                    "Garland %s is not in range of any adapter or proxy",
                    self._address,
                )
                return False
            try:
                await close_stale_connections_by_address(self._address.upper())
                self._client = await establish_connection(
                    BleakClientWithServiceCache,
                    ble_device,
                    self._address,
                    timeout=self._connection_timeout,
                )
            except (BleakError, TimeoutError) as exc:
                self.logger.debug(
                    "Could not connect to garland %s: %s", self._address, exc
                )
                self._client = None
                return False
            except Exception:  # pylint: disable=broad-except
                self.logger.exception(
                    "Unexpected error connecting to garland %s", self._address
                )
                self._client = None
                return False
            self._writer = PacedWriter(self._client, self.logger)
            self._connected.set()
            self.logger.debug("Connected to garland %s", self._address)
        return True

    async def _async_disconnect(self) -> None:
        """Drop the session and publish the new state."""
        async with self._lock:
            await self._async_disconnect_locked()
        self._publish_state()

    async def _async_disconnect_locked(self) -> None:
        """Drop the session. The caller must hold the lock."""
        client, self._client = self._client, None
        self._writer = None
        self._connected.clear()
        if client is None:
            return
        try:
            await client.disconnect()
        except BleakError as exc:
            self.logger.debug(
                "Error disconnecting from garland %s: %s", self._address, exc
            )

    def _publish_state(self) -> None:
        """Push connection state to the entities."""
        self.async_set_updated_data({"connected": self.is_connected})

    async def _async_update_data(self) -> dict[str, Any]:
        """Return current state. Only used if a refresh is requested."""
        return {"connected": self.is_connected}
