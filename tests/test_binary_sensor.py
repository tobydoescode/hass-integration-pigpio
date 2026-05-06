"""Tests for PiGPIO binary sensor entities."""

from __future__ import annotations

from custom_components.pigpio.binary_sensor import PigpioBinarySensor
from custom_components.pigpio.const import (
    CONF_INVERT_LOGIC,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
)
from custom_components.pigpio.coordinator import PigpioCoordinator

from .test_coordinator import make_entry


def make_sensor(hass, data: dict[int, int] | None = None, invert: bool = False):
    """Create a binary sensor backed by a coordinator with test data."""
    coordinator = PigpioCoordinator(hass, make_entry({}))
    if data is not None:
        coordinator.async_set_updated_data(data)
    return PigpioBinarySensor(
        coordinator,
        {
            CONF_PIN_NUMBER: 17,
            CONF_PIN_NAME: "Door",
            CONF_INVERT_LOGIC: invert,
        },
    )


def test_binary_sensor_unknown_without_data(hass):
    """Test binary sensor is unknown without coordinator data."""
    entity = make_sensor(hass, None)
    assert entity.is_on is None


def test_binary_sensor_unknown_when_gpio_missing(hass):
    """Test binary sensor is unknown when its GPIO has no data."""
    entity = make_sensor(hass, {})
    assert entity.is_on is None


def test_binary_sensor_state_from_coordinator_data(hass):
    """Test binary sensor state comes from coordinator data."""
    entity = make_sensor(hass, {17: 1})
    assert entity.is_on is True


def test_binary_sensor_applies_invert_logic(hass):
    """Test binary sensor state applies invert logic."""
    entity = make_sensor(hass, {17: 0}, invert=True)
    assert entity.is_on is True
