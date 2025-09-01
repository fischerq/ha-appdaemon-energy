# DESIGN.md: Modular AppDaemon Energy Controller

This document outlines the design for the modular, AppDaemon-based energy controller.

## 1. Core Architecture

The system is designed with a modular architecture to ensure extensibility and maintainability.

*   **EnergyController**: The central AppDaemon class that acts as the orchestrator. It is responsible for gathering system state, publishing it to Home Assistant, and delegating control logic to specialized device handlers.

*   **Device Handlers**: These are individual classes, each responsible for the control logic of a specific device or type of device (e.g., a heater, an EV wallbox). This allows for clean separation of concerns and makes it easy to add new devices without modifying the core controller logic.

*   **SystemState Dataclass**: A simple data container that holds the current state of the system (e.g., PV surplus, battery SOC). This object is passed to each device handler, ensuring they all operate on the same consistent data for a given control loop.

*   **Configuration-Driven**: All aspects of the controller, from entity IDs to device-specific thresholds, are defined in the `apps.yaml` file. This eliminates hard-coded values and makes the system highly configurable.

## 2. Class Structure

### `SystemState` (Dataclass)

A data container for passing state between methods and objects.

```python
@dataclass
class SystemState:
    pv_surplus: float
    battery_soc: float
    is_heating_needed: bool
    last_updated: str
```

### `MinerHeaterHandler`

A handler for a device that acts as a controllable heater.

```python
class MinerHeaterHandler:
    def __init__(self, app, config):
        # ... stores config and entity IDs

    def evaluate_and_act(self, state: SystemState):
        # ... contains the core on/off logic for the heater
```

### `EnergyController` (hass.Hass)

The main AppDaemon application class.

```python
class EnergyController(hass.Hass):
    def initialize(self):
        # ...

    def control_loop(self, kwargs):
        # ...

    def _get_system_state(self) -> SystemState:
        # ...

    def _publish_state_to_ha(self, state: SystemState):
        # ...
```

## 3. Key Methods

### `EnergyController.initialize()`

*   Called once on AppDaemon startup.
*   Initializes an empty list `self.device_handlers`.
*   Reads the `self.args` (from `apps.yaml`) and instantiates the configured device handlers (e.g., `MinerHeaterHandler`).
*   Schedules the `control_loop` to run every minute.

### `EnergyController.control_loop()`

*   The main execution loop.
*   Calls `_get_system_state()` to get fresh data from Home Assistant.
*   Calls `_publish_state_to_ha()` to update the controller's state sensors.
*   Iterates through `self.device_handlers` and calls the `evaluate_and_act()` method on each one, passing the current `SystemState`.

### `EnergyController._get_system_state()`

*   Reads all required input sensor values from Home Assistant (e.g., grid power, battery SOC).
*   Performs any necessary calculations (e.g., calculating `pv_surplus` from grid power).
*   Returns a fully populated `SystemState` object.

### `EnergyController._publish_state_to_ha()`

*   Uses `self.set_state()` to create or update several entities in Home Assistant.
*   This makes the controller's internal state (like calculated PV surplus) visible and usable elsewhere in Home Assistant.

### `MinerHeaterHandler.evaluate_and_act()`

*   Contains the specific logic for when to turn the miner/heater on or off.
*   It bases its decisions on the `SystemState` object it receives and its own configuration (power draw, thresholds, etc.).

## 4. State Publishing

A key feature of this design is that the controller publishes its internal state back to Home Assistant. This is done in the `_publish_state_to_ha` method. It creates the following entities (with configurable names):

*   `sensor.controller_pv_surplus`: The calculated PV surplus in Watts.
*   `sensor.controller_battery_soc`: The battery state of charge.
*   `binary_sensor.controller_heating_demand`: A binary sensor indicating if heating is currently needed.

This allows for easy monitoring, debugging, and use in other automations or dashboards.

## 5. Configuration (`apps.yaml`)

The entire system is configured via `apps.yaml`.

```yaml
energy_manager:
  module: energy_manager
  class: EnergyController

  # Input sensors the controller reads from
  sensors:
    grid_power: sensor.grid_power
    battery_soc: sensor.battery_soc
    heating_demand_boolean: input_boolean.heating_demand

  # Configuration for device handlers
  miner_heater:
    switch_entity: switch.bitcoin_miner
    power_draw: 2000
    min_battery_soc: 95
  
  # Entities the controller will create/publish to
  publish_entities:
    pv_surplus: sensor.controller_pv_surplus
    battery_soc: sensor.controller_battery_soc
    heating_demand: binary_sensor.controller_heating_demand
```
