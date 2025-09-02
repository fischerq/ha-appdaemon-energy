import math
import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState

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
        self.power_limit_entity = self.config.get("power_limit_entity")
        self.activation_threshold = self.config.get("activation_threshold", 2000)
        self.max_power = self.config.get("max_power", 6000)
        self.power_step = self.config.get("power_step", 1000)

    def evaluate_and_act(self, state: SystemState, is_dry_run: bool):
        """
        Main decision-making method to control the miner.
        Args:
            state: The current system state.
            is_dry_run: If True, the handler will only log its actions.
        """
        is_on = self.app.get_state(self.entity_id) == "on"

        # Turn on if there is at least a certain amount of total surplus
        if state.total_surplus >= self.activation_threshold:
            if not is_on:
                self.app.log(f"[DRY RUN] Turning on miner heater ({self.entity_id}) due to total surplus." if is_dry_run else f"Turning on miner heater ({self.entity_id}) due to total surplus.")
                if not is_dry_run:
                    self.app.turn_on(self.entity_id)

            # Increase the limit in increments up to the max power
            power_limit = min(self.max_power, self.activation_threshold + self.power_step * math.floor((state.total_surplus - self.activation_threshold) / self.power_step))
            self.app.log(f"[DRY RUN] Setting miner power limit to {power_limit} W." if is_dry_run else f"Setting miner power limit to {power_limit} W.")
            if not is_dry_run:
                self.app.call_service("number/set_value", entity_id=self.power_limit_entity, value=power_limit)

        # Turn off if there is not enough surplus
        else:
            if is_on:
                self.app.log(f"[DRY RUN] Turning off miner heater ({self.entity_id}) due to insufficient total surplus." if is_dry_run else f"Turning off miner heater ({self.entity_id}) due to insufficient total surplus.")
                if not is_dry_run:
                    self.app.turn_off(self.entity_id)
