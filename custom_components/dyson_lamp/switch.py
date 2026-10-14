"""Switch platform for the Dyson Lightcycle Morph (sensors)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .connection import ConnectionManager
from .const import (
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dyson sensor switches."""
    data = hass.data[DOMAIN][entry.entry_id]
    manager: ConnectionManager = data["manager"]
    serial = data["serial"]
    coordinator = data["light_coordinator"]

    async_add_entities(
        [
            DysonSwitch(
                coordinator,
                manager,
                serial,
                "auto_brightness",
                "Auto-Brightness (Ambient Light Sensor)",
                "auto_brightness",
            ),
            DysonSwitch(
                coordinator,
                manager,
                serial,
                "movement_sensor",
                "Movement Sensor (PIR)",
                "movement_sensor",
            ),
        ],
        update_before_add=True,
    )


class DysonSwitch(SwitchEntity):
    """A toggleable Dyson sensor mode (auto-brightness / movement)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, manager: ConnectionManager, serial: str, key: str, display: str, setter: str) -> None:
        self._coordinator = coordinator
        self._manager = manager
        self._serial = serial
        self._key = key
        self._setter = setter
        self._attr_unique_id = f"dyson_lamp_{serial}_switch_{key}"
        self._attr_name = display

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=f"{DEVICE_NAME} {self._serial}",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )

    @property
    def is_on(self) -> bool | None:
        state = self._coordinator.lamp_state
        if not state:
            return None
        return getattr(state, self._key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        lamp = await self._manager.ensure_connection()
        await getattr(lamp, f"set_{self._setter}")(True)
        await self._coordinator.refresh_now()

    async def async_turn_off(self, **kwargs: Any) -> None:
        lamp = await self._manager.ensure_connection()
        await getattr(lamp, f"set_{self._setter}")(False)
        await self._coordinator.refresh_now()
