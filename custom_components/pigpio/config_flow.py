"""Config flow for PiGPIO integration."""

from __future__ import annotations

from typing import Any

import pigpio
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_INVERT_LOGIC,
    CONF_PINS,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PULL_MODE,
    DEFAULT_PORT,
    DOMAIN,
    PIN_TYPE_INPUT,
    PIN_TYPE_OUTPUT,
    PULL_MODE_DOWN,
    PULL_MODE_NONE,
    PULL_MODE_UP,
)


class PigpioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PiGPIO."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step — host and port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            # Test connection
            pi = await self.hass.async_add_executor_job(pigpio.pi, host, port)
            try:
                if pi.connected:
                    # Prevent duplicate entries for the same host:port
                    await self.async_set_unique_id(f"{host}:{port}")
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=f"PiGPIO ({host})",
                        data={CONF_HOST: host, CONF_PORT: port},
                    )
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PigpioOptionsFlow:
        """Get the options flow for this handler."""
        return PigpioOptionsFlow()


class PigpioOptionsFlow(OptionsFlow):
    """Handle options flow for PiGPIO — manage GPIO pins."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["add_pin", "remove_pin"],
        )

    async def async_step_add_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle adding a new GPIO pin."""
        errors: dict[str, str] = {}

        if user_input is not None:
            gpio = user_input[CONF_PIN_NUMBER]
            pins = list(self.config_entry.options.get(CONF_PINS, []))

            # Check for duplicate GPIO number
            if any(p[CONF_PIN_NUMBER] == gpio for p in pins):
                errors[CONF_PIN_NUMBER] = "gpio_in_use"
            else:
                pin_config: dict[str, Any] = {
                    CONF_PIN_NUMBER: gpio,
                    CONF_PIN_NAME: user_input[CONF_PIN_NAME],
                    CONF_PIN_TYPE: user_input[CONF_PIN_TYPE],
                    CONF_INVERT_LOGIC: user_input.get(CONF_INVERT_LOGIC, False),
                }
                if user_input[CONF_PIN_TYPE] == PIN_TYPE_INPUT:
                    pin_config[CONF_PULL_MODE] = user_input.get(
                        CONF_PULL_MODE, PULL_MODE_NONE
                    )

                pins.append(pin_config)
                return self.async_create_entry(data={CONF_PINS: pins})

        return self.async_show_form(
            step_id="add_pin",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN_NUMBER): vol.All(
                        int, vol.Range(min=0, max=31)
                    ),
                    vol.Required(CONF_PIN_NAME): str,
                    vol.Required(CONF_PIN_TYPE): vol.In(
                        {
                            PIN_TYPE_INPUT: "Input (Binary Sensor)",
                            PIN_TYPE_OUTPUT: "Output (Switch)",
                        }
                    ),
                    vol.Optional(CONF_PULL_MODE, default=PULL_MODE_NONE): vol.In(
                        {
                            PULL_MODE_UP: "Pull Up",
                            PULL_MODE_DOWN: "Pull Down",
                            PULL_MODE_NONE: "None",
                        }
                    ),
                    vol.Optional(CONF_INVERT_LOGIC, default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_remove_pin(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle removing a GPIO pin."""
        pins = list(self.config_entry.options.get(CONF_PINS, []))

        if not pins:
            return self.async_abort(reason="no_pins")

        if user_input is not None:
            gpio_to_remove = user_input[CONF_PIN_NUMBER]
            pins = [p for p in pins if p[CONF_PIN_NUMBER] != gpio_to_remove]
            return self.async_create_entry(data={CONF_PINS: pins})

        pin_choices = {
            p[CONF_PIN_NUMBER]: f"GPIO {p[CONF_PIN_NUMBER]} - {p[CONF_PIN_NAME]}"
            for p in pins
        }

        return self.async_show_form(
            step_id="remove_pin",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PIN_NUMBER): vol.In(pin_choices),
                }
            ),
        )
