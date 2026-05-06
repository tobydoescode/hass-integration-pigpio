"""Config flow for PiGPIO integration."""

from __future__ import annotations

import re
import socket
import subprocess
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback

import pigpio

from .const import (
    CONF_INVERT_LOGIC,
    CONF_MAC,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PINS,
    CONF_PULL_MODE,
    DEFAULT_PORT,
    DOMAIN,
    PIN_TYPE_INPUT,
    PIN_TYPE_OUTPUT,
    PULL_MODE_DOWN,
    PULL_MODE_NONE,
    PULL_MODE_UP,
)

MAC_PATTERN = r"([0-9a-fA-F]{2}[:\-]){5}[0-9a-fA-F]{2}"
MAC_REGEX = re.compile(MAC_PATTERN)
MAC_REGEX_FULL = re.compile(f"^{MAC_PATTERN}$")


def _clean_host(host: str) -> str:
    """Return host value suitable for storage."""
    return host.strip()


def _clean_pin_name(name: str) -> str:
    """Return pin name suitable for storage."""
    return name.strip()


def _normalize_mac(mac: str) -> str:
    """Return MAC in lowercase colon-separated format."""
    return mac.strip().lower().replace("-", ":")


def _discover_mac(host: str) -> str | None:
    """Attempt to discover MAC address via ARP after resolving hostname."""
    try:
        ip = socket.gethostbyname(host)
    except OSError:
        return None
    try:
        output = subprocess.check_output(
            ["arp", "-n", ip], timeout=5, text=True, stderr=subprocess.DEVNULL
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None
    for line in output.splitlines():
        match = MAC_REGEX.search(line)
        if match:
            return _normalize_mac(match.group(0))
    return None


class PigpioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiGPIO."""

    VERSION = 1
    MINOR_VERSION = 2

    _discovered_host: str | None = None
    _discovered_port: int | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step — host and port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = _clean_host(user_input[CONF_HOST])
            port = user_input[CONF_PORT]

            pi = await self.hass.async_add_executor_job(pigpio.pi, host, port)
            try:
                if pi.connected:
                    self._discovered_host = host
                    self._discovered_port = port

                    mac = await self.hass.async_add_executor_job(_discover_mac, host)
                    if mac:
                        await self.async_set_unique_id(mac)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"PiGPIO ({host})",
                            data={CONF_HOST: host, CONF_PORT: port, CONF_MAC: mac},
                        )

                    return await self.async_step_mac()
                errors["base"] = "cannot_connect"
            finally:
                await self.hass.async_add_executor_job(pi.stop)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    async def async_step_mac(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Prompt user to manually enter the MAC address."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mac = _normalize_mac(user_input[CONF_MAC])
            if not MAC_REGEX_FULL.match(mac):
                errors[CONF_MAC] = "invalid_mac"
            else:
                await self.async_set_unique_id(mac)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"PiGPIO ({self._discovered_host})",
                    data={
                        CONF_HOST: self._discovered_host,
                        CONF_PORT: self._discovered_port,
                        CONF_MAC: mac,
                    },
                )

        return self.async_show_form(
            step_id="mac",
            data_schema=vol.Schema({vol.Required(CONF_MAC): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PigpioOptionsFlow:
        """Get the options flow for this handler."""
        return PigpioOptionsFlow()


class PigpioOptionsFlow(OptionsFlow):
    """Handle options flow for PiGPIO — manage GPIO pins."""

    _pending_pin: dict[str, Any] | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_pin", "remove_pin"],
        )

    async def async_step_add_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle adding a new GPIO pin."""
        errors: dict[str, str] = {}

        if user_input is not None:
            gpio = user_input[CONF_PIN_NUMBER]
            pin_name = _clean_pin_name(user_input[CONF_PIN_NAME])
            pins = list(self.config_entry.options.get(CONF_PINS, []))

            # Check for duplicate GPIO number
            if any(p[CONF_PIN_NUMBER] == gpio for p in pins):
                errors[CONF_PIN_NUMBER] = "gpio_in_use"
            if not pin_name:
                errors[CONF_PIN_NAME] = "invalid_name"

            if not errors:
                pin_config: dict[str, Any] = {
                    CONF_PIN_NUMBER: gpio,
                    CONF_PIN_NAME: pin_name,
                    CONF_PIN_TYPE: user_input[CONF_PIN_TYPE],
                    CONF_INVERT_LOGIC: user_input.get(CONF_INVERT_LOGIC, False),
                }
                if user_input[CONF_PIN_TYPE] == PIN_TYPE_INPUT:
                    self._pending_pin = pin_config
                    return await self.async_step_add_input_details()

                pins.append(pin_config)
                return self.async_create_entry(data={CONF_PINS: pins})

        return self.async_show_form(
            step_id="add_pin",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN_NUMBER): vol.All(int, vol.Range(min=0, max=31)),
                    vol.Required(CONF_PIN_NAME): str,
                    vol.Required(CONF_PIN_TYPE): vol.In(
                        {
                            PIN_TYPE_INPUT: "Input (Binary Sensor)",
                            PIN_TYPE_OUTPUT: "Output (Switch)",
                        }
                    ),
                    vol.Optional(CONF_INVERT_LOGIC, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_add_input_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect input-only GPIO settings."""
        if self._pending_pin is None:
            return await self.async_step_add_pin()

        if user_input is not None:
            pins = list(self.config_entry.options.get(CONF_PINS, []))
            pin_config = dict(self._pending_pin)
            pin_config[CONF_PULL_MODE] = user_input.get(CONF_PULL_MODE, PULL_MODE_NONE)
            pins.append(pin_config)
            self._pending_pin = None
            return self.async_create_entry(data={CONF_PINS: pins})

        return self.async_show_form(
            step_id="add_input_details",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PULL_MODE, default=PULL_MODE_NONE): vol.In(
                        {
                            PULL_MODE_UP: "Pull Up",
                            PULL_MODE_DOWN: "Pull Down",
                            PULL_MODE_NONE: "None",
                        }
                    ),
                }
            ),
        )

    async def async_step_remove_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle removing a GPIO pin."""
        pins = list(self.config_entry.options.get(CONF_PINS, []))

        if not pins:
            return self.async_abort(reason="no_pins")

        if user_input is not None:
            gpio_to_remove = user_input[CONF_PIN_NUMBER]
            pins = [p for p in pins if p[CONF_PIN_NUMBER] != gpio_to_remove]
            return self.async_create_entry(data={CONF_PINS: pins})

        pin_choices = {
            p[CONF_PIN_NUMBER]: f"GPIO {p[CONF_PIN_NUMBER]} - {p[CONF_PIN_NAME]}" for p in pins
        }

        return self.async_show_form(
            step_id="remove_pin",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN_NUMBER): vol.In(pin_choices),
                }
            ),
        )
