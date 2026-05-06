"""Binary sensor platform for PiGPIO integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_INVERT_LOGIC,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PINS,
    PIN_TYPE_INPUT,
)
from .coordinator import PigpioCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up PiGPIO binary sensors from a config entry."""
    coordinator: PigpioCoordinator = entry.runtime_data
    pins = entry.options.get(CONF_PINS, [])

    entities = [
        PigpioBinarySensor(coordinator, pin_config)
        for pin_config in pins
        if pin_config[CONF_PIN_TYPE] == PIN_TYPE_INPUT
    ]

    async_add_entities(entities)


class PigpioBinarySensor(CoordinatorEntity[PigpioCoordinator], BinarySensorEntity):
    """A binary sensor backed by a remote GPIO input pin."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PigpioCoordinator, pin_config: dict) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._gpio: int = pin_config[CONF_PIN_NUMBER]
        self._invert: bool = pin_config.get(CONF_INVERT_LOGIC, False)
        self._attr_name = pin_config[CONF_PIN_NAME]
        self._attr_unique_id = f"{coordinator.host}:{coordinator.port}_gpio{self._gpio}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool | None:
        """Return true if the pin is high (or low if inverted)."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self._gpio)
        if value is None:
            return None
        return bool(value) != self._invert
