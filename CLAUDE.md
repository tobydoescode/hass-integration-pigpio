# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Home Assistant custom integration for remote Raspberry Pi GPIO via the pigpio daemon. Exposes GPIO pins as binary sensors (inputs) and switches (outputs). Distributed via HACS.

## Commands

```bash
task sync                # Install dependencies (uv)
task test                # Run tests
task test:coverage       # Run tests with coverage report
task lint                # Ruff lint + format check
task lint:fix            # Auto-fix lint and formatting
uv run pyright custom_components/pigpio/   # Type check
task dev                 # Start HA in Docker
task dev:restart         # Restart HA after code changes
task dev:logs            # Tail HA logs
```

Run a single test: `uv run pytest tests/test_coordinator.py::test_name -v`

## Architecture

The integration follows the standard HA `DataUpdateCoordinator` pattern:

- **`coordinator.py`** — `PigpioCoordinator` manages the `pigpio.pi` connection, polls all configured pin states every 30s, and handles reconnection. GPIO edge callbacks use `call_soon_threadsafe` to publish state changes on the HA event loop. Writes to output pins go through `async_write_pin` which wraps `OSError` as `HomeAssistantError`. Disconnected writes are queued in `_pending_output_states` and replayed on reconnect. Creates HA repair issues after 3 consecutive connection failures, auto-clears on recovery.

- **`config_flow.py`** — Two-phase setup: user enters host:port, then MAC is discovered via ARP or manually entered. MAC is the config entry `unique_id` and device registry identifier (stable across IP changes). Options flow manages pins with a multi-step form (input pins get an extra pull-mode step). Helper functions `_discover_mac`, `_clean_host`, `_normalize_mac` handle network identity.

- **`entity.py` does not exist** — entity classes live directly in `binary_sensor.py` and `switch.py`. Both set `_attr_device_info` from `coordinator.device_info` to group all pins under one device per daemon.

- **`__init__.py`** — Contains `async_migrate_entry` for v1.1→v1.2 migration (adds MAC field to existing entries via ARP discovery).

## Key Design Decisions

- MAC address (not host:port) is the stable identifier for both config entries and device registry, so IP changes don't orphan entities.
- `pigpio` library has no type stubs — coordinator uses `dict[int, Any]` for callbacks. Pyright suppressions are only for HA upstream type conflicts (`reportIncompatibleVariableOverride` on `CoordinatorEntity` + `BinarySensorEntity`/`SwitchEntity`).
- Entity state properties use `@cached_property` with `_handle_coordinator_update` invalidation to match modern HA base classes.
- `strings.json` and `translations/en.json` must stay in sync manually.

## Testing

Tests use `FakePigpioPi` (in `conftest.py`) which simulates the pigpio connection with configurable error injection (`read_errors`, `write_errors`, `mode_errors`, `pull_errors`). Integration lifecycle tests use `MockConfigEntry` from `pytest-homeassistant-custom-component`. Coverage must stay above 90% (enforced in CI).

## CI

Two workflows: `ci.yml` (ruff, pyright, pytest with coverage artifact) and `validate.yaml` (HACS + hassfest validation). Pre-commit runs ruff check/format and gitleaks.
