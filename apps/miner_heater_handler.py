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

    def evaluate_and_act(self, state: SystemState, is_dry_run: bool):
        """
        Main decision-making method to control the miner.
        Args:
            state: The current system state.
            is_dry_run: If True, the handler will only log its actions.
        """
        is_on = self.app.get_state(self.entity_id) == "on"

        # The available surplus for the miner is the total surplus plus what the miner is already consuming.
        adjusted_surplus = state.total_surplus + state.miner_consumption

        # Turn on if there is at least a certain amount of total surplus
        if adjusted_surplus >= self.activation_threshold:
            if not is_on:
                self.app.log(f"Turning on miner heater ({self.entity_id}) due to total surplus.")
                if not is_dry_run:
                    self.app.turn_on(self.entity_id)
                else:
                    self.app.log(f"[DRY RUN] Would have turned on {self.entity_id}")

            # Increase the limit in increments up to the max power
            new_power_limit = min(self.max_power, self.activation_threshold + self.power_step * math.floor((adjusted_surplus - self.activation_threshold) / self.power_step))

            if new_power_limit != state.miner_power_limit:
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
                    self.app.log(f"Setting miner power limit to {new_power_limit} W.")
                    if not is_dry_run:
                        current_attributes = power_limit_entity_state.get("attributes", {})
                        new_attributes = current_attributes.copy()
                        new_attributes["last_write"] = datetime.now(timezone.utc).isoformat()
                        self.app.set_state(self.power_limit_entity, state=new_power_limit, attributes=new_attributes)
                    else:
                        self.app.log(f"[DRY RUN] Would have set power limit for {self.power_limit_entity} to {new_power_limit} W.")
                else:
                    self.app.log(f"Skipping miner power limit write for {self.power_limit_entity} due to minimum interval. New limit would be {new_power_limit}W.")
        # Turn off if there is not enough surplus
        else:
            if is_on:
                self.app.log(f"Turning off miner heater ({self.entity_id}) due to insufficient total surplus.")
                if not is_dry_run:
                    self.app.turn_off(self.entity_id)
                else:
                    self.app.log(f"[DRY RUN] Would have turned off {self.entity_id}")
