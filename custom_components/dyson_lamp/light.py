"""Light platform for the Dyson Lightcycle Morph."""

from __future__ import annotations

import asyncio
import logging
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

from .connection import ConnectionManager
from .const import (
    COLOR_TEMP_MAX,
    COLOR_TEMP_MIN,
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
    EFFECTS,
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
    poller = data["poller"]
    serial = data["serial"]

    async_add_entities([DysonLight(poller, manager, serial)], update_before_add=True)

    # Immediate first read so entities show real values right away.
    await poller.poll_once()


class DysonLight(LightEntity):
    """Representation of the Dyson Lightcycle Morph as a light."""

    _attr_has_entity_name = True
    _attr_available = True
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = COLOR_TEMP_MIN
    _attr_max_color_temp_kelvin = COLOR_TEMP_MAX
    _attr_supported_features = LightEntityFeature.EFFECT

    def __init__(self, poller, manager: ConnectionManager, serial: str) -> None:
        self._poller = poller
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

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._poller.async_add_listener(self._on_state_update))
        self._on_state_update()

    def _on_state_update(self) -> None:
        self.async_write_ha_state()

    @property
    def lamp_state(self):
        return self._poller.lamp_state

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
        # Optimistically reflect ON right away so the UI doesn't flicker back
        # to OFF while the lamp applies the power bit.
        await self._set_optimistic(on=True)
        await asyncio.sleep(0.6)
        await self._poller.request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        lamp = await self._manager.ensure_connection()
        await lamp.set_power(False)
        await self._set_optimistic(on=False)
        await asyncio.sleep(0.6)
        await self._poller.request_refresh()

    async def _set_optimistic(self, on: bool) -> None:
        poller = self._poller
        state = poller.lamp_state
        if state is None:
            return
        # Reflect the new power state immediately; the next poll reconciles.
        poller.lamp_state.is_on = on
        self.async_write_ha_state()
