"""Sensor platform for the Dyson Lightcycle Morph (numeric status)."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLuminousFlux, UnitOfTemperature
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
    """Set up Dyson numeric status sensors."""
    data = hass.data[DOMAIN][entry.entry_id]
    manager = data["manager"]
    serial = data["serial"]
    coordinator = data["coordinator"]

    async_add_entities(
        [
            DysonBrightnessSensor(coordinator, manager, serial),
            DysonColorTempSensor(coordinator, manager, serial),
        ],
        update_before_add=True,
    )


class DysonSensorBase(SensorEntity):
    """Shared device/property logic for Dyson status sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, manager, serial: str) -> None:
        self._coordinator = coordinator
        self._manager = manager
        self._serial = serial
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
        self._update_from_state(state)
        if state is not None:
            self._attr_available = True
        self.async_write_ha_state()

    def _update_from_coordinator(self) -> None:
        state = self._coordinator.lamp_state
        self._attr_available = state is not None
        self._update_from_state(state)
        self.async_write_ha_state()

    def _update_from_state(self, state) -> None:
        """Map lamp_state -> entity attrs (override)."""


class DysonBrightnessSensor(DysonSensorBase):
    """Current lamp brightness in lumens."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLuminousFlux.LUMENS

    def __init__(self, coordinator, manager, serial: str) -> None:
        super().__init__(coordinator, manager, serial)
        self._attr_unique_id = f"dyson_lamp_{serial}_sensor_brightness"
        self._attr_name = "Brightness"

    def _update_from_state(self, state) -> None:
        if state is not None:
            self._attr_native_value = state.brightness


class DysonColorTempSensor(DysonSensorBase):
    """Current lamp color temperature in Kelvin."""

    _attr_device_class = SensorDeviceClass.COLOR_TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.KELVIN

    def __init__(self, coordinator, manager, serial: str) -> None:
        super().__init__(coordinator, manager, serial)
        self._attr_unique_id = f"dyson_lamp_{serial}_sensor_color_temp"
        self._attr_name = "Color Temperature"

    def _update_from_state(self, state) -> None:
        if state is not None:
            self._attr_native_value = state.color_temp
