import appdaemon.plugins.hass.hassapi as hass
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

@dataclass(kw_only=True)
class SystemState:
    """A dataclass to act as a data container for system state."""
    # Sensor values
    solar_surplus: float
    total_surplus: float
    chp_production: float
    battery_soc: float
    battery_power: float
    battery_charging: float
    battery_discharging: float
    grid_power: float
    grid_import: float
    grid_export: float
    solar_production: float
    miner_consumption: float
    miner_power_limit: float
    house_consumption: float
    miner_surplus: float
    last_updated: str
    is_dry_run: bool

    # Intended actions from handlers
    miner_intended_power_limit: Optional[float] = None
    miner_intended_switch_state: Optional[str] = None
    battery_intended_charge_switch_state: Optional[str] = None
    chp_intended_switch_state: Optional[str] = None

    @classmethod
    def validate_sensors(cls, app: hass.Hass, sensors: dict) -> bool:
        """
        Validates that all required sensors exist and have valid states in Home Assistant.

        Args:
            app: The AppDaemon app instance.
            sensors: A dictionary of sensor entity IDs.

        Returns:
            True if all sensors are valid, False otherwise.
        """
        for sensor_name, entity_id in sensors.items():
            try:
                state = app.get_state(entity_id)
                if state is None:
                    app.error(f"Sensor '{sensor_name}' ({entity_id}) does not exist.")
                    return False
                if sensor_name == "miner_consumption":
                    if state == "unknown":
                        continue
                    else:
                        float(state) 
                else:
                    float(state)
            except (TypeError, ValueError):
                app.error(f"Sensor '{sensor_name}' ({entity_id}) has a non-numeric state: {state}")
                return False
        app.log("All sensors validated successfully.")
        return True

    @classmethod
    def from_home_assistant(cls, app: hass.Hass) -> Optional["SystemState"]:
        """
        Factory method to create a SystemState object from Home Assistant sensor values.

        Args:
            app: The AppDaemon app instance.
            Returns:
            A populated SystemState object, or None if sensor data is unavailable.
        """
        dry_run_switch_entity = app.args.get("dry_run_switch_entity")
        is_dry_run = False
        if dry_run_switch_entity:
            raw_dry_run_state = app.get_state(dry_run_switch_entity)
            app.log(f"Raw dry-run switch state: '{raw_dry_run_state}'")
            is_dry_run = (raw_dry_run_state == "on")
        grid_power_sensor = app.args["sensors"]["grid_power"]
        battery_soc_sensor = app.args["sensors"]["battery_soc"]
        battery_power_sensor = app.args["sensors"]["battery_power"]
        solar_production_sensor = app.args["sensors"]["solar_production"]
        miner_consumption_sensor = app.args["sensors"]["miner_consumption"]
        chp_production_sensor = app.args["sensors"]["chp_production"]
        miner_power_limit_entity = app.args.get("miner_heater", {}).get("power_limit_entity")
        try:
            grid_power = float(app.get_state(grid_power_sensor))
            battery_soc = float(app.get_state(battery_soc_sensor))
            battery_power = float(app.get_state(battery_power_sensor))
            solar_production = float(app.get_state(solar_production_sensor)) * 1000 # convert kW to W
            chp_production = float(app.get_state(chp_production_sensor))

            miner_consumption_value = app.get_state(miner_consumption_sensor)
            miner_consumption = float(miner_consumption_value) if miner_consumption_value not in ("unknown", "unavailable", None) else 0.0

            miner_power_limit = 0.0
            if miner_power_limit_entity:
                miner_power_limit_value = app.get_state(miner_power_limit_entity)
                if miner_power_limit_value not in ("unknown", "unavailable", None):
                    miner_power_limit = float(miner_power_limit_value)

        except (TypeError, ValueError) as e:
            app.error(f"Error retrieving sensor data: {e}")
            return None
        
        # Positive grid power is drawing from grid, negative is sending power to grid
        grid_import = max(0, grid_power)
        grid_export = max(0, -grid_power)
        # Positive battery power means the battery is charging, negative is supplying power to house
        battery_charging = max(0, battery_power)
        battery_discharging = max(0, -battery_power)
        # Solar surplus is the sum of power being sent to the grid and power being used to charge the battery
        solar_surplus = grid_export + battery_charging - chp_production
        # Validate that solar surplus is not greater than solar production
        if solar_surplus > solar_production:
            app.log(f"Solar surplus ({solar_surplus}W) is greater than solar production ({solar_production}W). Setting surplus to production value.")
            solar_surplus = solar_production
        # Total surplus is the sum of solar surplus and CHP production
        total_surplus = solar_surplus + chp_production

        # House consumption is the total consumption of the house, excluding the miner
        house_consumption = solar_production + grid_import + battery_discharging + chp_production - (grid_export + battery_charging + miner_consumption)

        # Miner surplus is the solar power not used by the house, but counting power for mining or battery charging as available
        miner_surplus = solar_production - house_consumption

        state = cls(
            solar_surplus=solar_surplus,
            total_surplus=total_surplus,
            house_consumption=house_consumption,
            miner_surplus=miner_surplus,
            chp_production=chp_production,
            battery_soc=battery_soc,
            battery_power=battery_power,
            battery_charging=battery_charging,
            battery_discharging=battery_discharging,
            grid_power=grid_power,
            grid_import=grid_import,
            grid_export=grid_export,
            solar_production=solar_production,
            miner_consumption=miner_consumption,
            miner_power_limit=miner_power_limit,
            last_updated=datetime.now(timezone.utc).isoformat(),
            is_dry_run=is_dry_run,
        )
        app.log(f"Current state: {state}")
        return state

    def publish_to_ha(self, hass_app, publish_entities):
        """Publishes the controller's internal state to Home Assistant sensors."""
        
        # Mapping from SystemState attributes to HA entity keys
        attribute_entity_map = {
            "solar_surplus": "solar_surplus",
            "total_surplus": "total_surplus",
            "chp_production": "chp_production",
            "battery_soc": "battery_soc",
            "battery_power": "battery_power",
            "battery_charging": "battery_charging",
            "battery_discharging": "battery_discharging",
            "grid_power": "grid_power",
            "grid_import": "grid_import",
            "grid_export": "grid_export",
            "solar_production": "solar_production",
            "miner_consumption": "miner_consumption",
            "miner_power_limit": "miner_power_limit",
            "house_consumption": "house_consumption",
            "miner_surplus": "miner_surplus",
            "is_dry_run": "is_dry_run",
            "miner_intended_power_limit": "miner_intended_power_limit",
            "miner_intended_switch_state": "miner_intended_switch_state",
            "battery_intended_charge_switch_state": "battery_intended_charge_switch_state",
            "chp_intended_switch_state": "chp_intended_switch_state",
        }

        # Units for the sensors
        units = {
            "solar_surplus": "W",
            "total_surplus": "W",
            "chp_production": "W",
            "battery_soc": "%",
            "battery_power": "W",
            "battery_charging": "W",
            "battery_discharging": "W",
            "grid_power": "W",
            "grid_import": "W",
            "grid_export": "W",
            "solar_production": "W",
            "miner_consumption": "W",
            "miner_power_limit": "W",
            "house_consumption": "W",
            "miner_surplus": "W",
            "miner_intended_power_limit": "W",
        }

        state_dict = asdict(self)
        for attr, entity_key in attribute_entity_map.items():
            if entity_key in publish_entities:
                entity_id = publish_entities[entity_key]
                value = state_dict[attr]

                # Skip publishing None values to avoid errors and retain previous state
                if value is None:
                    continue

                unit = units.get(attr)
                attributes = {"unit_of_measurement": unit} if unit else {}

                final_state = value
                if isinstance(value, float):
                    final_state = round(value, 2)
                elif isinstance(value, bool):
                    final_state = "on" if value else "off"

                hass_app.set_state(entity_id, state=final_state, attributes=attributes)
        
        hass_app.set_state(publish_entities["controller_running"], state="on")
        hass_app.set_state(publish_entities["last_successful_run"], state=self.last_updated)
        
        hass_app.log("Published controller state to Home Assistant.")

    def execute_actions(self, app: hass.Hass):
        """
        Executes the intended actions from the handlers, respecting the dry run mode.
        """
        miner_config = app.args.get("miner_heater", {})
        battery_config = app.args.get("battery_handler", {})
        chp_config = app.args.get("chp_handler", {})

        # Miner Actions
        if self.miner_intended_switch_state is not None:
            entity = miner_config.get("switch_entity")
            if entity and app.get_state(entity) != self.miner_intended_switch_state:
                app.log(f"Intending to turn {self.miner_intended_switch_state} {entity}")
                if not self.is_dry_run:
                    if self.miner_intended_switch_state == 'on':
                        app.turn_on(entity)
                    else:
                        app.turn_off(entity)
                else:
                    app.log(f"[DRY RUN] Would have turned {self.miner_intended_switch_state} {entity}")

        if self.miner_intended_power_limit is not None:
            entity = miner_config.get("power_limit_entity")
            if entity:
                app.log(f"Intending to set miner power limit for {entity} to {self.miner_intended_power_limit} W.")
                if not self.is_dry_run:
                    power_limit_entity_state = app.get_state(entity, attribute="all") or {}
                    current_attributes = power_limit_entity_state.get("attributes", {})
                    new_attributes = current_attributes.copy()
                    new_attributes["last_write"] = datetime.now(timezone.utc).isoformat()
                    app.set_state(entity, state=self.miner_intended_power_limit, attributes=new_attributes)
                else:
                    app.log(f"[DRY RUN] Would have set power limit for {entity} to {self.miner_intended_power_limit} W.")

        # Battery Actions
        if self.battery_intended_charge_switch_state is not None:
            entity = battery_config.get("disable_charge_switch")
            if entity:
                # Note: 'on' means disabled, 'off' means enabled.
                current_state_is_on = app.get_state(entity) == 'on'
                intend_to_be_on = self.battery_intended_charge_switch_state == 'on'
                if current_state_is_on != intend_to_be_on:
                    action = "ON to disable" if intend_to_be_on else "OFF to enable"
                    app.log(f"Intending to turn {action} charging for {entity}")
                    if not self.is_dry_run:
                        if intend_to_be_on:
                            app.turn_on(entity)
                        else:
                            app.turn_off(entity)
                    else:
                        app.log(f"[DRY RUN] Would have turned {action} charging for {entity}")

        # CHP Actions
        if self.chp_intended_switch_state is not None:
            entity = chp_config.get("switch_entity")
            if entity and app.get_state(entity) != self.chp_intended_switch_state:
                app.log(f"Intending to turn {self.chp_intended_switch_state} {entity}")
                if not self.is_dry_run:
                    if self.chp_intended_switch_state == 'on':
                        app.turn_on(entity)
                    else:
                        app.turn_off(entity)
                else:
                    app.log(f"[DRY RUN] Would have turned {self.chp_intended_switch_state} {entity}")
