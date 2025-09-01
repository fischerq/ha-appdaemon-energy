# Modular AppDaemon Energy Controller

This AppDaemon application provides a modular and extensible energy controller for Home Assistant. It is designed to manage various energy-consuming devices based on real-time system conditions like PV surplus and battery state of charge.

## Project Goal

The primary objective is to create a configuration-driven energy management system within AppDaemon. The system is built with a modular architecture, allowing for easy addition of new devices and control logic without modifying the core controller.

The controller orchestrates one or more "Device Handlers," each responsible for the logic of a specific device. It also publishes its own internal state back to Home Assistant, providing visibility into its calculations and decisions.

For a detailed explanation of the architecture, class structure, and logic, please see the [DESIGN.md](DESIGN.md) file.

## Setup and Configuration

1.  **Install AppDaemon:** Ensure you have a working AppDaemon setup.
2.  **Copy Files:** Place the `apps/energy_manager.py` file into your AppDaemon `apps` directory and the `apps/apps.yaml` configuration into your `apps` folder.
3.  **Configure `apps.yaml`:** Modify the `apps/apps.yaml` file to match your Home Assistant entity IDs and desired control parameters. The system is configured as follows:

    ```yaml
    energy_manager:
      module: energy_manager
      class: EnergyController

      # Input sensors the controller reads from
      sensors:
        grid_power: sensor.grid_power
        battery_soc: sensor.battery_soc
        heating_demand_boolean: input_boolean.heating_demand

      # Configuration for the first device handler
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

4.  **Reload AppDaemon:** Reload your AppDaemon apps to start the energy controller.
