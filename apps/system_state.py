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
