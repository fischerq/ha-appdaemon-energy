import math
from datetime import datetime, timezone
import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState
from optimization_plan import OptimizationPlan


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
        self.min_write_interval_seconds = self.config.get(
            "min_write_interval_seconds", 60
        )

    def evaluate_and_act(self, state: SystemState) -> bool:
        """
        Main decision-making method for URGENT control of the miner.
        Returns True if an action was taken, False otherwise.
        """
        if not self.entity_id:
            self.app.log(
                "`switch_entity` is not configured for MinerHeaterHandler. Skipping."
            )
            return False

        action_taken = False
        is_on = self.app.get_state(self.entity_id) == "on"
        adjusted_surplus = state.miner_surplus
        should_be_on = adjusted_surplus >= self.activation_threshold

        # The intent is always recorded; execute_actions() only toggles the
        # switch when the intent differs from the actual switch state.
        state.miner_intended_switch_state = "on" if should_be_on else "off"
        if should_be_on != is_on:
            action_taken = True
            if should_be_on:
                self.app.log("MINER: Urgent action to turn ON due to high surplus.")
            else:
                self.app.log("MINER: Urgent action to turn OFF due to low surplus.")
                state.miner_intended_power_limit = 0

        if should_be_on and self.power_limit_entity:
            new_power_limit = min(
                self.max_power,
                self.activation_threshold
                + self.power_step
                * math.floor(
                    (adjusted_surplus - self.activation_threshold) / self.power_step
                ),
            )
            if abs(new_power_limit - state.miner_power_limit) >= self.power_step:
                power_limit_entity_state = (
                    self.app.get_state(self.power_limit_entity, attribute="all") or {}
                )
                last_write_str = power_limit_entity_state.get("attributes", {}).get(
                    "last_write"
                )
                can_write = False
                if last_write_str is None:
                    can_write = True
                else:
                    try:
                        last_write_dt = datetime.fromisoformat(last_write_str)
                    except (TypeError, ValueError):
                        last_write_dt = None
                    if last_write_dt is None:
                        can_write = True
                    else:
                        if last_write_dt.tzinfo is None:
                            last_write_dt = last_write_dt.replace(tzinfo=timezone.utc)
                        time_since_last_write = (
                            datetime.now(timezone.utc) - last_write_dt
                        ).total_seconds()
                        if time_since_last_write >= self.min_write_interval_seconds:
                            can_write = True

                if can_write:
                    self.app.log(
                        f"MINER: Urgent action to set power limit to {new_power_limit}W."
                    )
                    state.miner_intended_power_limit = new_power_limit
                    action_taken = True

        return action_taken

    def execute_planned_action(
        self, state: SystemState, plan: OptimizationPlan, minute_of_day: int
    ):
        """Executes a planned action from the optimization plan."""
        planned_action = plan.get_action_for_handler("miner_heater", minute_of_day)
        if planned_action is None:
            return

        is_on = self.app.get_state(self.entity_id) == "on"
        planned_on = planned_action == "on"

        if planned_on != is_on:
            self.app.log(f"MINER: Executing planned action to turn {planned_action}.")
            state.miner_intended_switch_state = planned_action
            if not planned_on:
                state.miner_intended_power_limit = 0
