"""Tests for the PiGPIO config and options flows."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pigpio.config_flow import PigpioOptionsFlow, _discover_mac
from custom_components.pigpio.const import (
    CONF_INVERT_LOGIC,
    CONF_MAC,
    CONF_PIN_NAME,
    CONF_PIN_NUMBER,
    CONF_PIN_TYPE,
    CONF_PINS,
    CONF_PULL_MODE,
    DOMAIN,
    PIN_TYPE_INPUT,
    PIN_TYPE_OUTPUT,
    PULL_MODE_UP,
)


class _PigpioOptionsFlowForTest(PigpioOptionsFlow):
    """Options flow with an injectable config entry for unit tests."""

    def __init__(self, config_entry: Mock) -> None:
        """Initialize the test options flow."""
        super().__init__()
        self._test_config_entry = config_entry

    @property
    def config_entry(self):
        """Return the injected config entry."""
        return self._test_config_entry


def connected_pi():
    """Return a connected fake pigpio object."""
    pi = Mock()
    pi.connected = True
    return pi


def disconnected_pi():
    """Return a disconnected fake pigpio object."""
    pi = Mock()
    pi.connected = False
    return pi


def make_options_flow(existing_options: dict | None = None) -> PigpioOptionsFlow:
    """Create an options flow with a fake config entry."""
    entry = Mock()
    entry.options = existing_options or {}
    return _PigpioOptionsFlowForTest(entry)


@pytest.mark.asyncio
async def test_user_step_creates_entry_when_mac_discovered(hass):
    """Test entry created with MAC when ARP lookup succeeds."""
    with (
        patch("custom_components.pigpio.config_flow.pigpio.pi", return_value=connected_pi()),
        patch(
            "custom_components.pigpio.config_flow._discover_mac",
            return_value="aa:bb:cc:dd:ee:ff",
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: " PiHost.LOCAL ", CONF_PORT: 8888},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        CONF_HOST: "PiHost.LOCAL",
        CONF_PORT: 8888,
        CONF_MAC: "aa:bb:cc:dd:ee:ff",
    }


@pytest.mark.asyncio
async def test_user_step_prompts_for_mac_when_discovery_fails(hass):
    """Test MAC step shown when ARP lookup fails."""
    with (
        patch("custom_components.pigpio.config_flow.pigpio.pi", return_value=connected_pi()),
        patch("custom_components.pigpio.config_flow._discover_mac", return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "pi.local", CONF_PORT: 8888},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "mac"


@pytest.mark.asyncio
async def test_mac_step_creates_entry(hass):
    """Test manual MAC entry creates config entry."""
    with (
        patch("custom_components.pigpio.config_flow.pigpio.pi", return_value=connected_pi()),
        patch("custom_components.pigpio.config_flow._discover_mac", return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "pi.local", CONF_PORT: 8888},
        )

    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MAC: "11:22:33:44:55:66"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC] == "11:22:33:44:55:66"


@pytest.mark.asyncio
async def test_mac_step_rejects_invalid_mac(hass):
    """Test invalid MAC address is rejected."""
    with (
        patch("custom_components.pigpio.config_flow.pigpio.pi", return_value=connected_pi()),
        patch("custom_components.pigpio.config_flow._discover_mac", return_value=None),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "pi.local", CONF_PORT: 8888},
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MAC: "not-a-mac"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MAC: "invalid_mac"}


@pytest.mark.asyncio
async def test_rejects_duplicate_mac(hass):
    """Test duplicate MAC is rejected."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "pi.local", CONF_PORT: 8888, CONF_MAC: "aa:bb:cc:dd:ee:ff"},
        unique_id="aa:bb:cc:dd:ee:ff",
    ).add_to_hass(hass)

    with (
        patch("custom_components.pigpio.config_flow.pigpio.pi", return_value=connected_pi()),
        patch(
            "custom_components.pigpio.config_flow._discover_mac",
            return_value="aa:bb:cc:dd:ee:ff",
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "pi2.local", CONF_PORT: 8888},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.asyncio
async def test_user_step_shows_cannot_connect(hass):
    """Test connection failure shows cannot_connect."""
    with patch("custom_components.pigpio.config_flow.pigpio.pi", return_value=disconnected_pi()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "pi.local", CONF_PORT: 8888},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


@pytest.mark.asyncio
async def test_add_pin_rejects_empty_name():
    """Test add-pin rejects names empty after stripping."""
    flow = make_options_flow()

    result = await flow.async_step_add_pin(
        {
            CONF_PIN_NUMBER: 18,
            CONF_PIN_NAME: "   ",
            CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
            CONF_INVERT_LOGIC: False,
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PIN_NAME: "invalid_name"}


@pytest.mark.asyncio
async def test_add_output_pin_stores_no_pull_mode():
    """Test output pin creation does not store pull mode."""
    flow = make_options_flow()

    result = await flow.async_step_add_pin(
        {
            CONF_PIN_NUMBER: 18,
            CONF_PIN_NAME: "Relay",
            CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
            CONF_INVERT_LOGIC: False,
        }
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    pin = result["data"][CONF_PINS][0]
    assert pin[CONF_PIN_TYPE] == PIN_TYPE_OUTPUT
    assert CONF_PULL_MODE not in pin


@pytest.mark.asyncio
async def test_add_input_pin_routes_to_pull_mode_step_and_stores_pull_mode():
    """Test input pin creation collects input-only pull mode."""
    flow = make_options_flow()

    first = await flow.async_step_add_pin(
        {
            CONF_PIN_NUMBER: 17,
            CONF_PIN_NAME: "Door",
            CONF_PIN_TYPE: PIN_TYPE_INPUT,
            CONF_INVERT_LOGIC: False,
        }
    )
    assert first["type"] is FlowResultType.FORM
    assert first["step_id"] == "add_input_details"

    second = await flow.async_step_add_input_details({CONF_PULL_MODE: PULL_MODE_UP})

    assert second["type"] is FlowResultType.CREATE_ENTRY
    pin = second["data"][CONF_PINS][0]
    assert pin[CONF_PIN_TYPE] == PIN_TYPE_INPUT
    assert pin[CONF_PULL_MODE] == PULL_MODE_UP


@pytest.mark.asyncio
async def test_add_pin_rejects_duplicate_gpio():
    """Test duplicate GPIO numbers are rejected."""
    flow = make_options_flow(
        {
            CONF_PINS: [
                {
                    CONF_PIN_NUMBER: 18,
                    CONF_PIN_NAME: "Relay",
                    CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
                    CONF_INVERT_LOGIC: False,
                }
            ]
        }
    )

    result = await flow.async_step_add_pin(
        {
            CONF_PIN_NUMBER: 18,
            CONF_PIN_NAME: "Other",
            CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
            CONF_INVERT_LOGIC: False,
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PIN_NUMBER: "gpio_in_use"}


@pytest.mark.asyncio
async def test_remove_pin_returns_remaining_pins():
    """Test removing a pin preserves remaining pin definitions."""
    remaining = {
        CONF_PIN_NUMBER: 18,
        CONF_PIN_NAME: "Relay",
        CONF_PIN_TYPE: PIN_TYPE_OUTPUT,
        CONF_INVERT_LOGIC: False,
    }
    flow = make_options_flow(
        {
            CONF_PINS: [
                {CONF_PIN_NUMBER: 17, CONF_PIN_NAME: "Door", CONF_PIN_TYPE: PIN_TYPE_INPUT},
                remaining,
            ]
        }
    )

    result = await flow.async_step_remove_pin({CONF_PIN_NUMBER: 17})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PINS] == [remaining]


@pytest.mark.asyncio
async def test_remove_pin_aborts_when_no_pins():
    """Test remove-pin aborts when no pins configured."""
    flow = make_options_flow()

    result = await flow.async_step_remove_pin(None)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_pins"


@pytest.mark.asyncio
async def test_remove_pin_shows_form_when_pins_exist():
    """Test remove-pin shows selection form."""
    flow = make_options_flow(
        {
            CONF_PINS: [
                {CONF_PIN_NUMBER: 17, CONF_PIN_NAME: "Door", CONF_PIN_TYPE: PIN_TYPE_INPUT},
            ]
        }
    )

    result = await flow.async_step_remove_pin(None)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "remove_pin"


@pytest.mark.asyncio
async def test_add_input_details_redirects_without_pending_pin():
    """Test add_input_details redirects to add_pin if no pending pin."""
    flow = make_options_flow()
    flow._pending_pin = None

    result = await flow.async_step_add_input_details(None)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_pin"


PATCH_DNS = "custom_components.pigpio.config_flow.socket.gethostbyname"
PATCH_ARP = "custom_components.pigpio.config_flow.subprocess.check_output"


def test_discover_mac_returns_mac_on_success():
    """Test _discover_mac parses MAC from arp output."""
    arp_output = "pi.local (192.168.1.50) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]"
    with (
        patch(PATCH_DNS, return_value="192.168.1.50"),
        patch(PATCH_ARP, return_value=arp_output),
    ):
        result = _discover_mac("pi.local")

    assert result == "aa:bb:cc:dd:ee:ff"


def test_discover_mac_returns_none_on_dns_failure():
    """Test _discover_mac returns None when hostname can't resolve."""
    with patch(PATCH_DNS, side_effect=OSError("DNS failed")):
        result = _discover_mac("unknown.host")

    assert result is None


def test_discover_mac_returns_none_on_arp_failure():
    """Test _discover_mac returns None when arp command fails."""
    with (
        patch(PATCH_DNS, return_value="192.168.1.50"),
        patch(PATCH_ARP, side_effect=FileNotFoundError),
    ):
        result = _discover_mac("pi.local")

    assert result is None


def test_discover_mac_returns_none_when_no_mac_in_output():
    """Test _discover_mac returns None when arp output has no MAC."""
    with (
        patch(PATCH_DNS, return_value="192.168.1.50"),
        patch(PATCH_ARP, return_value="no entries"),
    ):
        result = _discover_mac("pi.local")

    assert result is None
