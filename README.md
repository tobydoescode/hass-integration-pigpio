# Home Assistant PiGPIO Integration

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=tobydoescode&repository=hass-integration-pigpio&category=integration)

A [HACS](https://hacs.xyz)-compatible custom integration that exposes GPIO pins on a remote Raspberry Pi (via the [pigpio](https://abyz.me.uk/rpi/pigpio/) daemon) as Home Assistant entities.

## Features

Each configured GPIO pin becomes an HA entity:

- **Binary sensor** — for input pins, with optional pull-up/pull-down and invert logic
- **Switch** — for output pins, with optional invert logic

Pins are added and removed through the HA UI; multiple pins per daemon are supported.

## Prerequisites

- A Raspberry Pi (or any host) running [`pigpiod`](https://abyz.me.uk/rpi/pigpio/pigpiod.html), reachable from Home Assistant on the network. Start it with `sudo pigpiod` (default port `8888`).

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** → **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Install **PiGPIO** and restart Home Assistant

### Manual

Copy the `custom_components/pigpio` directory into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **PiGPIO**
3. Enter the **Host** and **Port** of the machine running `pigpiod` (default port `8888`)

Duplicate daemon entries are detected after trimming host whitespace and normalizing host casing. DNS aliases and IP addresses for the same daemon are not resolved as duplicates.

Once the daemon connection is established, open **Configure** on the integration to manage pins:

- **Add GPIO pin** — specify:
  - **GPIO Number** (0–31)
  - **Name** — used as the entity name
  - **Pin Type** — `Input (Binary Sensor)` or `Output (Switch)`
  - **Invert Logic** — flip the reported/applied state
  - For input pins, the next step asks for **Pull Mode**: `Pull Up`, `Pull Down`, or `None`
  - Output pins do not use pull mode and no pull-mode value is stored
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
| `task lint` | Run Ruff lint and format checks |
| `task lint:fix` | Auto-fix Ruff lint issues and format Python files |
| `task test` | Run pytest |
| `task test:coverage` | Run tests with coverage report |
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

Unit tests use mocked pigpio objects and do not require GPIO hardware. End-to-end testing requires a real `pigpiod` daemon.
