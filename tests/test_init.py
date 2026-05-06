"""Tests for PiGPIO integration setup and unload."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pigpio.const import (
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PINS,
    DOMAIN,
    PIN_TYPE_INPUT,
    PIN_TYPE_OUTPUT,
)

from .conftest import FakePigpioPi, make_config_entry_data


def make_entry(hass, options: dict | None = None) -> MockConfigEntry:
    """Create and add a config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="PiGPIO",
        data=make_config_entry_data(),
        unique_id="pi.local:8888",
        options=options or {},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.mark.asyncio
async def test_setup_and_unload_entry(hass):
    """Test full setup and unload lifecycle."""
    fake_pi = FakePigpioPi(levels={17: 1, 18: 0})
    entry = make_entry(
        hass,
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                },
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                },
            ]
        },
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert not fake_pi.stopped

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert fake_pi.stopped
    assert fake_pi.callbacks[0].cancelled is True


@pytest.mark.asyncio
async def test_unload_shuts_down_coordinator(hass):
    """Test unload calls coordinator shutdown which stops pigpio and cancels callbacks."""
    fake_pi = FakePigpioPi(levels={17: 0})
    entry = make_entry(
        hass,
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Sensor",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        },
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    assert coordinator.pi is fake_pi

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert fake_pi.stopped is True
    assert coordinator.pi is None


@pytest.mark.asyncio
async def test_setup_entry_fails_when_daemon_unreachable(hass):
    """Test setup fails gracefully when pigpio daemon cannot be reached."""
    dead_pi = FakePigpioPi(connected=False)
    entry = make_entry(hass)

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=dead_pi):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
