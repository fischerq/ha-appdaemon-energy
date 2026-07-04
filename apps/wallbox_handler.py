import appdaemon.plugins.hass.hassapi as hass
from system_state import SystemState


class WallboxHandler:
    """A class to contain all logic for controlling the EV wallbox."""

    # Ignore power-limit differences below this threshold to avoid
    # rewriting the limit every cycle over sensor noise.
    POWER_DEADBAND_W = 50

    def __init__(self, app, config):
        """
        Initializes the handler.
        Args:
            app: The AppDaemon app instance.
            config: The configuration dictionary for this handler.
        """
        self.app = app
        self.config = config
        self.power_sensor = self.config.get("power_sensor")
        self.fast_charge_switch = self.config.get("fast_charge_switch")
        self.power_limit_entity = self.config.get("power_limit_entity")
        self.min_surplus_for_charging = self.config.get("min_surplus_for_charging", 500)
        self.max_power = self.config.get("max_power", 11000)

    def _read_float(self, entity_id, default=0.0):
        """Reads an entity state as float, tolerating unknown/unavailable."""
        value = self.app.get_state(entity_id)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def evaluate_and_act(self, state: SystemState) -> bool:
        """
        Adjusts the wallbox charge power based on the available solar surplus.
        The intended limit is stored in the SystemState object and applied by
        execute_actions(), which also honours dry-run mode.
        Returns True if an action was requested, False otherwise.
        """
        if not self.power_limit_entity:
            self.app.log(
                "`power_limit_entity` is not configured for WallboxHandler. Skipping."
            )
            return False

        if (
            self.fast_charge_switch
            and self.app.get_state(self.fast_charge_switch) == "on"
        ):
            # Manual override: never touch the wallbox while fast charge is on.
            self.app.log(
                "Wallbox fast charging is manually enabled. No automatic adjustments."
            )
            return False

        current_power = (
            self._read_float(self.power_sensor) if self.power_sensor else 0.0
        )

        # The wallbox's own draw already reduced the measured surplus, so the
        # power available for charging is the surplus plus what the wallbox is
        # currently consuming. Without this the limit would oscillate.
        available_power = state.solar_surplus + current_power

        if available_power > self.min_surplus_for_charging:
            target_limit = round(min(available_power, self.max_power), 2)
        elif current_power > 0:
            # Not enough surplus but the car is still charging: stop it.
            target_limit = 0.0
        else:
            return False

        current_limit = self._read_float(self.power_limit_entity)
        if abs(target_limit - current_limit) < self.POWER_DEADBAND_W:
            return False

        self.app.log(
            f"WALLBOX: Setting charge power limit to {target_limit}W (available: {available_power}W)."
        )
        state.wallbox_intended_power_limit = target_limit
        return True
