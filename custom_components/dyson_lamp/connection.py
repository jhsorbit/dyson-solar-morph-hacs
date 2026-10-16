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
        self._wakeup_task: Optional[asyncio.Task] = None

    @property
    def wakeup_running(self) -> bool:
        """True while a wake-up ramp is in progress."""
        return self._wakeup_task is not None and not self._wakeup_task.done()

    def start_wakeup(self, duration_sec: int, lumens: int, kelvin: int) -> None:
        """Start the wake-up ramp in the background (replaces a running one)."""
        if self._wakeup_task and not self._wakeup_task.done():
            self._wakeup_task.cancel()
        self._wakeup_task = asyncio.create_task(
            self._run_wakeup(duration_sec, lumens, kelvin)
        )

    async def cancel_wakeup(self) -> bool:
        """Stop a running wake-up ramp. Returns True if one was running."""
        task = self._wakeup_task
        if task is None or task.done():
            return False
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _LOGGER.info("Dyson wake-up ramp cancelled")
        return True

    async def _run_wakeup(self, duration_sec: int, lumens: int, kelvin: int) -> None:
        try:
            lamp = await self.ensure_connection()
            await lamp.run_wakeup(
                duration_sec=duration_sec,
                target_lumens=lumens,
                target_kelvin=kelvin,
            )
            _LOGGER.info("Dyson wake-up routine finished")
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("Dyson wake-up routine failed: %s", err)

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
        await self.cancel_wakeup()
        if self._idle_task:
            self._idle_task.cancel()
            self._idle_task = None
        await self._lamp.disconnect()

    async def reset_connection(self) -> None:
        """Drop the BLE link (e.g. after a failed read) without stopping a ramp."""
        if self.wakeup_running:
            return
        await self._lamp.disconnect()

    def _schedule_idle_disconnect(self) -> None:
        if self._idle_task:
            self._idle_task.cancel()
        self._idle_task = asyncio.create_task(self._idle_disconnect())

    async def _idle_disconnect(self) -> None:
        await asyncio.sleep(self._idle_seconds)
        # Never drop the link in the middle of a wake-up ramp.
        while self.wakeup_running:
            await asyncio.sleep(5)
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
