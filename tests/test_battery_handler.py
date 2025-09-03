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
            battery_soc=60,
            chp_production=200,
            solar_production=20,
            # Other fields are not relevant for this test
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0, last_updated="now"
        )
        # Mock that the disable switch is currently 'off' (i.e., charging is enabled)
        mock_app.get_state.return_value = "off"

        battery_handler.evaluate_and_act(state, is_dry_run=False)

        # Assert that the switch is turned ON to DISABLE charging
        mock_app.turn_on.assert_called_once_with(battery_handler.disable_charge_switch)
        mock_app.turn_off.assert_not_called()

    def test_enable_charging_when_solar_is_active(self, battery_handler, mock_app):
        """Test that charging is enabled when solar is active, even with high SOC."""
        state = SystemState(
            battery_soc=60,
            chp_production=200,
            solar_production=100, # Solar is active
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0, last_updated="now"
        )
        # Mock that the disable switch is currently 'on' (i.e., charging is disabled)
        mock_app.get_state.return_value = "on"

        battery_handler.evaluate_and_act(state, is_dry_run=False)

        # Assert that the switch is turned OFF to ENABLE charging
        mock_app.turn_off.assert_called_once_with(battery_handler.disable_charge_switch)
        mock_app.turn_on.assert_not_called()

    def test_enable_charging_with_low_soc(self, battery_handler, mock_app):
        """Test that charging is enabled when SOC is low, even with only CHP running."""
        state = SystemState(
            battery_soc=40, # SOC is low
            chp_production=200,
            solar_production=20,
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0, last_updated="now"
        )
        # Mock that the disable switch is currently 'on' (i.e., charging is disabled)
        mock_app.get_state.return_value = "on"

        battery_handler.evaluate_and_act(state, is_dry_run=False)

        # Assert that the switch is turned OFF to ENABLE charging
        mock_app.turn_off.assert_called_once_with(battery_handler.disable_charge_switch)
        mock_app.turn_on.assert_not_called()

    def test_no_action_if_already_disabled(self, battery_handler, mock_app):
        """Test that no action is taken if charging is already disabled and should be."""
        state = SystemState(
            battery_soc=60,
            chp_production=200,
            solar_production=20,
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0, last_updated="now"
        )
        # Mock that the disable switch is already 'on'
        mock_app.get_state.return_value = "on"

        battery_handler.evaluate_and_act(state, is_dry_run=False)

        # Assert that no switch actions are taken
        mock_app.turn_on.assert_not_called()
        mock_app.turn_off.assert_not_called()

    def test_no_action_if_already_enabled(self, battery_handler, mock_app):
        """Test that no action is taken if charging is already enabled and should be."""
        state = SystemState(
            battery_soc=40, # Low SOC means charging should be enabled
            chp_production=200,
            solar_production=20,
            solar_surplus=0, total_surplus=0, battery_power=0, battery_charging=0, battery_discharging=0,
            grid_power=0, grid_import=0, grid_export=0, miner_consumption=0, miner_power_limit=0, last_updated="now"
        )
        # Mock that the disable switch is already 'off'
        mock_app.get_state.return_value = "off"

        battery_handler.evaluate_and_act(state, is_dry_run=False)

        # Assert that no switch actions are taken
        mock_app.turn_on.assert_not_called()
        mock_app.turn_off.assert_not_called()
