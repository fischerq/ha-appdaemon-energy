import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState

class BatteryHandler:
    """A class to contain all logic for controlling the battery charging."""

    def __init__(self, app, config):
        """
        Initializes the handler.
        Args:
            app: The AppDaemon app instance.
            config: The configuration dictionary for this handler.
        """
        self.app = app
        self.config = config
        self.disable_charge_switch = self.config.get("disable_charge_switch")
        self.min_soc_for_chp_charging = self.config.get("min_soc_for_chp_charging", 50)
        self.min_chp_production_for_logic = self.config.get("min_chp_production_for_logic", 100)

    def evaluate_and_act(self, state: SystemState):
        """
        Main decision-making method to control the battery charging.
        This method calculates the intended state and stores it in the SystemState object.
        Args:
            state: The current system state.
        """
        if not self.disable_charge_switch:
            self.app.log("`disable_charge_switch` is not configured for BatteryHandler. Skipping.")
            return

        soc_is_high = state.battery_soc >= self.min_soc_for_chp_charging
        is_charging_from_chp_only = (state.chp_production >= self.min_chp_production_for_logic and
                                     state.grid_export < state.chp_production)

        # Condition to disable charging: SOC is high and the only significant power source is CHP.
        if soc_is_high and is_charging_from_chp_only:
            # We want the disable_charge_switch to be 'on'.
            state.battery_intended_charge_switch_state = 'on'
        # Otherwise, charging should be enabled.
        else:
            # We want the disable_charge_switch to be 'off'.
            state.battery_intended_charge_switch_state = 'off'
