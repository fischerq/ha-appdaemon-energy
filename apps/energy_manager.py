import appdaemon.plugins.hass.hassapi as hass
from dataclasses import dataclass
from datetime import datetime, timezone

@dataclass
class SystemState:
    """A dataclass to act as a data container for system state."""
    pv_surplus: float
    battery_soc: float
    is_heating_needed: bool
    battery_power: float
    solar_production: float
    last_updated: str

class MinerHeaterHandler:
    """A class to contain all logic for controlling the miner."""

    def __init__(self, app, config):
        """
        Initializes the handler.
        Args:
            app: The AppDaemon app instance.
            config: The configuration dictionary for this handler.
        """
        self.app = app
        self.config = config
        self.entity_id = self.config.get("switch_entity")
        self.power_draw = self.config.get("power_draw")
        self.min_soc = self.config.get("min_battery_soc")

    def evaluate_and_act(self, state: SystemState):
        """
        Main decision-making method to control the miner.
        Args:
            state: The current system state.
        """
        is_on = self.app.get_state(self.entity_id) == "on"

        # Start Logic
        if not is_on and \
           state.is_heating_needed and \
           state.pv_surplus > self.power_draw and \
           state.battery_soc >= self.min_soc:
            self.app.log(f"Turning on miner heater ({self.entity_id}) due to heating need and PV surplus.")
            self.app.turn_on(self.entity_id)

        # Stop Logic
        elif is_on and \
             (not state.is_heating_needed or \
              state.pv_surplus < self.power_draw * 0.8):
            self.app.log(f"Turning off miner heater ({self.entity_id}). Heating needed: {state.is_heating_needed}, PV Surplus: {state.pv_surplus}")
            self.app.turn_off(self.entity_id)


class EnergyController(hass.Hass):
    """The main AppDaemon class for orchestrating energy devices."""

    def initialize(self):
        """Initializes the controller, loads handlers, and schedules the loop."""
        self.log("Hello from the Solalindenstein AppDaemon Energy Manager!")
        self.log("Initializing Modular Energy Controller.")
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

    def control_loop(self, kwargs):
        """The main control loop."""
        self.log("Running control loop...")
        state = self._get_system_state()

        if state is None:
            self.log("Could not retrieve system state. Skipping control loop.")
            # Set controller_running to off if the loop fails
            publish_entities = self.args["publish_entities"]
            self.set_state(publish_entities["controller_running"], state="off")
            return

        self._publish_state_to_ha(state)

        for handler in self.device_handlers:
            handler.evaluate_and_act(state)
        self.log("Control loop finished.")

    def _get_system_state(self) -> SystemState:
        """
        Reads sensor values from Home Assistant and calculates the current system state.
        """
        grid_power_sensor = self.args["sensors"]["grid_power"]
        battery_soc_sensor = self.args["sensors"]["battery_soc"]
        heating_demand_sensor = self.args["sensors"]["heating_demand_boolean"]
        battery_power_sensor = self.args["sensors"]["battery_power"]
        solar_production_sensor = self.args["sensors"]["solar_production"]

        try:
            grid_power = float(self.get_state(grid_power_sensor))
            battery_soc = float(self.get_state(battery_soc_sensor))
            battery_power = float(self.get_state(battery_power_sensor))
            solar_production = float(self.get_state(solar_production_sensor))
        except (TypeError, ValueError) as e:
            self.error(f"Error retrieving sensor data: {e}")
            return None

        is_heating_needed = self.get_state(heating_demand_sensor) == "on"

        # Surplus is negative grid power
        pv_surplus = -grid_power

        state = SystemState(
            pv_surplus=pv_surplus,
            battery_soc=battery_soc,
            is_heating_needed=is_heating_needed,
            battery_power=battery_power,
            solar_production=solar_production,
            last_updated=datetime.now(timezone.utc).isoformat()
        )
        self.log(f"Current state: {state}")
        return state

    def _publish_state_to_ha(self, state: SystemState):
        """
        Publishes the controller's internal state to Home Assistant sensors.
        """
        publish_entities = self.args["publish_entities"]

        # Publish PV surplus
        self.set_state(publish_entities["pv_surplus"], state=round(state.pv_surplus, 2), attributes={"unit_of_measurement": "W"})
        
        # Publish Battery SOC
        self.set_state(publish_entities["battery_soc"], state=round(state.battery_soc, 2), attributes={"unit_of_measurement": "%"})
        
        # Publish Heating Demand
        self.set_state(publish_entities["heating_demand"], state="on" if state.is_heating_needed else "off")

        # Publish Battery Power
        self.set_state(publish_entities["battery_power"], state=round(state.battery_power, 2), attributes={"unit_of_measurement": "W"})

        # Publish Solar Production
        self.set_state(publish_entities["solar_production"], state=round(state.solar_production, 2), attributes={"unit_of_measurement": "W"})

        # Publish Controller Status
        self.set_state(publish_entities["controller_running"], state="on")
        self.set_state(publish_entities["last_successful_run"], state=state.last_updated)

        self.log("Published controller state to Home Assistant.")
