import pytest
from unittest.mock import Mock
import sys
import unittest


# Add the apps directory to the python path to allow for imports
sys.path.append('apps')

from system_state import SystemState

@pytest.fixture
def mock_app():
    """Fixture for a mocked AppDaemon app instance."""
    app = Mock()
    app.get_state.return_value = "off"
    app.args = {
        "sensors": {
            "grid_power": "sensor.grid_power",
            "battery_soc": "sensor.battery_soc",
            "battery_power": "sensor.battery_power",
            "solar_production": "sensor.solar_production",
            "miner_consumption": "sensor.miner_consumption",
            "chp_production": "sensor.chp_production"
        },
        "miner_heater": {
            "power_limit_entity": "number.miner_power_limit"
        }
    }
    return app

from datetime import datetime, timezone
from unittest.mock import call

class TestSystemState:
    def test_from_home_assistant_success(self, mock_app):
        """Test successful creation of SystemState from Home Assistant."""
        mock_app.get_state.side_effect = [
            "-1500.0",  # grid_power
            "85.5",     # battery_soc
            "-500.0",   # battery_power
            "2.0",      # solar_production (in kW)
            "100.0",    # chp_production
            "1000.0",   # miner_consumption
            "1200.0"    # miner_power_limit
        ]

        state = SystemState.from_home_assistant(mock_app, is_dry_run=False)

        assert state is not None
        assert state.grid_power == -1500.0
        assert state.battery_soc == 85.5
        assert state.battery_power == -500.0
        assert state.solar_production == 2000.0 # aW
        assert state.chp_production == 100.0
        assert state.miner_consumption == 1000.0
        assert state.miner_power_limit == 1200.0
        assert state.grid_import == 0
        assert state.grid_export == 1500.0
        assert state.battery_charging == 0
        assert state.battery_discharging == 500.0
        assert state.solar_surplus == 1400.0
        assert state.total_surplus == 1500.0
        assert "T" in state.last_updated

    def test_publish_to_ha(self, mock_app):
        """Test that all state variables are published to HA correctly."""
        now = datetime.now(timezone.utc).isoformat()
        state = SystemState(
            solar_surplus=1500.234,
            total_surplus=1600.234,
            chp_production=100.0,
            battery_soc=85.567,
            battery_power=-500.789,
            battery_charging=0,
            battery_discharging=500.789,
            grid_power=-1000.0,
            grid_import=0,
            grid_export=1000.0,
            solar_production=2000.123,
            miner_consumption=0,
            miner_power_limit=1200.0,
            last_updated=now,
            is_dry_run=False
        )

        publish_entities = {
            "solar_surplus": "sensor.controller_solar_surplus",
            "total_surplus": "sensor.controller_total_surplus",
            "battery_soc": "sensor.controller_battery_soc",
            "battery_power": "sensor.controller_battery_power",
            "solar_production": "sensor.controller_solar_production",
            "controller_running": "binary_sensor.controller_running",
            "last_successful_run": "sensor.controller_last_successful_run",
        }

        state.publish_to_ha(mock_app, publish_entities)

        expected_calls = [
            call("sensor.controller_solar_surplus", state=1500.23, attributes={"unit_of_measurement": "W"}),
            call("sensor.controller_total_surplus", state=1600.23, attributes={"unit_of_measurement": "W"}),
            call("sensor.controller_battery_soc", state=85.57, attributes={"unit_of_measurement": "%"}),
            call("sensor.controller_battery_power", state=-500.79, attributes={"unit_of_measurement": "W"}),
            call("sensor.controller_solar_production", state=2000.12, attributes={"unit_of_measurement": "W"}),
            call("binary_sensor.controller_running", state="on"),
            call("sensor.controller_last_successful_run", state=now),
        ]

        mock_app.set_state.assert_has_calls(expected_calls, any_order=True)

class TestSystemStateActions:
    def test_execute_actions_normal_run(self, mock_app):
        """Test that actions are executed correctly in a normal run."""
        state = SystemState(
            # Sensor values are not relevant for this test
            solar_surplus=0, total_surplus=0, chp_production=0, battery_soc=0, battery_power=0,
            battery_charging=0, battery_discharging=0, grid_power=0, grid_import=0, grid_export=0,
            solar_production=0, miner_consumption=0, miner_power_limit=0, last_updated="now",
            # Set dry run to False
            is_dry_run=False,
            # Set intended actions
            miner_intended_switch_state='on',
            miner_intended_power_limit=3000.0,
            battery_intended_charge_switch_state='off'
        )
        # Add necessary configs to mock_app.args
        mock_app.args["miner_heater"] = {"switch_entity": "switch.miner", "power_limit_entity": "number.miner_power"}
        mock_app.args["battery_handler"] = {"disable_charge_switch": "switch.battery_disable_charge"}

        # Mock current states
        def get_state_side_effect(entity_id, **kwargs):
            if entity_id == "switch.miner": return "off"
            if entity_id == "number.miner_power": return {"state": "0", "attributes": {}}
            if entity_id == "switch.battery_disable_charge": return "on"
        mock_app.get_state.side_effect = get_state_side_effect

        state.execute_actions(mock_app)

        # Assert miner actions
        mock_app.turn_on.assert_any_call("switch.miner")
        mock_app.set_state.assert_any_call("number.miner_power", state=3000.0, attributes=unittest.mock.ANY)
        # Assert battery actions
        mock_app.turn_off.assert_any_call("switch.battery_disable_charge")

    def test_execute_actions_dry_run(self, mock_app):
        """Test that actions are logged but not executed in a dry run."""
        state = SystemState(
            solar_surplus=0, total_surplus=0, chp_production=0, battery_soc=0, battery_power=0,
            battery_charging=0, battery_discharging=0, grid_power=0, grid_import=0, grid_export=0,
            solar_production=0, miner_consumption=0, miner_power_limit=0, last_updated="now",
            is_dry_run=True,
            miner_intended_switch_state='on',
            miner_intended_power_limit=3000.0,
            battery_intended_charge_switch_state='off'
        )
        mock_app.args["miner_heater"] = {"switch_entity": "switch.miner", "power_limit_entity": "number.miner_power"}
        mock_app.args["battery_handler"] = {"disable_charge_switch": "switch.battery_disable_charge"}

        def get_state_side_effect(entity_id, **kwargs):
            if entity_id == "switch.miner": return "off"
            if entity_id == "switch.battery_disable_charge": return "on"
        mock_app.get_state.side_effect = get_state_side_effect

        state.execute_actions(mock_app)

        # Assert no actions were taken
        mock_app.turn_on.assert_not_called()
        mock_app.set_state.assert_not_called()
        mock_app.turn_off.assert_not_called()

        # Assert logs were made
        expected_logs = [
            call("[DRY RUN] Would have turned on switch.miner"),
            call("[DRY RUN] Would have set power limit for number.miner_power to 3000.0 W."),
            call("[DRY RUN] Would have turned OFF to enable charging for switch.battery_disable_charge")
        ]
        mock_app.log.assert_has_calls(expected_logs, any_order=True)
