"""Coordinator for PiGPIO integration."""

from __future__ import annotations

import logging
from contextlib import suppress
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import pigpio

from .const import (
    CONF_MAC,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PINS,
    CONF_PULL_MODE,
    DOMAIN,
    PIN_TYPE_INPUT,
    PIN_TYPE_OUTPUT,
    PULL_MODE_DOWN,
    PULL_MODE_UP,
)

_LOGGER = logging.getLogger(__name__)

PULL_MODE_MAP = {
    PULL_MODE_UP: pigpio.PUD_UP,
    PULL_MODE_DOWN: pigpio.PUD_DOWN,
}


class PigpioCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Manage pigpio connection and poll input pin states."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=30),
        )
        self.host: str = entry.data[CONF_HOST]
        self.port: int = entry.data[CONF_PORT]
        self.pi: pigpio.pi | None = None
        self._callbacks: dict[int, pigpio.callback] = {}
        self._pending_output_states: dict[int, int] = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for the pigpio daemon."""
        mac = self.config_entry.data[CONF_MAC]
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, mac)},
            identifiers={(DOMAIN, mac)},
            name=f"PiGPIO ({self.host})",
            manufacturer="Raspberry Pi",
            configuration_url=f"http://{self.host}:{self.port}",
        )

    @property
    def pins(self) -> list[dict[str, Any]]:
        """Return configured pins from options."""
        return self.config_entry.options.get(CONF_PINS, [])

    async def _async_setup(self) -> None:
        """Establish initial connection to pigpio daemon."""
        await self._connect()
        if self.pi is None or not self.pi.connected:
            raise UpdateFailed(f"Cannot connect to pigpio daemon at {self.host}:{self.port}")
        await self._setup_pins()

    async def _async_update_data(self) -> dict[int, int]:
        """Health check and read configured pin states."""
        connected = await self.hass.async_add_executor_job(self._check_connection)
        if not connected:
            _LOGGER.warning(
                "Connection lost to pigpio at %s:%s, reconnecting",
                self.host,
                self.port,
            )
            await self._connect()
            connected = await self.hass.async_add_executor_job(self._check_connection)
            if not connected:
                raise UpdateFailed(f"Cannot connect to pigpio daemon at {self.host}:{self.port}")
            await self._setup_pins()
            _LOGGER.info("Reconnected to pigpio at %s:%s", self.host, self.port)

        try:
            return await self.hass.async_add_executor_job(self._read_all_configured_pins)
        except OSError as err:
            raise UpdateFailed(str(err)) from err

    def _check_connection(self) -> bool:
        """Actively check if the pigpio connection is alive."""
        if self.pi is None or not self.pi.connected:
            return False
        try:
            # Issue a lightweight command to verify the connection is live
            self.pi.get_current_tick()
            return True
        except Exception:  # noqa: BLE001
            return False

    async def _connect(self) -> None:
        """Connect to pigpio daemon."""
        if self.pi is not None:
            await self.hass.async_add_executor_job(self._stop_connection)
        self.pi = await self.hass.async_add_executor_job(pigpio.pi, self.host, self.port)

    def _stop_connection(self) -> None:
        """Stop existing pigpio connection."""
        self._cancel_callbacks()
        with suppress(Exception):
            if self.pi is not None:
                self.pi.stop()
        self.pi = None

    async def _setup_pins(self) -> None:
        """Configure pin modes after (re)connection."""
        await self.hass.async_add_executor_job(self._setup_pins_sync)

    def _setup_pins_sync(self) -> None:
        """Configure pin modes and register callbacks synchronously."""
        self._cancel_callbacks()

        if self.pi is None or not self.pi.connected:
            return

        for pin_config in self.pins:
            gpio = pin_config[CONF_PIN_NUMBER]
            pin_type = pin_config[CONF_PIN_TYPE]

            if pin_type == PIN_TYPE_INPUT:
                result = self.pi.set_mode(gpio, pigpio.INPUT)
                self._raise_for_pigpio_result("set_mode", gpio, result)
                pull_mode = pin_config.get(CONF_PULL_MODE)
                if pull_mode in PULL_MODE_MAP:
                    result = self.pi.set_pull_up_down(gpio, PULL_MODE_MAP[pull_mode])
                else:
                    result = self.pi.set_pull_up_down(gpio, pigpio.PUD_OFF)
                self._raise_for_pigpio_result("set_pull_up_down", gpio, result)
                # Register edge callback for instant state updates
                self._callbacks[gpio] = self.pi.callback(
                    gpio, pigpio.EITHER_EDGE, self._gpio_callback
                )
            elif pin_type == PIN_TYPE_OUTPUT:
                result = self.pi.set_mode(gpio, pigpio.OUTPUT)
                self._raise_for_pigpio_result("set_mode", gpio, result)
                if gpio in self._pending_output_states:
                    value = self._pending_output_states[gpio]
                    result = self.pi.write(gpio, value)
                    self._raise_for_pigpio_result("write", gpio, result)
                    self._pending_output_states.pop(gpio)

    def _gpio_callback(self, gpio: int, level: int, tick: int) -> None:
        """Handle GPIO edge change by scheduling HA-loop state publication."""
        if level == 2:
            return
        self.hass.loop.call_soon_threadsafe(self._handle_gpio_edge, gpio, level)

    def _handle_gpio_edge(self, gpio: int, level: int) -> None:
        """Publish GPIO edge data on the Home Assistant event loop."""
        data = dict(self.data or {})
        data[gpio] = level
        self.async_set_updated_data(data)

    def _cancel_callbacks(self) -> None:
        """Cancel all registered pigpio callbacks."""
        for cb in self._callbacks.values():
            with suppress(Exception):
                cb.cancel()
        self._callbacks.clear()

    def _raise_for_pigpio_result(self, operation: str, gpio: int, result: int) -> None:
        """Raise when pigpio returns an error code."""
        if result < 0:
            raise OSError(f"pigpio {operation} failed for GPIO {gpio}: {result}")

    def _read_all_configured_pins(self) -> dict[int, int]:
        """Read all configured pin states. Returns {gpio: value}."""
        states: dict[int, int] = {}
        if self.pi is None or not self.pi.connected:
            return states

        for pin_config in self.pins:
            gpio = pin_config[CONF_PIN_NUMBER]
            value = self.pi.read(gpio)
            self._raise_for_pigpio_result("read", gpio, value)
            states[gpio] = value

        return states

    def write_pin(self, gpio: int, value: int) -> None:
        """Write a value to an output pin."""
        if self.pi is None or not self.pi.connected:
            self._pending_output_states[gpio] = value
            raise OSError(f"pigpio is not connected for GPIO {gpio}")
        result = self.pi.write(gpio, value)
        self._raise_for_pigpio_result("write", gpio, result)
        self._pending_output_states.pop(gpio, None)

    async def async_write_pin(self, gpio: int, value: int) -> None:
        """Write a value to an output pin asynchronously."""
        try:
            await self.hass.async_add_executor_job(self.write_pin, gpio, value)
        except OSError as err:
            raise HomeAssistantError(str(err)) from err

        data = dict(self.data or {})
        data[gpio] = value
        self.async_set_updated_data(data)

    async def async_shutdown(self) -> None:
        """Clean up pigpio connection."""
        if self.pi is not None:
            await self.hass.async_add_executor_job(self._stop_connection)
        await super().async_shutdown()
