import pytest
from unittest.mock import Mock
import sys

# Add the apps directory to the python path to allow for imports
sys.path.append('apps')

from battery_handler import BatteryHandler
from system_state import SystemState

@pytest.fixture
def mock_app():
    """Fixture for a mocked AppDaemon app instance."""
    app = Mock()
    app.get_state.return_value = "off"
    app.log = Mock()
    app.turn_on = Mock()
    app.turn_off = Mock()
    return app

@pytest.fixture
def battery_handler(mock_app):
    """Fixture for a BatteryHandler instance."""
    config = {
        "disable_charge_switch": "switch.victron_vebus_disablecharge_227",
        "min_soc_for_chp_charging": 50,
        "min_chp_production_for_logic": 100,
        "max_solar_for_chp_logic": 50
    }
    return BatteryHandler(mock_app, config)

class TestBatteryHandler:
    def test_disable_charging_on_chp_with_high_soc(self, battery_handler, mock_app):
        """Test that charging is disabled when SOC is high and only CHP is running."""
        state = SystemState(
            battery_soc=60, chp_production=200, solar_production=20,
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0,
            last_updated="now", is_dry_run=False
        )

        battery_handler.evaluate_and_act(state)

        assert state.battery_intended_charge_switch_state == 'on'

    def test_enable_charging_when_solar_is_active(self, battery_handler, mock_app):
        """Test that charging is enabled when solar is active, even with high SOC."""
        state = SystemState(
            battery_soc=60, chp_production=200, solar_production=100,
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0,
            last_updated="now", is_dry_run=False
        )

        battery_handler.evaluate_and_act(state)

        assert state.battery_intended_charge_switch_state == 'off'

    def test_enable_charging_with_low_soc(self, battery_handler, mock_app):
        """Test that charging is enabled when SOC is low, even with only CHP running."""
        state = SystemState(
            battery_soc=40, chp_production=200, solar_production=20,
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0,
            last_updated="now", is_dry_run=False
        )

        battery_handler.evaluate_and_act(state)

        assert state.battery_intended_charge_switch_state == 'off'
