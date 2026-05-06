"""Tests for PiGPIO switch entities."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.pigpio.const import (
    CONF_INVERT_LOGIC,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
)
from custom_components.pigpio.coordinator import PigpioCoordinator
from custom_components.pigpio.switch import PigpioSwitch

from .test_coordinator import make_entry


def make_switch(hass, data: dict[int, int] | None = None, invert: bool = False):
    """Create a switch backed by a coordinator with test data."""
    coordinator = PigpioCoordinator(hass, make_entry({}))
    coordinator.async_set_updated_data(data or {})
    entity = PigpioSwitch(
        coordinator,
        {
            CONF_PIN_NUMBER: 18,
            CONF_PIN_NAME: "Relay",
            CONF_INVERT_LOGIC: invert,
        },
    )
    return entity, coordinator


def test_switch_state_comes_from_coordinator_data(hass):
    """Test switch state is derived from coordinator data."""
    entity, _coordinator = make_switch(hass, {18: 1})
    assert entity.is_on is True


def test_switch_state_applies_invert_logic(hass):
    """Test switch state applies invert logic."""
    entity, _coordinator = make_switch(hass, {18: 0}, invert=True)
    assert entity.is_on is True


def test_switch_state_unknown_when_data_missing(hass):
    """Test switch state is unknown when coordinator data is missing."""
    entity, _coordinator = make_switch(hass, {})
    assert entity.is_on is None


@pytest.mark.asyncio
async def test_turn_on_propagates_write_failure(hass):
    """Test write failures propagate from turn_on."""
    entity, coordinator = make_switch(hass, {18: 0})

    async def fail_write(gpio: int, value: int) -> None:
        raise HomeAssistantError("write failed")

    coordinator.async_write_pin = fail_write

    with pytest.raises(HomeAssistantError):
        await entity.async_turn_on()

    assert coordinator.data == {18: 0}
