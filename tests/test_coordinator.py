"""Tests for the PiGPIO coordinator."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.pigpio.const import (
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PINS,
    CONF_PULL_MODE,
    PIN_TYPE_INPUT,
    PIN_TYPE_OUTPUT,
    PULL_MODE_UP,
)
from custom_components.pigpio.coordinator import PigpioCoordinator

from .conftest import FakePigpioPi, make_config_entry_data


def make_entry(options: dict) -> ConfigEntry:
    """Create a config entry for coordinator tests."""
    return ConfigEntry(
        version=1,
        minor_version=1,
        domain="pigpio",
        title="PiGPIO",
        data=make_config_entry_data(),
        discovery_keys={},
        source="user",
        entry_id="test-entry",
        subentries_data={},
        unique_id="pi.local:8888",
        options=options,
    )


@pytest.mark.asyncio
async def test_first_refresh_reads_input_and_output_states(hass):
    """Test first refresh reads both input and output GPIO states."""
    fake_pi = FakePigpioPi(levels={17: 1, 18: 1})
    entry = make_entry(
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
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()
        coordinator.async_set_updated_data(await coordinator._async_update_data())

    assert coordinator.data == {17: 1, 18: 1}


@pytest.mark.asyncio
async def test_gpio_callback_schedules_data_update_on_event_loop(hass):
    """Test GPIO callbacks defer coordinator data mutation to the HA loop."""
    fake_pi = FakePigpioPi(levels={17: 0})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()
        coordinator.async_set_updated_data(await coordinator._async_update_data())

    coordinator._gpio_callback(17, 1, 123)
    assert coordinator.data == {17: 0}

    await hass.async_block_till_done()

    assert coordinator.data == {17: 1}


@pytest.mark.asyncio
async def test_write_pin_updates_data_after_success(hass):
    """Test successful output writes update coordinator data."""
    fake_pi = FakePigpioPi(levels={18: 0})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        await coordinator.async_write_pin(18, 1)

    assert fake_pi.write_calls == [(18, 1)]
    assert coordinator.data == {18: 1}


@pytest.mark.asyncio
async def test_write_pin_raises_and_keeps_state_after_failure(hass):
    """Test failed output writes raise and keep the previous state."""
    fake_pi = FakePigpioPi(levels={18: 0}, write_errors={18: -1})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()
        coordinator.async_set_updated_data(await coordinator._async_update_data())
        with pytest.raises(HomeAssistantError):
            await coordinator.async_write_pin(18, 1)

    assert coordinator.data == {18: 0}


@pytest.mark.asyncio
async def test_read_error_raises_update_failed(hass):
    """Test pigpio read errors become coordinator update failures."""
    fake_pi = FakePigpioPi(levels={17: 0}, read_errors={17: -1})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_disconnected_write_is_pending_and_replayed_after_reconnect(hass):
    """Test disconnected writes raise but replay after reconnect."""
    disconnected_pi = FakePigpioPi(connected=False)
    reconnected_pi = FakePigpioPi(levels={18: 0})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                }
            ]
        }
    )
    coordinator = PigpioCoordinator(hass, entry)
    coordinator.pi = disconnected_pi

    with pytest.raises(HomeAssistantError):
        await coordinator.async_write_pin(18, 1)

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=reconnected_pi):
        await coordinator._connect()
        await coordinator._setup_pins()
        coordinator.async_set_updated_data(await coordinator._async_update_data())

    assert reconnected_pi.write_calls == [(18, 1)]
    assert coordinator.data == {18: 1}


@pytest.mark.asyncio
async def test_shutdown_cancels_callbacks_and_stops_pigpio(hass):
    """Test shutdown cancels callbacks and stops the pigpio connection."""
    fake_pi = FakePigpioPi(levels={17: 0})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()

    assert len(fake_pi.callbacks) == 1

    await coordinator.async_shutdown()

    assert fake_pi.callbacks[0].cancelled is True
    assert fake_pi.stopped is True


@pytest.mark.asyncio
async def test_setup_fails_when_connection_refused(hass):
    """Test _async_setup raises UpdateFailed when daemon unreachable."""
    not_connected = FakePigpioPi(connected=False)
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=not_connected):
        coordinator = PigpioCoordinator(hass, entry)
        with pytest.raises(UpdateFailed):
            await coordinator._async_setup()


@pytest.mark.asyncio
async def test_reconnect_failure_raises_update_failed(hass):
    """Test _async_update_data raises UpdateFailed when reconnect also fails."""
    dead_pi = FakePigpioPi(connected=False)
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    coordinator = PigpioCoordinator(hass, entry)
    coordinator.pi = dead_pi

    with (
        patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=dead_pi),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_set_mode_error_raises_during_setup(hass):
    """Test pin setup raises OSError when set_mode fails."""
    fake_pi = FakePigpioPi(mode_errors={17: -1})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        with pytest.raises(OSError, match="set_mode failed for GPIO 17"):
            await coordinator._async_setup()


@pytest.mark.asyncio
async def test_set_pull_up_down_error_raises_during_setup(hass):
    """Test pin setup raises OSError when set_pull_up_down fails."""
    fake_pi = FakePigpioPi(pull_errors={17: -2})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                    CONF_PULL_MODE: PULL_MODE_UP,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        with pytest.raises(OSError, match="set_pull_up_down failed for GPIO 17"):
            await coordinator._async_setup()


@pytest.mark.asyncio
async def test_output_set_mode_error_raises_during_setup(hass):
    """Test output pin setup raises OSError when set_mode fails."""
    fake_pi = FakePigpioPi(mode_errors={18: -3})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        with pytest.raises(OSError, match="set_mode failed for GPIO 18"):
            await coordinator._async_setup()


@pytest.mark.asyncio
async def test_pending_write_error_during_reconnect_setup(hass):
    """Test pending output write failure raises during pin setup after reconnect."""
    fake_pi = FakePigpioPi(write_errors={18: -5})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        coordinator._pending_output_states[18] = 1
        with pytest.raises(OSError, match="write failed for GPIO 18"):
            await coordinator._async_setup()


@pytest.mark.asyncio
async def test_setup_pins_noop_when_pi_disconnected(hass):
    """Test _setup_pins_sync returns early when pi is not connected."""
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    coordinator = PigpioCoordinator(hass, entry)
    coordinator.pi = None
    await coordinator._setup_pins()
    # No exception raised, no callbacks registered
    assert coordinator._callbacks == {}


@pytest.mark.asyncio
async def test_watchdog_timeout_ignored_in_callback(hass):
    """Test GPIO callback ignores watchdog timeout (level=2)."""
    fake_pi = FakePigpioPi(levels={17: 0})
    entry = make_entry(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 17,
                    CONF_PIN_NAME: "Door",
                    CONF_PIN_TYPE: PIN_TYPE_INPUT,
                }
            ]
        }
    )

    with patch("custom_components.pigpio.coordinator.pigpio.pi", return_value=fake_pi):
        coordinator = PigpioCoordinator(hass, entry)
        await coordinator._async_setup()
        coordinator.async_set_updated_data(await coordinator._async_update_data())

    coordinator._gpio_callback(17, 2, 999)
    await hass.async_block_till_done()

    assert coordinator.data == {17: 0}
