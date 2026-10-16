"""Button platform for the Dyson Lightcycle Morph (wake-up & solar sync)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity
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
    """Set up Dyson action buttons."""
    data = hass.data[DOMAIN][entry.entry_id]
    manager: ConnectionManager = data["manager"]
    serial = data["serial"]

    async_add_entities(
        [
            SolarSyncButton(manager, serial),
            WakeUpButton(manager, serial),
        ],
        update_before_add=True,
    )


class DysonButton(ButtonEntity):
    """Base action button for the lamp."""

    _attr_has_entity_name = True

    def __init__(self, manager: ConnectionManager, serial: str, unique_suffix: str, display: str) -> None:
        self._manager = manager
        self._serial = serial
        self._attr_unique_id = f"dyson_lamp_{serial}_button_{unique_suffix}"
        self._attr_name = display

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=f"{DEVICE_NAME} {self._serial}",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )


class SolarSyncButton(DysonButton):
    """Push current GPS location/timezone to the onboard solar tracker."""

    def __init__(self, manager: ConnectionManager, serial: str) -> None:
        super().__init__(manager, serial, "sync_location", "Sync Solar Location")

    async def async_press(self) -> None:
        hass = self.hass
        lat = hass.config.latitude
        lon = hass.config.longitude
        tz = str(hass.config.time_zone)
        lamp = await self._manager.ensure_connection()
        await lamp.sync_solar_location(latitude=lat, longitude=lon, timezone_str=tz)


class WakeUpButton(DysonButton):
    """Run the sunrise wake-up routine (in the background)."""

    def __init__(
        self,
        manager: ConnectionManager,
        serial: str,
        duration: int = 1800,
        lumens: int = 800,
        kelvin: int = 4800,
    ) -> None:
        super().__init__(manager, serial, "wakeup", "Wake Up")
        self._duration = duration
        self._lumens = lumens
        self._kelvin = kelvin

    async def async_press(self) -> None:
        self._manager.start_wakeup(self._duration, self._lumens, self._kelvin)
