"""Dyson Lightcycle Morph integration for Home Assistant."""

from __future__ import annotations

import asyncio
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
    DEVICE_MANUFACTURER,
    DEVICE_MODEL,
    DEVICE_NAME,
    DOMAIN,
    MODE_PERSISTENT,
    SOLAR_SYNC_INTERVAL_SECONDS,
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

    # Start periodic status polling, an initial+daily solar/location sync, and
    # keep the connection alive in persistent mode.
    if manager.mode == MODE_PERSISTENT:
        await manager.ensure_connection()
    await poller.start()
    sync_task = asyncio.create_task(_auto_solar_sync(hass, manager))
    hass.data[DOMAIN][entry.entry_id]["sync_task"] = sync_task

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    sync_task = data.get("sync_task")
    if sync_task:
        sync_task.cancel()
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
        duration_min = float(call.data.get("duration", 30))
        _LOGGER.info(
            "set_wakeup called: %.0f min, %s lm, %s K",
            duration_min,
            call.data.get("lumens", 800),
            call.data.get("kelvin", 4800),
        )
        # Runs in the background so the calling automation is not blocked.
        manager.start_wakeup(
            int(duration_min * 60),
            int(call.data.get("lumens", 800)),
            int(call.data.get("kelvin", 4800)),
        )

    async def _cancel_wakeup(call) -> None:
        manager = await _get_manager()
        if manager is not None:
            await manager.cancel_wakeup()

    hass.services.async_register(DOMAIN, "sync_location", _sync_location)
    hass.services.async_register(DOMAIN, "set_wakeup", _set_wakeup)
    hass.services.async_register(DOMAIN, "cancel_wakeup", _cancel_wakeup)


async def _auto_solar_sync(hass: HomeAssistant, manager: ConnectionManager) -> None:
    """Sync the current time/date, timezone and location to the lamp daily.

    Keeps the lamp's internal clock and solar/circadian tracker accurate.
    """
    while True:
        try:
            lat = hass.config.latitude
            lon = hass.config.longitude
            tz = str(hass.config.time_zone)
            lamp = await manager.ensure_connection()
            await lamp.sync_solar_location(latitude=lat, longitude=lon, timezone_str=tz)
            _LOGGER.info("Dyson lamp time/location synced (lat=%.4f lon=%.4f tz=%s)", lat, lon, tz)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Dyson lamp time/location sync failed (will retry): %s", err)
        await asyncio.sleep(SOLAR_SYNC_INTERVAL_SECONDS)
