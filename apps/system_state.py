from dataclasses import dataclass
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
