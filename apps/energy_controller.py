import appdaemon.plugins.hass.hassapi as hass
from typing import List
from dataclasses import dataclass, asdict
from apps.attribution_engine import AttributionEngine
from apps.wallbox_handler import WallboxHandler

# --- SystemState and MinerHeaterHandler classes remain UNCHANGED ---
@dataclass
class SystemState:
    """A snapshot of the current state of the home energy system."""
    pv_surplus: float
    battery_soc: float
    is_heating_needed: bool
    last_updated: str

class MinerHeaterHandler:
    """Handles all control logic for the Bitcoin Miner as a heater."""
    def __init__(self, app: hass.Hass, config: dict):
        self.app = app
        self.config = config
        self.entity_id = config["switch_entity"]
        self.power_draw = config["power_draw"]
        self.min_soc = config.get("min_battery_soc", 95)

    def evaluate_and_act(self, state: SystemState):
        """The core decision-making logic for this device. (REMAINS ACTIVE)"""
        is_on = self.app.get_state(self.entity_id) == "on"
        can_start = (
            state.is_heating_needed and
            state.pv_surplus > self.power_draw and
            state.battery_soc >= self.min_soc
        )
        if not is_on and can_start:
            self.app.log(f"Miner Control: Turning ON. (Surplus: {state.pv_surplus}W)")
            self.app.turn_on(self.entity_id)
            return

        must_stop = not state.is_heating_needed or state.pv_surplus < (self.power_draw * 0.8)
        if is_on and must_stop:
            self.app.log(f"Miner Control: Turning OFF. (Surplus: {state.pv_surplus}W)")
            self.app.turn_off(self.entity_id)
            return

# --- EnergyController class is MODIFIED ---
class EnergyController(hass.Hass):

    def initialize(self):
        self.log("Initializing Energy Controller...")
        
        self.device_handlers: List[object] = []
        if "miner_heater" in self.args:
            self.log("Found configuration for MinerHeater, setting up handler.")
            self.device_handlers.append(
                MinerHeaterHandler(self, self.args["miner_heater"])
            )
        if "wallbox" in self.args:
            self.log("Found configuration for Wallbox, setting up handler.")
            self.device_handlers.append(
                WallboxHandler(self, self.args["wallbox"])
            )
        
        # --- NEW: Attribution Engine Setup ---
        try:
            prod_priority = self.args["priority"]["production"]
            con_priority = self.args["priority"]["consumption"]
            self.engine = AttributionEngine(self, prod_priority, con_priority)
            self.log("AttributionEngine initialized successfully.")
        except KeyError as e:
            self.log(f"Missing priority configuration for AttributionEngine: {e}", level="ERROR")
            self.engine = None # Disable engine if config is missing
        
        # Start the main control loop (now runs two tasks)
        self.run_minutely(self.control_loop, start_time=self.time())

    def control_loop(self, kwargs):
        """The main execution loop for BOTH control and observation."""
        
        # --- 1. Existing Control Logic (UNCHANGED) ---
        try:
            current_state = self._get_simple_system_state()
            self._publish_simple_state_to_ha(current_state)
            
            for handler in self.device_handlers:
                handler.evaluate_and_act(current_state)
        except Exception as e:
            self.log(f"Error during control logic: {e}", level="ERROR")
            
        # --- 2. NEW: Parallel Attribution Logic ---
        if self.engine:
            try:
                producers, consumers = self._get_full_power_state()
                flow_matrix = self.engine.calculate_flows(producers, consumers)
                self._publish_attribution_to_ha(flow_matrix, producers, consumers)
            except Exception as e:
                self.log(f"Error during attribution logic: {e}", level="ERROR")

    # --- Existing state methods are renamed for clarity ---
    def _get_simple_system_state(self) -> "SystemState":
        """Gathers SENSOR data for the simple (old) control logic."""
        grid_power = float(self.get_state(self.args["sensors_simple"]["grid_power"], default=0))
        
        return SystemState(
            pv_surplus = round(-grid_power if grid_power < 0 else 0, 2),
            battery_soc = float(self.get_state(self.args["sensors_simple"]["battery_soc"], default=0)),
            is_heating_needed = self.get_state(self.args["sensors_simple"]["heating_demand_boolean"]) == "on",
            last_updated = self.datetime().isoformat()
        )

    def _publish_simple_state_to_ha(self, state: SystemState):
        """Publishes the simple (old) state sensors. (UNCHANGED)"""
        entities = self.args.get("publish_entities_simple", {})
        # ... (logic to set_state for pv_surplus, battery_soc, etc.) ...
        self.set_state(entities.get("pv_surplus", "sensor.controller_pv_surplus"), state=state.pv_surplus, attributes={"unit_of_measurement": "W"})
        self.set_state(entities.get("battery_soc", "sensor.controller_battery_soc"), state=state.battery_soc, attributes={"unit_of_measurement": "%"})
        self.set_state(entities.get("heating_demand", "binary_sensor.controller_heating_demand"), state="on" if state.is_heating_needed else "off")


    # --- NEW: State methods for the Attribution Engine ---
    def _get_full_power_state(self) -> (dict, dict):
        """
        Gathers ALL power data and splits it into producers/consumers
        for the AttributionEngine.
        """
        producers = {}
        consumers = {}
        sensors = self.args["sensors_power"]

        # --- Read all power endpoints ---
        pv_power = float(self.get_state(sensors["pv_power"], default=0))
        grid_power = float(self.get_state(sensors["grid_power"], default=0))
        battery_power = float(self.get_state(sensors["battery_power"], default=0))
        miner_power = float(self.get_state(sensors["miner_power"], default=0))
        wallbox_power = float(self.get_state(sensors["wallbox_power"], default=0))

        
        # --- Split into producer/consumer dicts ---
        if pv_power > 0: producers["pv"] = pv_power
        
        if grid_power > 0: producers["grid"] = grid_power      # Grid Import
        else: consumers["grid"] = -grid_power                  # Grid Export
        
        if battery_power < 0: producers["battery"] = -battery_power # Battery Discharging
        else: consumers["battery"] = battery_power             # Battery Charging
        
        if miner_power > 0: consumers["miner"] = miner_power
        if wallbox_power > 0: consumers["wallbox"] = wallbox_power
        
        # --- Calculate residual house load ---
        total_producers = sum(producers.values())
        total_measured_consumers = sum(consumers.values())
        
        residual_load = total_producers - total_measured_consumers
        
        if residual_load < 0:
            self.log(f"Inconsistent sensor data! Measured consumption ({total_measured_consumers}W) > Total production ({total_producers}W).", level="WARNING")
            consumers["house_load"] = 0
        else:
            consumers["house_load"] = round(residual_load, 2)
            
        return producers, consumers

    def _publish_attribution_to_ha(self, flow_matrix: dict, producers: dict, consumers: dict):
        """
        Publishes the entire attribution matrix to a single HA sensor
        for observation.
        """
        entity_id = self.args["publish_attribution_entity"]
        
        attributes = {
            "flow_matrix": flow_matrix,
            "producers_total": producers,
            "consumers_total": consumers,
            "last_updated": self.datetime().isoformat()
        }
        
        main_state = sum(producers.values()) # Total production as main state
        
        self.set_state(
            entity_id,
            state=round(main_state, 1),
            attributes=attributes,
            unit_of_measurement="W",
            friendly_name="Energy Flow Attribution"
        )
