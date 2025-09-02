import appdaemon.plugins.hass.hassapi as hass
from dataclasses import dataclass, asdict
from datetime import datetime

@dataclass
class SystemState:
    """A dataclass to act as a data container for system state."""
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
    last_updated: str

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
                    if state == "Unknown":
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
    def from_home_assistant(cls, app: hass.Hass) -> SystemState | None:
        """
        Factory method to create a SystemState object from Home Assistant sensor values.

        Args:
            app: The AppDaemon app instance.
            Returns:
            A populated SystemState object, or None if sensor data is unavailable.
        """
        grid_power_sensor = app.args["sensors"]["grid_power"]
        battery_soc_sensor = app.args["sensors"]["battery_soc"]
        battery_power_sensor = app.args["sensors"]["battery_power"]
        solar_production_sensor = app.args["sensors"]["solar_production"]
        miner_consumption_sensor = app.args["sensors"]["miner_consumption"]
        chp_production_sensor = app.args["sensors"]["chp_production"]
        try:
            grid_power = float(app.get_state(grid_power_sensor))
            battery_soc = float(app.get_state(battery_soc_sensor))
            battery_power = float(app.get_state(battery_power_sensor))
            solar_production = float(app.get_state(solar_production_sensor)) * 1000 # convert kW to W
            chp_production = float(app.get_state(chp_production_sensor))
            miner_consumption_value = app.get_state(miner_consumption_sensor)
            if miner_consumption_value == "Unknown":
                miner_consumption = 0
            else:
                miner_consumption = float(miner_consumption_value)
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
            app.warning(f"Solar surplus ({solar_surplus}W) is greater than solar production ({solar_production}W). Setting surplus to production value.")
            solar_surplus = solar_production
        # Total surplus is the sum of solar surplus and CHP production
        total_surplus = solar_surplus + chp_production
        state = cls(
            solar_surplus=solar_surplus,
            total_surplus=total_surplus,
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
            last_updated=datetime.now(timezone.utc).isoformat()
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
        }

        state_dict = asdict(self)
        for attr, entity_key in attribute_entity_map.items():
            if entity_key in publish_entities:
                entity_id = publish_entities[entity_key]
                value = state_dict[attr]
                unit = units.get(attr)
                attributes = {"unit_of_measurement": unit} if unit else {}
                hass_app.set_state(entity_id, state=round(value, 2), attributes=attributes)
        
        hass_app.set_state(publish_entities["controller_running"], state="on")
        hass_app.set_state(publish_entities["last_successful_run"], state=self.last_updated)
        
        hass_app.log("Published controller state to Home Assistant.")
