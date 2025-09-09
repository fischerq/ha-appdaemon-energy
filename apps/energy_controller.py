import appdaemon.plugins.hass.hassapi as hass
from datetime import datetime, timezone
from system_state import SystemState
from miner_heater_handler import MinerHeaterHandler
from battery_handler import BatteryHandler
from chp_handler import ChpHandler

class EnergyController(hass.Hass):
    """The main AppDaemon class for orchestrating energy devices."""

    def initialize(self):
        """Initializes the controller, loads handlers, and schedules the loop."""
        self.log("Hello from the Solalindenstein AppDaemon Energy Manager!")
        self.log("Initializing Modular Energy Controller.")

        self.dry_run_switch_entity = self.args.get("dry_run_switch_entity")
        if not SystemState.validate_sensors(self, self.args.get("sensors", {})):
            self.error("Aborting initialization due to bad sensor configuration.")
            return

        self.device_handlers = []

        # Instantiate handlers based on configuration
        if "miner_heater" in self.args:
            miner_config = self.args["miner_heater"]
            self.device_handlers.append(MinerHeaterHandler(self, miner_config))
            self.log("Initialized MinerHeaterHandler.")

        if "battery_handler" in self.args:
            battery_config = self.args["battery_handler"]
            self.device_handlers.append(BatteryHandler(self, battery_config))
            self.log("Initialized BatteryHandler.")

        if "chp_handler" in self.args:
            chp_config = self.args["chp_handler"]
            self.device_handlers.append(ChpHandler(self, chp_config))
            self.log("Initialized ChpHandler.")

        # Add more handlers here for other devices, e.g., wallbox

        # Schedule the main control loop
        self.run_every(self.control_loop, "now", 60)
        self.log("Control loop scheduled to run every minute.")

        # Run first control loop immediately
        self.control_loop(None)

    def control_loop(self, kwargs):
        """The main control loop."""
        self.log("Running control loop...")
        state = SystemState.from_home_assistant(self)

        if state is None:
            self.log("Could not retrieve system state. Skipping control loop.")
            # Set controller_running to off if the loop fails
            publish_entities = self.args["publish_entities"]
            self.set_state(publish_entities["controller_running"], state="off")
            return

        for handler in self.device_handlers:
            handler.evaluate_and_act(state)

        state.publish_to_ha(self, self.args["publish_entities"])
        state.execute_actions(self)

        self.log("Control loop finished.")
