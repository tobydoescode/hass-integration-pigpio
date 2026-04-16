"""Coordinator for PiGPIO integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import pigpio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_INVERT_LOGIC,
    CONF_PINS,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
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
        self._output_states: dict[int, int] = {}  # gpio -> last written value

    @property
    def pins(self) -> list[dict[str, Any]]:
        """Return configured pins from options."""
        return self.config_entry.options.get(CONF_PINS, [])

    async def _async_setup(self) -> None:
        """Establish initial connection to pigpio daemon."""
        await self._connect()
        if self.pi is None or not self.pi.connected:
            raise UpdateFailed(
                f"Cannot connect to pigpio daemon at {self.host}:{self.port}"
            )
        await self._setup_pins()

    async def _async_update_data(self) -> dict[int, int]:
        """Health check and read input states."""
        connected = await self.hass.async_add_executor_job(self._check_connection)
        if not connected:
            _LOGGER.warning("Connection lost to pigpio at %s:%s, reconnecting", self.host, self.port)
            await self._connect()
            connected = await self.hass.async_add_executor_job(self._check_connection)
            if not connected:
                raise UpdateFailed(
                    f"Cannot connect to pigpio daemon at {self.host}:{self.port}"
                )
            await self._setup_pins()
            _LOGGER.info("Reconnected to pigpio at %s:%s", self.host, self.port)

        return await self.hass.async_add_executor_job(self._read_all_inputs)

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
        try:
            if self.pi is not None:
                self.pi.stop()
        except Exception:  # noqa: BLE001
            pass
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
                self.pi.set_mode(gpio, pigpio.INPUT)
                pull_mode = pin_config.get(CONF_PULL_MODE)
                if pull_mode in PULL_MODE_MAP:
                    self.pi.set_pull_up_down(gpio, PULL_MODE_MAP[pull_mode])
                else:
                    self.pi.set_pull_up_down(gpio, pigpio.PUD_OFF)
                # Register edge callback for instant state updates
                self._callbacks[gpio] = self.pi.callback(
                    gpio, pigpio.EITHER_EDGE, self._gpio_callback
                )
            elif pin_type == PIN_TYPE_OUTPUT:
                self.pi.set_mode(gpio, pigpio.OUTPUT)
                # Re-apply last known output state after reconnection
                if gpio in self._output_states:
                    self.pi.write(gpio, self._output_states[gpio])

    def _gpio_callback(self, gpio: int, level: int, tick: int) -> None:
        """Handle GPIO edge change — update data and notify entities."""
        if level == 2:  # watchdog timeout, not a real edge
            return
        if self.data is not None:
            self.data[gpio] = level
        else:
            self.data = {gpio: level}
        # Schedule HA state update from the callback thread
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, self.data)

    def _cancel_callbacks(self) -> None:
        """Cancel all registered pigpio callbacks."""
        for cb in self._callbacks.values():
            try:
                cb.cancel()
            except Exception:  # noqa: BLE001
                pass
        self._callbacks.clear()

    def _read_all_inputs(self) -> dict[int, int]:
        """Read all input pin states. Returns {gpio: value}."""
        states: dict[int, int] = {}
        if self.pi is None or not self.pi.connected:
            return states

        for pin_config in self.pins:
            if pin_config[CONF_PIN_TYPE] == PIN_TYPE_INPUT:
                gpio = pin_config[CONF_PIN_NUMBER]
                states[gpio] = self.pi.read(gpio)

        return states

    def write_pin(self, gpio: int, value: int) -> None:
        """Write a value to an output pin."""
        self._output_states[gpio] = value
        if self.pi is not None and self.pi.connected:
            self.pi.write(gpio, value)

    async def async_write_pin(self, gpio: int, value: int) -> None:
        """Write a value to an output pin asynchronously."""
        await self.hass.async_add_executor_job(self.write_pin, gpio, value)

    async def async_shutdown(self) -> None:
        """Clean up pigpio connection."""
        if self.pi is not None:
            await self.hass.async_add_executor_job(self._stop_connection)
        await super().async_shutdown()
