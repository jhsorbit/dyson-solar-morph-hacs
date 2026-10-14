"""Config flow for the Dyson Lightcycle Morph integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ADDRESS,
    CONF_LTK,
    CONF_MODE,
    CONF_SERIAL,
    CONF_USER_ID,
    CONNECTION_MODES,
    DOMAIN,
    MODE_PERSISTENT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SERIAL, default=""): str,
        vol.Required(CONF_ADDRESS, default=""): str,
        vol.Required(CONF_USER_ID, default=""): str,
        vol.Required(CONF_LTK, default=""): str,
        vol.Required(CONF_MODE, default=MODE_PERSISTENT): vol.In(CONNECTION_MODES),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MODE, default=MODE_PERSISTENT): vol.In(CONNECTION_MODES),
    }
)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate that the supplied credentials can reach a lamp.

    Performs a real BLE connect + authentication. Raises ValueError on failure.
    """
    from .lamp import DysconnError, LampClient

    address = data.get(CONF_ADDRESS) or data.get(CONF_SERIAL)
    if not address:
        raise ValueError("No BLE address or serial provided")

    if "-" in address and ":" not in address and len(address) >= 18:
        # Likely a macOS CoreBluetooth UUID pasted in. On Linux/HA the BLE
        # address must be a MAC (XX:XX:XX:XX:XX:XX) or empty (auto-scan by serial).
        raise ValueError(
            "The address looks like a macOS CoreBluetooth UUID. On Linux/HA enter the "
            "lamp's MAC address (e.g. A4:C1:38:AA:BB:CC) or leave it empty to auto-scan by serial."
        )

    client = LampClient(
        address=address,
        user_id=data[CONF_USER_ID],
        ltk_hex=data[CONF_LTK],
    )
    try:
        await client.connect(timeout=15, hass=hass)
    except DysconnError as err:
        _LOGGER.exception("Dyson lamp connection failed (phase=connect)")
        raise ValueError(f"Could not connect to the lamp: {err}") from err
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("Dyson lamp authentication failed (phase=auth)")
        raise ValueError(f"Connected but authentication failed: {err}") from err
    finally:
        await client.disconnect()

    return {
        CONF_SERIAL: data[CONF_SERIAL],
        CONF_ADDRESS: address,
        CONF_USER_ID: data[CONF_USER_ID],
        CONF_LTK: data[CONF_LTK],
        CONF_MODE: data[CONF_MODE],
    }


class DysonLampConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dyson Lightcycle Morph."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _validate_input(self.hass, user_input)
            except ValueError as err:
                errors["base"] = "cannot_connect"
                _LOGGER.warning("Dyson lamp config validation failed: %s", err)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Dyson lamp validation")
                errors["base"] = "unknown"
            else:
                serial = info[CONF_SERIAL]
                await self.async_set_unique_id(f"dyson_lamp_{serial or info[CONF_ADDRESS]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Dyson Lamp {serial or info[CONF_ADDRESS]}",
                    data=info,
                    options={CONF_MODE: info[CONF_MODE]},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return DysonLampOptionsFlow(config_entry)


class DysonLampOptionsFlow(OptionsFlow):
    """Handle options (e.g. switching the connection mode)."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_mode = self._config_entry.options.get(CONF_MODE, MODE_PERSISTENT)
        schema = OPTIONS_SCHEMA.extend(
            {vol.Required(CONF_MODE, default=current_mode): vol.In(CONNECTION_MODES)}
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
