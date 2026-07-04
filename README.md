# Modular AppDaemon Energy Controller

This AppDaemon application provides a modular and extensible energy controller for Home Assistant. It manages energy-producing and -consuming devices (Bitcoin miner used as heater, CHP plant, battery, EV wallbox) based on real-time system conditions like solar surplus and battery state of charge.

## Project Goal

The primary objective is a configuration-driven energy management system within AppDaemon. The system is built with a modular architecture, allowing for easy addition of new devices and control logic without modifying the core controller.

The controller orchestrates one or more "Device Handlers," each responsible for the logic of a specific device. Handlers record *intended* actions on a shared `SystemState` object; the controller then executes those intents in one place, which also implements the global dry-run mode. The controller publishes its internal state back to Home Assistant, providing visibility into its calculations and decisions, and can optionally attribute energy flows from producers to consumers.

For a detailed explanation of the architecture, class structure, and logic, please see the [DESIGN.md](DESIGN.md) file.

## Setup and Configuration

1.  **Install AppDaemon:** Ensure you have a working AppDaemon setup (`pip install -r requirements.txt`).
2.  **Copy Files:** Place all Python modules from `apps/` and the `apps/apps.yaml` configuration into your AppDaemon `apps` directory.
3.  **Configure `apps.yaml`:** Modify `apps/apps.yaml` to match your Home Assistant entity IDs and desired control parameters. See the comments in that file for the available options. Each handler section (`miner_heater`, `chp_handler`, `battery_handler`, `wallbox`) is optional — a handler is only instantiated when its section is present. The same applies to the attribution engine (`priority` + `publish_attribution_entity`).
4.  **Dry-run mode:** Point `dry_run_switch_entity` at an `input_boolean`. While it is `on`, the controller logs and publishes everything it *would* do without touching any devices.
5.  **Reload AppDaemon:** Reload your AppDaemon apps to start the energy controller.

## Development

Tests do not require the AppDaemon runtime (it is stubbed in `tests/conftest.py`):

```bash
pip install -r requirements-dev.txt
pytest
black --check .
```

The suite contains unit tests per module plus end-to-end tests (`tests/test_e2e_controller.py`) that drive the full control loop against a simulated Home Assistant state machine.
