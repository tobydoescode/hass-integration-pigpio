"""Shared test helpers for the PiGPIO integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in Home Assistant tests."""


class FakePigpioCallback:
    """Fake pigpio callback registration."""

    def __init__(self, gpio: int, edge: int, func: Callable[[int, int, int], None]) -> None:
        """Initialize the callback."""
        self.gpio = gpio
        self.edge = edge
        self.func = func
        self.cancelled = False

    def cancel(self) -> None:
        """Cancel the callback."""
        self.cancelled = True


@dataclass
class FakePigpioPi:
    """Fake pigpio connection."""

    connected: bool = True
    levels: dict[int, int] = field(default_factory=dict)
    write_result: int = 0
    read_errors: dict[int, int] = field(default_factory=dict)
    write_errors: dict[int, int] = field(default_factory=dict)
    mode_errors: dict[int, int] = field(default_factory=dict)
    pull_errors: dict[int, int] = field(default_factory=dict)
    mode_calls: list[tuple[int, int]] = field(default_factory=list)
    pull_calls: list[tuple[int, int]] = field(default_factory=list)
    write_calls: list[tuple[int, int]] = field(default_factory=list)
    callbacks: list[FakePigpioCallback] = field(default_factory=list)
    stopped: bool = False

    def get_current_tick(self) -> int:
        """Return a fake current tick."""
        if not self.connected:
            raise OSError("not connected")
        return 1

    def set_mode(self, gpio: int, mode: int) -> int:
        """Set a fake GPIO mode."""
        self.mode_calls.append((gpio, mode))
        return self.mode_errors.get(gpio, 0)

    def set_pull_up_down(self, gpio: int, pud: int) -> int:
        """Set a fake GPIO pull mode."""
        self.pull_calls.append((gpio, pud))
        return self.pull_errors.get(gpio, 0)

    def read(self, gpio: int) -> int:
        """Read a fake GPIO value."""
        if gpio in self.read_errors:
            return self.read_errors[gpio]
        return self.levels.get(gpio, 0)

    def write(self, gpio: int, value: int) -> int:
        """Write a fake GPIO value."""
        self.write_calls.append((gpio, value))
        if gpio in self.write_errors:
            return self.write_errors[gpio]
        self.levels[gpio] = value
        return self.write_result

    def callback(
        self, gpio: int, edge: int, func: Callable[[int, int, int], None]
    ) -> FakePigpioCallback:
        """Register a fake GPIO callback."""
        callback = FakePigpioCallback(gpio, edge, func)
        self.callbacks.append(callback)
        return callback

    def stop(self) -> None:
        """Stop the fake connection."""
        self.stopped = True
        self.connected = False


def make_config_entry_data(
    host: str = "pi.local", port: int = 8888, mac: str = "aa:bb:cc:dd:ee:ff"
) -> dict[str, Any]:
    """Return config entry data for tests."""
    return {"host": host, "port": port, "mac": mac}
