import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, timezone
from system_state import SystemState
from miner_heater_handler import MinerHeaterHandler

class EnergyController(hass.Hass):
    """The main AppDaemon class for orchestrating energy devices."""

    def initialize(self):
        """Initializes the controller, loads handlers, and schedules the loop."""
        self.log("Hello from the Solalindenstein AppDaemon Energy Manager!")
        self.log("Initializing Modular Energy Controller.")

        # Create dry run switch if it doesn't exist
        self.dry_run_switch_entity = self.args.get("dry_run_switch_entity")
        if self.dry_run_switch_entity and self.get_state(self.dry_run_switch_entity) is None:
            self.log(f"Creating dry run switch: {self.dry_run_switch_entity}")
            self.set_state(self.dry_run_switch_entity, state="off", attributes={"friendly_name": "Energy Manager Dry Run"})

        if not self._validate_sensors():
            self.error("Aborting initialization due to bad sensor configuration.")
            return

        self.device_handlers = []

        # Instantiate handlers based on configuration
        if "miner_heater" in self.args:
            miner_config = self.args["miner_heater"]
            self.device_handlers.append(MinerHeaterHandler(self, miner_config))
            self.log("Initialized MinerHeaterHandler.")

        # Add more handlers here for other devices, e.g., wallbox

        # Schedule the main control loop
        self.run_every(self.control_loop, "now", 60)
        self.log("Control loop scheduled to run every minute.")

    def _validate_sensors(self):
        """Validates that all required sensors are available."""
        sensors = self.args.get("sensors", {})
        for sensor_name, sensor_entity in sensors.items():
            try:
                if self.get_state(sensor_entity) is None:
                    self.error(f"Sensor '{sensor_name}' ({sensor_entity}) not found.")
                    return False
            except Exception as e:
                self.error(f"Error checking sensor '{sensor_name}' ({sensor_entity}): {e}")
                return False
        self.log("All sensors found.")
        return True

    def control_loop(self, kwargs):
        """The main control loop."""
        is_dry_run = self.dry_run_switch_entity and self.get_state(self.dry_run_switch_entity) == "on"
        if is_dry_run:
            self.log("Running in dry-run mode.")
        
        self.log("Running control loop...")
        state = self._get_system_state()

        if state is None:
            self.log("Could not retrieve system state. Skipping control loop.")
            # Set controller_running to off if the loop fails
            publish_entities = self.args["publish_entities"]
            self.set_state(publish_entities["controller_running"], state="off")
            return

        state.publish_to_ha(self, self.args["publish_entities"])

        for handler in self.device_handlers:
            handler.evaluate_and_act(state, is_dry_run)
        self.log("Control loop finished.")

    def _get_system_state(self) -> SystemState:
        """
        Reads sensor values from Home Assistant and calculates the current system state.
        """
        grid_power_sensor = self.args["sensors"]["grid_power"]
        battery_soc_sensor = self.args["sensors"]["battery_soc"]
        battery_power_sensor = self.args["sensors"]["battery_power"]
        solar_production_sensor = self.args["sensors"]["solar_production"]
        miner_consumption_sensor = self.args["sensors"]["miner_consumption"]
        chp_production_sensor = self.args["sensors"]["chp_production"]

        try:
            grid_power = float(self.get_state(grid_power_sensor))
            battery_soc = float(self.get_state(battery_soc_sensor))
            battery_power = float(self.get_state(battery_power_sensor))
            solar_production = float(self.get_state(solar_production_sensor)) * 1000 # convert kW to W
            miner_consumption = float(self.get_state(miner_consumption_sensor))
            chp_production = float(self.get_state(chp_production_sensor))
        except (TypeError, ValueError) as e:
            self.error(f"Error retrieving sensor data: {e}")
            return None

        # Positive grid power is drawing from grid, negative is sending power to grid
        grid_import = max(0, grid_power)
        grid_export = max(0, -grid_power)

        # Positive battery power means the battery is charging, negative is supplying power to house
        battery_charging = max(0, battery_power)
        battery_discharging = max(0, -battery_power)

        # Solar surplus is the sum of power being sent to the grid and power being used to charge the battery
        solar_surplus = grid_export + battery_charging

        # Validate that solar surplus is not greater than solar production
        if solar_surplus > solar_production:
            self.warning(f"Solar surplus ({solar_surplus}W) is greater than solar production ({solar_production}W). Setting surplus to production value.")
            solar_surplus = solar_production

        # Total surplus is the sum of solar surplus and CHP production
        total_surplus = solar_surplus + chp_production

        state = SystemState(
            solar_surplus=solar_surplus,
            total_surplus=total_surplus,
            chp_production=chp_production,
            battery_soc=battery_soc,
            battery_power=battery_power,
            battery_charging=battery_charging,
            battery_discharging=battery_discharging,
            grid_power=grid_power,
            grid_import=grid_import,
            grid_export=grid_export,
            solar_production=solar_production,
            miner_consumption=miner_consumption,
            last_updated=datetime.now(timezone.utc).isoformat()
        )
        self.log(f"Current state: {state}")
        return state
