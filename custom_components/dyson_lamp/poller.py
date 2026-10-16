"""Robust periodic status poller for the Dyson Lightcycle Morph.

The built-in DataUpdateCoordinator stops periodic refresh after repeated
failures (backoff/task-killer behaviour), which left the status entities
stale. This poller keeps polling forever, recovers from blips, and notifies
registered listeners after each successful read.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Optional

from .connection import ConnectionManager
from .const import SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

DEFAULT_INTERVAL = SCAN_INTERVAL_SECONDS


class StatusPoller:
    """Periodically read the lamp state and notify listeners."""

    def __init__(self, manager: ConnectionManager, interval: float = DEFAULT_INTERVAL) -> None:
        self.manager = manager
        self.interval = interval
        self.lamp_state = None
        self._listeners: list[Callable[[], None]] = []
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Begin periodic polling (immediate first read, then on interval)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        while True:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Dyson status poll failed (will retry): %s", err)
            await asyncio.sleep(self.interval)

    async def poll_once(self) -> None:
        """Read the lamp state once and notify listeners on success."""
        async with self._lock:
            try:
                async def _read():
                    lamp = await self.manager.ensure_connection(timeout=15)
                    return await lamp.get_state()

                # Hard timeout so a hung BLE read can never stall polling.
                self.lamp_state = await asyncio.wait_for(_read(), timeout=60)
                self._notify()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not read Dyson lamp state: %s", repr(err))
                # Drop a possibly broken link so the next poll reconnects cleanly.
                try:
                    await self.manager.reset_connection()
                except Exception:  # noqa: BLE001
                    pass

    async def request_refresh(self) -> None:
        """Read state immediately (e.g. right after a command)."""
        await self.poll_once()

    def async_add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a listener invoked after each successful state read."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Listener error in Dyson status poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None
