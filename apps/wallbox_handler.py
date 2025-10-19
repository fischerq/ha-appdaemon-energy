
import appdaemon.plugins.hass.hassapi as hass

class WallboxHandler:
    """Handles all control logic for the EV Wallbox."""

    def __init__(self, app: hass.Hass, config: dict):
        self.app = app
        self.config = config
        self.power_sensor = config["power_sensor"]
        self.fast_charge_switch = config["fast_charge_switch"]
        self.power_limit_entity = config["power_limit_entity"]
        self.min_surplus_for_charging = config.get("min_surplus_for_charging", 500) # Minimum surplus to start charging
        self.max_power = config.get("max_power", 11000) # Max power of the wallbox

    def evaluate_and_act(self, state: "SystemState"):
        """Evaluates wallbox state and acts based on surplus power."""
        is_fast_charging = self.app.get_state(self.fast_charge_switch) == "on"

        if is_fast_charging:
            # If fast charging is on, do nothing (manual override)
            self.app.log("Wallbox fast charging is manually enabled. No automatic adjustments.")
            return

        current_power = float(self.app.get_state(self.power_sensor, default=0))

        # Logic for surplus charging
        if state.pv_surplus > self.min_surplus_for_charging:
            # We have surplus, let's charge
            charge_power = state.pv_surplus
            self.app.log(f"Setting wallbox charge power to {charge_power}W based on surplus.")
            self.app.call_service("number/set_value", entity_id=self.power_limit_entity, value=charge_power)

        elif current_power > 0:
            # No surplus, but it is still charging, so we stop it.
            self.app.log("No PV surplus. Stopping wallbox charging.")
            self.app.call_service("number/set_value", entity_id=self.power_limit_entity, value=0)
