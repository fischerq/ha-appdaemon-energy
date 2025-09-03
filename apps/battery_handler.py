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
        self.max_solar_for_chp_logic = self.config.get("max_solar_for_chp_logic", 50)

    def evaluate_and_act(self, state: SystemState, is_dry_run: bool):
        """
        Main decision-making method to control the battery charging.
        Args:
            state: The current system state.
            is_dry_run: If True, the handler will only log its actions.
        """
        if not self.disable_charge_switch:
            self.app.log("`disable_charge_switch` is not configured for BatteryHandler. Skipping.")
            return

        is_charging_disabled = self.app.get_state(self.disable_charge_switch) == 'on'

        soc_is_high = state.battery_soc >= self.min_soc_for_chp_charging
        is_charging_from_chp_only = (state.chp_production >= self.min_chp_production_for_logic and
                                     state.solar_production < self.max_solar_for_chp_logic)

        # Condition to disable charging: SOC is high and the only significant power source is CHP.
        if soc_is_high and is_charging_from_chp_only:
            if not is_charging_disabled:
                self.app.log(f"Disabling battery charging from CHP. SOC: {state.battery_soc}%, Solar: {state.solar_production}W, CHP: {state.chp_production}W")
                if not is_dry_run:
                    self.app.turn_on(self.disable_charge_switch) # Turn ON to DISABLE charging
                else:
                    self.app.log(f"[DRY RUN] Would have turned ON {self.disable_charge_switch} to disable charging.")
        # Otherwise, charging should be enabled.
        else:
            if is_charging_disabled:
                self.app.log("Enabling battery charging.")
                if not is_dry_run:
                    self.app.turn_off(self.disable_charge_switch) # Turn OFF to ENABLE charging
                else:
                    self.app.log(f"[DRY RUN] Would have turned OFF {self.disable_charge_switch} to enable charging.")
