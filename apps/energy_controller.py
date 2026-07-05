import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState
from miner_heater_handler import MinerHeaterHandler
from battery_handler import BatteryHandler
from chp_handler import ChpHandler
from wallbox_handler import WallboxHandler
from attribution_engine import AttributionEngine, split_power_flows


class EnergyController(hass.Hass):
    """The main AppDaemon class for orchestrating energy devices."""

    def initialize(self):
        """Initializes the controller, loads handlers, and schedules the loop."""
        self.log("Initializing Modular Energy Controller.")

        self.dry_run_switch_entity = self.args.get("dry_run_switch_entity")
        if not SystemState.validate_sensors(self, self.args.get("sensors", {})):
            # Do not abort: sensors may simply be unavailable right now.
            # Every control loop re-reads them and skips the cycle on failure.
            self.error(
                "Sensor validation failed. The control loop will skip cycles until sensors are available."
            )

        self.device_handlers = []

        # Instantiate handlers based on configuration. Order matters: the
        # ChpHandler must run after the MinerHeaterHandler so its miner
        # interlock can override the miner's own intent for this cycle.
        if "miner_heater" in self.args:
            self.device_handlers.append(
                MinerHeaterHandler(self, self.args["miner_heater"])
            )
            self.log("Initialized MinerHeaterHandler.")

        if "chp_handler" in self.args:
            self.device_handlers.append(ChpHandler(self, self.args["chp_handler"]))
            self.log("Initialized ChpHandler.")

        if "battery_handler" in self.args:
            self.device_handlers.append(
                BatteryHandler(self, self.args["battery_handler"])
            )
            self.log("Initialized BatteryHandler.")

        if "wallbox" in self.args:
            self.device_handlers.append(WallboxHandler(self, self.args["wallbox"]))
            self.log("Initialized WallboxHandler.")

        # Optional: attribution engine for observing energy flows.
        self.engine = None
        if "priority" in self.args:
            try:
                self.engine = AttributionEngine(
                    self,
                    self.args["priority"]["production"],
                    self.args["priority"]["consumption"],
                )
                self.log("Initialized AttributionEngine.")
            except KeyError as e:
                self.error(f"Missing priority configuration for AttributionEngine: {e}")

        # Schedule the main control loop
        self.run_every(self.control_loop, "now", 60)
        self.log("Control loop scheduled to run every minute.")

    def control_loop(self, kwargs):
        """The main control loop."""
        self.log("Running control loop...")
        state = SystemState.from_home_assistant(self)

        if state is None:
            self.log("Could not retrieve system state. Skipping control loop.")
            # Set controller_running to off if the loop fails
            publish_entities = self.args.get("publish_entities", {})
            if "controller_running" in publish_entities:
                self.set_state(publish_entities["controller_running"], state="off")
            return

        for handler in self.device_handlers:
            try:
                handler.evaluate_and_act(state)
            except Exception as e:
                self.error(f"Handler {type(handler).__name__} failed: {e}")

        state.publish_to_ha(self, self.args["publish_entities"])
        state.execute_actions(self)

        if self.engine:
            try:
                self._run_attribution(state)
            except Exception as e:
                self.error(f"Error during attribution logic: {e}")

        self.log("Control loop finished.")

    def _run_attribution(self, state: SystemState):
        """Calculates and publishes the energy flow attribution matrix."""
        entity_id = self.args.get("publish_attribution_entity")
        if not entity_id:
            return

        producers, consumers = split_power_flows(state, self._get_wallbox_power())
        flow_matrix = self.engine.calculate_flows(producers, consumers)

        attributes = {
            "flow_matrix": flow_matrix,
            "producers_total": producers,
            "consumers_total": consumers,
            "last_updated": state.last_updated,
            "unit_of_measurement": "W",
            "friendly_name": "Energy Flow Attribution",
        }
        # Total production as the main state
        self.set_state(
            entity_id, state=round(sum(producers.values()), 1), attributes=attributes
        )

    def _get_wallbox_power(self) -> float:
        """Reads the current wallbox power draw, if a sensor is configured."""
        sensor = self.args.get("wallbox", {}).get("power_sensor")
        if not sensor:
            return 0.0
        try:
            return float(self.get_state(sensor))
        except (TypeError, ValueError):
            return 0.0
