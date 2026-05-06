"""Diagnostics support for PiGPIO integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import CONF_PINS
from .coordinator import PigpioCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: PigpioCoordinator = entry.runtime_data
    return {
        "config": {
            "host": entry.data[CONF_HOST],
            "port": entry.data[CONF_PORT],
            "mac": "**REDACTED**",
        },
        "connection": {
            "connected": coordinator.pi is not None and coordinator.pi.connected,
        },
        "pins": entry.options.get(CONF_PINS, []),
        "pin_states": dict(coordinator.data) if coordinator.data else {},
        "pending_output_states": dict(coordinator._pending_output_states),
    }
