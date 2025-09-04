import math
from datetime import datetime, timezone
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
        self.min_write_interval_seconds = self.config.get("min_write_interval_seconds", 60)

    def evaluate_and_act(self, state: SystemState):
        """
        Main decision-making method to control the miner.
        This method calculates the intended state and stores it in the SystemState object.
        Args:
            state: The current system state.
        """
        is_on = self.app.get_state(self.entity_id) == "on"

        adjusted_surplus = state.miner_surplus

        if adjusted_surplus >= self.activation_threshold:
            # We want the miner to be on.
            state.miner_intended_switch_state = 'on'

            # Only adjust power limit if the surplus is significantly different from the current limit
            if abs(adjusted_surplus - state.miner_power_limit) >= self.power_step:
                # Calculate new power limit
                new_power_limit = min(self.max_power, self.activation_threshold + self.power_step * math.floor((adjusted_surplus - self.activation_threshold) / self.power_step))

                if new_power_limit != state.miner_power_limit:
                    # Check if we are allowed to write based on the interval
                    power_limit_entity_state = self.app.get_state(self.power_limit_entity, attribute="all") or {}
                    last_write_str = power_limit_entity_state.get("attributes", {}).get("last_write")

                    can_write = False
                    if last_write_str is None:
                        can_write = True
                    else:
                        last_write_dt = datetime.fromisoformat(last_write_str)
                        time_since_last_write = (datetime.now(timezone.utc) - last_write_dt).total_seconds()
                        if time_since_last_write >= self.min_write_interval_seconds:
                            can_write = True

                    if can_write:
                        state.miner_intended_power_limit = new_power_limit
                    else:
                        self.app.log(f"Skipping miner power limit write for {self.power_limit_entity} due to minimum interval. New limit would be {new_power_limit}W.")
        else:
            # We want the miner to be off.
            state.miner_intended_switch_state = 'off'

