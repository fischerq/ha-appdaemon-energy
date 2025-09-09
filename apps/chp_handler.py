import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState
from datetime import datetime, timezone

class ChpHandler:
    """A class to contain all logic for controlling the CHP plant."""

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
        self.power_draw_threshold = self.config.get("power_draw_threshold", 1000)
        self.min_wait_time_minutes = self.config.get("min_wait_time", 3)

        # Get miner config from top-level args
        miner_config = self.app.args.get("miner_heater", {})
        self.miner_switch_entity = miner_config.get("switch_entity")
        # The user requested a configurable min wait time for the miner as well.
        self.miner_min_wait_time_minutes = miner_config.get("min_wait_time", 3)


    def _can_toggle(self, entity_id, min_wait_minutes):
        """Checks if an entity can be toggled based on its last_changed attribute."""
        if not entity_id:
            return True # Nothing to check against

        last_changed_str = self.app.get_state(entity_id, attribute="last_changed")
        if last_changed_str:
            # Appdaemon 4.x returns a datetime object, 3.x returns a string.
            if isinstance(last_changed_str, datetime):
                last_changed_dt = last_changed_str
            else:
                last_changed_dt = datetime.fromisoformat(last_changed_str)

            # Ensure the datetime is timezone-aware for comparison
            if last_changed_dt.tzinfo is None:
                last_changed_dt = last_changed_dt.astimezone()

            now = datetime.now(timezone.utc)
            time_since_last_change_seconds = (now - last_changed_dt).total_seconds()

            if time_since_last_change_seconds < min_wait_minutes * 60:
                self.app.log(f"Cannot toggle {entity_id}. Only {time_since_last_change_seconds:.0f}s of {min_wait_minutes*60}s elapsed.")
                return False
        return True

    def evaluate_and_act(self, state: SystemState):
        """
        Main decision-making method to control the CHP.
        """
        chp_is_on = self.app.get_state(self.entity_id) == "on"
        miner_is_on = self.app.get_state(self.miner_switch_entity) == "on" if self.miner_switch_entity else False

        # Determine if the CHP should be on based on house consumption
        should_be_on = state.grid_import > self.power_draw_threshold

        if should_be_on:
            # Condition to turn on CHP is met
            if miner_is_on:
                # If miner is on, we must turn it off first.
                if self._can_toggle(self.miner_switch_entity, self.miner_min_wait_time_minutes):
                    self.app.log(f"CHP: Drawing from grid ({state.grid_import}W > {self.power_draw_threshold}W), but miner is on. Waiting for miner to turn off first.")
                # Do not proceed to turn on CHP in this cycle. Wait for the miner to be off.
            else:
                # Miner is off, and we need power, so turn CHP on if it's currently off.
                if not chp_is_on:
                    if self._can_toggle(self.entity_id, self.min_wait_time_minutes):
                        self.app.log(f"CHP: House consumption is high ({state.house_consumption}W > {self.power_draw_threshold}W) and miner is off. Turning CHP on.")
                        state.chp_intended_switch_state = 'on'
        else:
            # Condition to turn on CHP is not met, so it should be off.
            if chp_is_on:
                if self._can_toggle(self.entity_id, self.min_wait_time_minutes):
                    self.app.log(f"CHP: House consumption is low ({state.house_consumption}W <= {self.power_draw_threshold}W). Turning CHP off.")
                    state.chp_intended_switch_state = 'off'
