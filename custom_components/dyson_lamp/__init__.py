"""Dyson Lightcycle Morph integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .connection import ConnectionManager
from .poller import StatusPoller
from .const import (
    CONF_ADDRESS,
    CONF_LTK,
    CONF_MODE,
    CONF_SERIAL,
    CONF_USER_ID,
    DOMAIN,
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DEVICE_NAME,
    MODE_PERSISTENT,
)

_LOGGER = logging.getLogger(__name__)

PLATFORM_LIST = [
    Platform.LIGHT,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Dyson lamp from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    manager = ConnectionManager(
        hass,
        address=entry.data[CONF_ADDRESS],
        user_id=entry.data[CONF_USER_ID],
        ltk_hex=entry.data[CONF_LTK],
        mode=entry.options.get(CONF_MODE, entry.data.get(CONF_MODE, MODE_PERSISTENT)),
    )

    serial = entry.data.get(CONF_SERIAL, entry.data[CONF_ADDRESS])

    # The poller is shared by all platforms (light, sensors, switches...) and
    # drives periodic status updates. It is created here, before any platform.
    poller = StatusPoller(manager)

    # Register the device in the device registry so all entities group under it.
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, serial)},
        name=f"{DEVICE_NAME} {serial}",
        manufacturer=DEVICE_MANUFACTURER,
        model=DEVICE_MODEL,
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "manager": manager,
        "poller": poller,
        "serial": serial,
        "unloaded": False,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORM_LIST)
    _register_services(hass)

    # Start periodic status polling and keep the connection alive in
    # persistent mode.
    if manager.mode == MODE_PERSISTENT:
        await manager.ensure_connection()
    await poller.start()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    poller: StatusPoller | None = data.get("poller")
    if poller:
        await poller.stop()
    manager: ConnectionManager | None = data.get("manager")
    if manager:
        await manager.close()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORM_LIST)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry (used when options change)."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle config entry migrations."""
    return True


def _register_services(hass: HomeAssistant) -> None:
    """Register domain-wide services acting on the configured lamp(s)."""
    if hass.services.has_service(DOMAIN, "sync_location"):
        return

    async def _get_manager():
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            return None
        return next(iter(entries.values()))["manager"]

    async def _sync_location(call) -> None:
        manager = await _get_manager()
        if manager is None:
            return
        lamp = await manager.ensure_connection()
        await lamp.sync_solar_location(
            latitude=call.data.get("latitude"),
            longitude=call.data.get("longitude"),
            timezone_str=call.data.get("timezone", "Europe/Berlin"),
        )

    async def _set_wakeup(call) -> None:
        manager = await _get_manager()
        if manager is None:
            return
        lamp = await manager.ensure_connection()
        duration_min = float(call.data.get("duration", 30))
        await lamp.run_wakeup(
            duration_sec=int(duration_min * 60),
            target_lumens=int(call.data.get("lumens", 800)),
            target_kelvin=int(call.data.get("kelvin", 4800)),
        )

    hass.services.async_register(DOMAIN, "sync_location", _sync_location)
    hass.services.async_register(DOMAIN, "set_wakeup", _set_wakeup)
