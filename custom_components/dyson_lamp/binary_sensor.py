"""Binary sensor platform for the Dyson Lightcycle Morph (on/off status)."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_MANUFACTURER, DEVICE_MODEL, DEVICE_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dyson on/off status entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    manager = data["manager"]
    serial = data["serial"]
    coordinator = data["coordinator"]

    async_add_entities(
        [
            DysonBinarySensor(coordinator, manager, serial, "is_on", "Power"),
            DysonBinarySensor(
                coordinator, manager, serial, "movement_sensor", "Movement Sensor"
            ),
        ],
        update_before_add=True,
    )


class DysonBinarySensor(BinarySensorEntity):
    """A binary (on/off) status read from the lamp."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, manager, serial: str, key: str, display: str) -> None:
        self._coordinator = coordinator
        self._manager = manager
        self._serial = serial
        self._key = key
        self._attr_unique_id = f"dyson_lamp_{serial}_binary_{key}"
        self._attr_name = display
        self._attr_is_on = None
        self._attr_available = False

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=f"{DEVICE_NAME} {self._serial}",
            manufacturer=DEVICE_MANUFACTURER,
            model=DEVICE_MODEL,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self._coordinator.async_add_listener(self._update_from_coordinator)
        )
        state = self._coordinator.lamp_state
        self._attr_available = state is not None
        if state is not None:
            self._attr_is_on = bool(getattr(state, self._key))
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        state = self._coordinator.lamp_state
        self._attr_available = state is not None
        if state is not None:
            self._attr_is_on = bool(getattr(state, self._key))
        self.async_write_ha_state()
