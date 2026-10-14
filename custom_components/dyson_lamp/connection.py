"""Connection manager for the Dyson Lightcycle Morph.

Mediates access to the lamp's BLE connection and implements the two
operating modes the user can choose from:

* ``persistent`` (default): keep the BLE connection open continuously for
  minimal latency and live contact to the lamp.
* ``app_compatible``: only connect when an action needs the lamp and
  disconnect again after a short inactivity period so the official Dyson
  app can claim the connection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .const import MODE_APP_COMPATIBLE, MODE_PERSISTENT
from .lamp import LampClient

_LOGGER = logging.getLogger(__name__)

# How long the connection is kept open after the last activity in
# app_compatible mode.
APP_COMPATIBLE_IDLE_SECONDS = 90


class ConnectionManager:
    """Owns the LampClient and disconnects based on the active mode."""

    def __init__(
        self,
        hass,
        address: str,
        user_id: str,
        ltk_hex: str,
        mode: str = MODE_PERSISTENT,
        idle_seconds: int = APP_COMPATIBLE_IDLE_SECONDS,
    ) -> None:
        self._hass = hass
        self._lamp = LampClient(address, user_id, ltk_hex)
        self._mode = mode
        self._idle_seconds = idle_seconds
        self._lock = asyncio.Lock()
        self._idle_task: Optional[asyncio.Task] = None

    @property
    def lamp(self) -> LampClient:
        """The underlying LampClient (for direct access)."""
        return self._lamp

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Switch the connection mode at runtime."""
        self._mode = mode
        if mode == MODE_APP_COMPATIBLE:
            self._schedule_idle_disconnect()
        _LOGGER.debug("Connection mode set to %s", mode)

    @property
    def is_connected(self) -> bool:
        return self._lamp.client is not None and self._lamp.client.is_connected

    async def close(self) -> None:
        """Tear down the connection and any idle task."""
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
        await self._lamp.disconnect()

    def _schedule_idle_disconnect(self) -> None:
        if self._idle_task:
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._idle_disconnect())

    async def _idle_disconnect(self) -> None:
        await asyncio.sleep(self._idle_seconds)
        await self._lamp.disconnect()
        self._idle_task = None
        _LOGGER.debug("App-compatible mode: disconnected after idle")

    async def ensure_connection(self, timeout: float = 15.0) -> LampClient:
        """Return an authenticated LampClient, connecting if needed.

        Call this from entities/services before performing an action. In
        app_compatible mode the connection is dropped again after an idle
        period.
        """
        async with self._lock:
            if self._mode == MODE_PERSISTENT:
                if not self.is_connected:
                    await self._lamp.connect(timeout=timeout, hass=self._hass)
                return self._lamp

            # App-compatible: connect only for the action.
            if not self.is_connected:
                await self._lamp.connect(timeout=timeout, hass=self._hass)
            self._schedule_idle_disconnect()
            return self._lamp
