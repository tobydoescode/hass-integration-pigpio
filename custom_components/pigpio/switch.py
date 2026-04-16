"""Switch platform for PiGPIO integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_INVERT_LOGIC,
    CONF_PINS,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    PIN_TYPE_OUTPUT,
)
from .coordinator import PigpioCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PiGPIO switches from a config entry."""
    coordinator: PigpioCoordinator = entry.runtime_data
    pins = entry.options.get(CONF_PINS, [])

    entities = [
        PigpioSwitch(coordinator, pin_config)
        for pin_config in pins
        if pin_config[CONF_PIN_TYPE] == PIN_TYPE_OUTPUT
    ]

    async_add_entities(entities)


class PigpioSwitch(CoordinatorEntity[PigpioCoordinator], SwitchEntity):
    """A switch backed by a remote GPIO output pin."""

    _attr_has_entity_name = True
    _attr_assumed_state = True

    def __init__(
        self, coordinator: PigpioCoordinator, pin_config: dict
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator)
        self._gpio: int = pin_config[CONF_PIN_NUMBER]
        self._invert: bool = pin_config.get(CONF_INVERT_LOGIC, False)
        self._attr_name = pin_config[CONF_PIN_NAME]
        self._attr_unique_id = (
            f"{coordinator.host}:{coordinator.port}_gpio{self._gpio}"
        )
        self._attr_is_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        value = 0 if self._invert else 1
        await self.coordinator.async_write_pin(self._gpio, value)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        value = 1 if self._invert else 0
        await self.coordinator.async_write_pin(self._gpio, value)
        self._attr_is_on = False
        self.async_write_ha_state()
