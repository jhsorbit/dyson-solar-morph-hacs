"""Select platform for the Dyson Lightcycle Morph (preset modes)."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
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
    EFFECTS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dyson preset mode select."""
    data = hass.data[DOMAIN][entry.entry_id]
    manager: ConnectionManager = data["manager"]
    serial = data["serial"]
    coordinator = data["coordinator"]

    async_add_entities(
        [DysonModeSelect(coordinator, manager, serial)],
        update_before_add=True,
    )


class DysonModeSelect(SelectEntity):
    """Let the user pick a preset mode (sync/study/relax/precision)."""

    _attr_has_entity_name = True
    _attr_options = list(EFFECTS.keys())

    def __init__(self, coordinator, manager: ConnectionManager, serial: str) -> None:
        self._coordinator = coordinator
        self._manager = manager
        self._serial = serial
        self._attr_unique_id = f"dyson_lamp_{serial}_select_mode"
        self._attr_name = "Preset Mode"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=f"{DEVICE_NAME} {self._serial}",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )

    @property
    def current_option(self) -> str | None:
        return None

    async def async_select_option(self, option: str) -> None:
        lamp = await self._manager.ensure_connection()
        await lamp.set_mode(EFFECTS[option])
        await self._coordinator.refresh_now()
