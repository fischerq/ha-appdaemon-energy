import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState
from optimization_plan import OptimizationPlan

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

    def evaluate_and_act(self, state: SystemState) -> bool:
        """
        Main decision-making method for URGENT control of the battery charging.
        This method calculates the intended state and stores it in the SystemState object.
        Returns True if an action was taken, False otherwise.
        Args:
            state: The current system state.
        """
        if not self.disable_charge_switch:
            self.app.log("`disable_charge_switch` is not configured for BatteryHandler. Skipping.")
            return False

        action_taken = False
        current_switch_state_is_on = self.app.get_state(self.disable_charge_switch) == 'on'

        soc_is_high = state.battery_soc >= self.min_soc_for_chp_charging
        is_charging_from_chp_only = (state.chp_production >= self.min_chp_production_for_logic and
                                     state.grid_export < state.chp_production)

        # We want the disable_charge_switch to be 'on' to disable charging.
        intended_switch_state_is_on = soc_is_high and is_charging_from_chp_only

        if intended_switch_state_is_on and not current_switch_state_is_on:
            # We want to turn the switch ON (disable charging)
            state.battery_intended_charge_switch_state = 'on'
            self.app.log("BATTERY: Urgent action to disable charging.")
            action_taken = True
        elif not intended_switch_state_is_on and current_switch_state_is_on:
            # We want to turn the switch OFF (enable charging)
            state.battery_intended_charge_switch_state = 'off'
            self.app.log("BATTERY: Urgent action to enable charging.")
            action_taken = True
        
        return action_taken

    def execute_planned_action(self, state: SystemState, plan: OptimizationPlan, minute_of_day: int):
        """Executes a planned action from the optimization plan."""
        planned_action = plan.get_action_for_handler("battery_handler", minute_of_day)
        if planned_action is None:
            return

        current_switch_state_is_on = self.app.get_state(self.disable_charge_switch) == 'on'
        planned_on = planned_action == 'on'

        if planned_on != current_switch_state_is_on:
            self.app.log(f"BATTERY: Executing planned action to turn {planned_action} disable_charge_switch.")
            state.battery_intended_charge_switch_state = planned_action
