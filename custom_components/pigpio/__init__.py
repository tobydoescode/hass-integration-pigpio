"""The PiGPIO integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_MAC
from .coordinator import PigpioCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SWITCH]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to current version."""
    if entry.version == 1 and entry.minor_version < 2:
        _LOGGER.debug("Migrating PiGPIO config entry from 1.%s to 1.2", entry.minor_version)
        new_data = {**entry.data}
        if CONF_MAC not in new_data:
            from .config_flow import _discover_mac

            mac = await hass.async_add_executor_job(_discover_mac, new_data[CONF_HOST])
            if mac is None:
                _LOGGER.warning(
                    "Cannot discover MAC for %s — reconfigure the integration to set it",
                    new_data[CONF_HOST],
                )
                return False
            new_data[CONF_MAC] = mac
        hass.config_entries.async_update_entry(entry, data=new_data, minor_version=2, version=1)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up PiGPIO from a config entry."""
    coordinator = PigpioCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a PiGPIO config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: PigpioCoordinator = entry.runtime_data
        await coordinator.async_shutdown()
    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
