
import pytest
from unittest.mock import Mock, call
import sys
from datetime import datetime, timezone, timedelta

# Add the apps directory to the python path to allow for imports
sys.path.append('apps')

from miner_heater_handler import MinerHeaterHandler
from energy_controller import EnergyController
from system_state import SystemState


@pytest.fixture
def mock_app():
    """Fixture for a mocked AppDaemon app instance."""
    app = Mock()
    app.get_state.return_value = "off"
    return app

@pytest.fixture
def miner_heater_handler(mock_app):
    """Fixture for a MinerHeaterHandler instance."""
    config = {
        "switch_entity": "switch.miner_heater",
        "power_draw": 1000,
        "min_battery_soc": 50,
    }
    return MinerHeaterHandler(mock_app, config)

@pytest.fixture
def energy_controller(monkeypatch):
    """Fixture for an EnergyController instance."""

    # Prevent initialize from running validation by patching SystemState.validate_sensors
    monkeypatch.setattr(SystemState, "validate_sensors", Mock(return_value=True))

    controller = Mock()
    controller.args = {
        "sensors": {
            "grid_power": "sensor.grid_power",
            "battery_soc": "sensor.battery_soc",
            "battery_power": "sensor.battery_power",
            "solar_production": "sensor.solar_production",
            "miner_consumption": "sensor.miner_consumption",
            "chp_production": "sensor.chp_production",
        },
        "publish_entities": {
            "solar_surplus": "sensor.controller_solar_surplus",
            "total_surplus": "sensor.controller_total_surplus",
            "battery_soc": "sensor.controller_battery_soc",
            "battery_power": "sensor.controller_battery_power",
            "solar_production": "sensor.controller_solar_production",
            "controller_running": "binary_sensor.controller_running",
            "last_successful_run": "sensor.controller_last_successful_run",
        },
        "miner_heater": {
            "switch_entity": "switch.miner_heater",
            "power_limit_entity": "number.miner_power_limit",
            "power_draw": 1000,
            "min_battery_soc": 50
        },
        "dry_run_switch_entity": "switch.dry_run"
    }
    controller.log = Mock()
    controller.error = Mock()
    def mock_get_state(entity_id, **kwargs):
        if entity_id == "switch.dry_run":
            return "off"
        if entity_id == "switch.miner_heater":
            return "on"
        if entity_id == "number.miner_power_limit":
            return { "state": "2000.0", "attributes": {} }
        return "off" # default
    controller.get_state = Mock(side_effect=mock_get_state)
    controller.set_state = Mock()
    controller.run_every = Mock()

    # Bypassing the Hass inheritance for easier testing
    EnergyController.initialize(controller)

    yield controller

class TestMinerHeaterHandler:
    def test_evaluate_and_act_turn_on(self, miner_heater_handler, mock_app):
        """Test turning the miner heater on."""
        state = SystemState(
            solar_surplus=2100,
            total_surplus=2100,
            chp_production=0,
            battery_soc=60,
            battery_power=-500,
            battery_charging=0,
            battery_discharging=500,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=2100,
            miner_consumption=0,
            miner_power_limit=0.0,
            last_updated="now"
        )
        mock_app.get_state.side_effect = [
            "off", # for is_on check
            { "state": "0.0", "attributes": {} } # for power_limit_entity
        ]
        miner_heater_handler.evaluate_and_act(state, is_dry_run=False)
        mock_app.turn_on.assert_called_with("switch.miner_heater")

    def test_evaluate_and_act_turn_off_low_surplus(self, miner_heater_handler, mock_app):
        """Test turning the miner heater off when PV surplus is low."""
        state = SystemState(
            solar_surplus=700,
            total_surplus=700,
            chp_production=0,
            battery_soc=60,
            battery_power=-200,
            battery_charging=0,
            battery_discharging=200,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=900,
            miner_consumption=0,
            miner_power_limit=2000.0,
            last_updated="now"
        )
        mock_app.get_state.return_value = "on"
        miner_heater_handler.evaluate_and_act(state, is_dry_run=False)
        mock_app.turn_off.assert_called_with("switch.miner_heater")

    def test_evaluate_and_act_skip_write_if_limit_unchanged(self, miner_heater_handler, mock_app):
        """Test that a write is skipped if the power limit is unchanged."""
        # The new power limit will be 2000W. We set the current limit to the same.
        state = SystemState(
            solar_surplus=2000,
            total_surplus=2000,
            chp_production=0,
            battery_soc=60,
            battery_power=0,
            battery_charging=0,
            battery_discharging=0,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=2000,
            miner_consumption=0,
            miner_power_limit=2000.0,
            last_updated="now"
        )
        mock_app.get_state.return_value = "on"

        miner_heater_handler.evaluate_and_act(state, is_dry_run=False)

        # turn_on should not be called as it's already on
        mock_app.turn_on.assert_not_called()
        # set_state for power limit should not be called
        mock_app.set_state.assert_not_called()

    def test_evaluate_and_act_skip_write_if_interval_not_passed(self, miner_heater_handler, mock_app, monkeypatch):
        """Test that a write is skipped if the minimum interval has not passed."""
        state = SystemState(
            solar_surplus=3000, # new limit will be 3000W
            total_surplus=3000,
            chp_production=0,
            battery_soc=60,
            battery_power=0,
            battery_charging=0,
            battery_discharging=0,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=3000,
            miner_consumption=0,
            miner_power_limit=2000.0, # current limit is different
            last_updated="now"
        )

        # Mock time
        now = datetime.now(timezone.utc)
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr('miner_heater_handler.datetime', MockDateTime)

        # Mock HA state to include a recent last_write
        last_write_time = (now - timedelta(seconds=30)).isoformat()
        mock_app.get_state.side_effect = [
            "on", # for is_on check
            {
                "state": "2000.0",
                "attributes": {"last_write": last_write_time}
            }
        ]

        miner_heater_handler.evaluate_and_act(state, is_dry_run=False)

        mock_app.set_state.assert_not_called()

    def test_evaluate_and_act_performs_write_when_conditions_met(self, miner_heater_handler, mock_app, monkeypatch):
        """Test that a write is performed when the limit changes and the interval has passed."""
        state = SystemState(
            solar_surplus=3000, # new limit will be 3000W
            total_surplus=3000,
            chp_production=0,
            battery_soc=60,
            battery_power=0,
            battery_charging=0,
            battery_discharging=0,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=3000,
            miner_consumption=0,
            miner_power_limit=2000.0, # current limit is different
            last_updated="now"
        )

        # Mock time
        now = datetime.now(timezone.utc)
        class MockDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now
        monkeypatch.setattr('miner_heater_handler.datetime', MockDateTime)

        # Mock HA state to include an old last_write
        last_write_time = (now - timedelta(seconds=90)).isoformat()
        mock_app.get_state.side_effect = [
            "on", # for is_on check
            {
                "state": "2000.0",
                "attributes": {"last_write": last_write_time, "friendly_name": "Miner Power Limit"}
            }
        ]

        miner_heater_handler.evaluate_and_act(state, is_dry_run=False)

        expected_attributes = {"last_write": now.isoformat(), "friendly_name": "Miner Power Limit"}
        mock_app.set_state.assert_called_once_with(miner_heater_handler.power_limit_entity, state=3000.0, attributes=expected_attributes)

class TestEnergyController:

    def test_control_loop_success(self, energy_controller, monkeypatch):
        """Tests a successful run of the control loop."""
        mock_state = Mock()
        mock_state.total_surplus = 2100
        mock_from_ha = Mock(return_value=mock_state)
        monkeypatch.setattr(SystemState, "from_home_assistant", mock_from_ha)

        EnergyController.control_loop(energy_controller, None)

        mock_from_ha.assert_called_once_with(energy_controller)
        mock_state.publish_to_ha.assert_called_once()

    def test_control_loop_failure(self, energy_controller, monkeypatch):
        """Tests a failed run of the control loop."""
        mock_from_ha = Mock(return_value=None)
        monkeypatch.setattr(SystemState, "from_home_assistant", mock_from_ha)

        EnergyController.control_loop(energy_controller, None)

        mock_from_ha.assert_called_once_with(energy_controller)
        energy_controller.set_state.assert_called_with(energy_controller.args["publish_entities"]["controller_running"], state="off")
    
