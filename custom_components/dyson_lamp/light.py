"""Light platform for the Dyson Lightcycle Morph."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .connection import ConnectionManager
from .const import (
    COLOR_TEMP_MAX,
    COLOR_TEMP_MIN,
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
    EFFECTS,
    MODE_APP_COMPATIBLE,
    MODE_PERSISTENT,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Dyson light entity."""
    data = hass.data[DOMAIN][entry.entry_id]
    manager: ConnectionManager = data["manager"]
    coordinator: DysonLampCoordinator = data["coordinator"]
    serial = data["serial"]

    async_add_entities([DysonLight(coordinator, manager, serial)], update_before_add=True)

    # Trigger the first state read. Subsequent refreshes happen on the
    # coordinator's update interval (persistent mode) or on demand.
    await coordinator.async_refresh()


class DysonLampCoordinator(DataUpdateCoordinator[None]):
    """Keep the lamp state fresh, respecting the connection mode.

    In persistent mode a periodic poll holds the connection and refreshes
    state. In app-compatible mode we only poll when explicitly asked so the
    connection is not kept alive permanently.
    """

    def __init__(self, hass: HomeAssistant, manager: ConnectionManager) -> None:
        self.manager = manager
        self._lock = asyncio.Lock()
        self.lamp_state = None
        super().__init__(
            hass,
            _LOGGER,
            name="Dyson Lamp",
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        if manager.mode == MODE_APP_COMPATIBLE:
            # In app-compatible mode periodic polling would keep BLE alive.
            self.update_interval = None

    def set_mode(self, mode: str) -> None:
        if mode == MODE_PERSISTENT:
            self.update_interval = timedelta(seconds=SCAN_INTERVAL_SECONDS)
        else:
            self.update_interval = None

    async def _async_update_data(self) -> None:
        try:
            await self._refresh()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Error communicating with Dyson lamp: {err}") from err

    async def refresh_now(self) -> None:
        """One-off state read (used by app-compatible mode and after actions)."""
        async with self._lock:
            try:
                await self._refresh()
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not refresh Dyson lamp state: %s", err)

    async def _refresh(self) -> None:
        async with self._lock:
            lamp = await self.manager.ensure_connection(timeout=15)
            self.lamp_state = await lamp.get_state()
            self.async_update_listeners()


class DysonLight(LightEntity):
    """Representation of the Dyson Lightcycle Morph as a light."""

    _attr_has_entity_name = True
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = COLOR_TEMP_MIN
    _attr_max_color_temp_kelvin = COLOR_TEMP_MAX
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, coordinator: DysonLampCoordinator, manager: ConnectionManager, serial: str) -> None:
        self._coordinator = coordinator
        self._manager = manager
        self._serial = serial
        self._attr_unique_id = f"dyson_lamp_{serial}_light"
        self._attr_name = "Light"
        self._attr_effect_list = list(EFFECTS.keys())

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=f"{DEVICE_NAME} {self._serial}",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )

    @property
    def available(self) -> bool:
        return self._coordinator.last_update_success or self.lamp_state is not None

    @property
    def lamp_state(self):
        return self._coordinator.lamp_state

    @property
    def is_on(self) -> bool | None:
        return self.lamp_state.is_on if self.lamp_state else None

    @property
    def brightness(self) -> int | None:
        if not self.lamp_state:
            return None
        return int(round((self.lamp_state.brightness - 100) / 900 * 255))

    @property
    def color_temp_kelvin(self) -> int | None:
        return self.lamp_state.color_temp if self.lamp_state else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        lamp = await self._manager.ensure_connection()
        if ATTR_BRIGHTNESS in kwargs:
            await lamp.set_brightness(int(round(kwargs[ATTR_BRIGHTNESS] / 255 * 900 + 100)))
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            await lamp.set_color_temp(int(kwargs[ATTR_COLOR_TEMP_KELVIN]))
        if ATTR_EFFECT in kwargs:
            await lamp.set_mode(EFFECTS[kwargs[ATTR_EFFECT]])
        await lamp.set_power(True)
        await self._coordinator.refresh_now()

    async def async_turn_off(self, **kwargs: Any) -> None:
        lamp = await self._manager.ensure_connection()
        await lamp.set_power(False)
        await self._coordinator.refresh_now()
