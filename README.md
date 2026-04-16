# Home Assistant PiGPIO Integration

A custom integration that exposes GPIO pins on a remote Raspberry Pi (via the [pigpio](https://abyz.me.uk/rpi/pigpio/) daemon) as Home Assistant entities.

## Features

Each configured GPIO pin becomes an HA entity:

- **Binary sensor** — for input pins, with optional pull-up/pull-down and invert logic
- **Switch** — for output pins, with optional invert logic

Pins are added and removed through the HA UI; multiple pins per daemon are supported.

## Prerequisites

- A Raspberry Pi (or any host) running [`pigpiod`](https://abyz.me.uk/rpi/pigpio/pigpiod.html), reachable from Home Assistant on the network. Start it with `sudo pigpiod` (default port `8888`).

## Installation

Copy the `custom_components/pigpio` directory into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **PiGPIO**
3. Enter the **Host** and **Port** of the machine running `pigpiod` (default port `8888`)

Once the daemon connection is established, open **Configure** on the integration to manage pins:

- **Add GPIO pin** — specify:
  - **GPIO Number** (0–31)
  - **Name** — used as the entity name
  - **Pin Type** — `Input (Binary Sensor)` or `Output (Switch)`
  - **Pull Mode** — `Pull Up`, `Pull Down`, or `None` (inputs only)
  - **Invert Logic** — flip the reported/applied state
- **Remove GPIO pin** — pick from the list of configured pins

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Task](https://taskfile.dev) — task runner
- [Docker](https://www.docker.com) — for the dev HA instance
- Optionally, [VS Code](https://code.visualstudio.com/) with the **Dev Containers** extension

### Two development paths

**Dev Container (VS Code)** — open the repo in VS Code and run **Reopen in Container**. This uses `.devcontainer/devcontainer.json`, which is based on `ghcr.io/home-assistant/devcontainer:2026.4`, installs `uv` and project dependencies post-create, forwards port `8123`, and preconfigures the Python and Ruff extensions.

**Docker Compose** — `task dev` runs the stable Home Assistant image via `docker-compose.yml`, bind-mounting `custom_components/pigpio` read-only into the container at `/config/custom_components/pigpio`.

### Commands

| Command | Description |
|---|---|
| `task sync` | Install Python dependencies |
| `task pre-commit:install` | Install git pre-commit hooks |
| `task lint` | Run ruff linter and format check |
| `task lint:fix` | Auto-fix lint and formatting issues |
| `task test` | Run pytest |
| `task dev` | Start Home Assistant in Docker |
| `task dev:stop` | Stop Home Assistant |
| `task dev:restart` | Restart Home Assistant (after code changes) |
| `task dev:logs` | Tail Home Assistant logs |

### End-to-end testing

1. **Start Home Assistant:**

   ```bash
   task dev
   ```

   Open http://localhost:8123 and complete the onboarding.

2. **Ensure `pigpiod` is running** on a host reachable from the HA container:

   ```bash
   sudo pigpiod
   ```

3. **Add the integration:**

   Go to **Settings → Devices & Services → Add Integration → PiGPIO** and enter the daemon host and port.

4. **Add a pin:**

   Open **Configure** on the PiGPIO integration → **Add GPIO pin**. Verify the resulting binary sensor or switch entity appears under **Settings → Devices & Services → PiGPIO**.

5. **Iterate:**

   After editing code, pick up changes with:

   ```bash
   task dev:restart
   ```

6. **Clean up:**

   ```bash
   task dev:stop
   ```

No mocked daemon is bundled — full end-to-end testing requires a real `pigpiod`. Unit tests (`task test`) run against `pytest-homeassistant-custom-component` without hardware.
