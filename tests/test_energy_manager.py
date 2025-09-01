
import pytest
from unittest.mock import Mock, call
import sys
from datetime import datetime, timezone

# Add the apps directory to the python path to allow for imports
sys.path.append('apps')

from energy_manager import MinerHeaterHandler, EnergyController, SystemState


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
def energy_controller():
    """Fixture for an EnergyController instance."""
    with Mock() as controller:
        controller.args = {
            "sensors": {
                "grid_power": "sensor.grid_power",
                "battery_soc": "sensor.battery_soc",
                "heating_demand_boolean": "input_boolean.heating_demand",
                "battery_power": "sensor.battery_power",
                "solar_production": "sensor.solar_production",
            },
            "publish_entities": {
                "pv_surplus": "sensor.controller_pv_surplus",
                "battery_soc": "sensor.controller_battery_soc",
                "heating_demand": "binary_sensor.controller_heating_demand",
                "battery_power": "sensor.controller_battery_power",
                "solar_production": "sensor.controller_solar_production",
                "controller_running": "binary_sensor.controller_running",
                "last_successful_run": "sensor.controller_last_successful_run",
            },
            "miner_heater": {
                "switch_entity": "switch.miner_heater",
                "power_draw": 1000,
                "min_battery_soc": 50
            }
        }
        controller.log = Mock()
        controller.error = Mock()
        controller.get_state = Mock()
        controller.set_state = Mock()
        controller.run_every = Mock()
        
        # Bypassing the Hass inheritance for easier testing
        EnergyController.initialize(controller)

        yield controller

class TestMinerHeaterHandler:
    def test_evaluate_and_act_turn_on(self, miner_heater_handler, mock_app):
        """Test turning the miner heater on."""
        state = SystemState(
            pv_surplus=1200,
            battery_soc=60,
            is_heating_needed=True,
            battery_power=-500,
            solar_production=1500,
            last_updated="now"
        )
        mock_app.get_state.return_value = "off"
        miner_heater_handler.evaluate_and_act(state)
        mock_app.turn_on.assert_called_with("switch.miner_heater")

    def test_evaluate_and_act_turn_off_no_heating_need(self, miner_heater_handler, mock_app):
        """Test turning the miner heater off when heating is not needed."""
        state = SystemState(
            pv_surplus=1200,
            battery_soc=60,
            is_heating_needed=False,
            battery_power=-500,
            solar_production=1500,
            last_updated="now"
        )
        mock_app.get_state.return_value = "on"
        miner_heater_handler.evaluate_and_act(state)
        mock_app.turn_off.assert_called_with("switch.miner_heater")

    def test_evaluate_and_act_turn_off_low_surplus(self, miner_heater_handler, mock_app):
        """Test turning the miner heater off when PV surplus is low."""
        state = SystemState(
            pv_surplus=700, # less than 80% of power_draw
            battery_soc=60,
            is_heating_needed=True,
            battery_power=-200,
            solar_production=900,
            last_updated="now"
        )
        mock_app.get_state.return_value = "on"
        miner_heater_handler.evaluate_and_act(state)
        mock_app.turn_off.assert_called_with("switch.miner_heater")

class TestEnergyController:

    def test_control_loop_success(self, energy_controller):
        """Tests a successful run of the control loop."""
        # We need to mock the return of _get_system_state and _publish_state_to_ha
        # as these are the core methods called by control_loop.
        EnergyController._get_system_state = Mock(return_value=SystemState(pv_surplus=1, battery_soc=1, is_heating_needed=True, battery_power=1, solar_production=1, last_updated="now"))
        EnergyController._publish_state_to_ha = Mock()

        EnergyController.control_loop(energy_controller, None)

        EnergyController._get_system_state.assert_called_once()
        EnergyController._publish_state_to_ha.assert_called_once()

    def test_control_loop_failure(self, energy_controller):
        """Tests a failed run of the control loop."""
        EnergyController._get_system_state = Mock(return_value=None)
        EnergyController._publish_state_to_ha = Mock()

        EnergyController.control_loop(energy_controller, None)

        EnergyController._get_system_state.assert_called_once()
        EnergyController._publish_state_to_ha.assert_not_called()
        energy_controller.set_state.assert_called_with("binary_sensor.controller_running", state="off")
    
    def test_get_system_state_success(self, energy_controller):
        """Test successful retrieval of system state."""
        energy_controller.get_state.side_effect = [
            "-1500.0",  # grid_power
            "85.5",     # battery_soc
            "-500.0",   # battery_power
            "2000.0",   # solar_production
            "on"        # heating_demand
        ]

        state = EnergyController._get_system_state(energy_controller)

        assert state.pv_surplus == 1500.0
        assert state.battery_soc == 85.5
        assert state.battery_power == -500.0
        assert state.solar_production == 2000.0
        assert state.is_heating_needed is True

    def test_get_system_state_failure(self, energy_controller):
        """Test failure to retrieve system state due to invalid sensor data."""
        energy_controller.get_state.return_value = "unavailable"
        state = EnergyController._get_system_state(energy_controller)
        assert state is None
        energy_controller.error.assert_called()

    def test_publish_state_to_ha(self, energy_controller):
        """Test that all state variables are published to HA correctly."""
        now = datetime.now(timezone.utc).isoformat()
        state = SystemState(
            pv_surplus=1500.234,
            battery_soc=85.567,
            is_heating_needed=True,
            battery_power=-500.789,
            solar_production=2000.123,
            last_updated=now
        )

        EnergyController._publish_state_to_ha(energy_controller, state)

        expected_calls = [
            call("sensor.controller_pv_surplus", state=1500.23, attributes={"unit_of_measurement": "W"}),
            call("sensor.controller_battery_soc", state=85.57, attributes={"unit_of_measurement": "%"}),
            call("binary_sensor.controller_heating_demand", state="on"),
            call("sensor.controller_battery_power", state=-500.79, attributes={"unit_of_measurement": "W"}),
            call("sensor.controller_solar_production", state=2000.12, attributes={"unit_of_measurement": "W"}),
            call("binary_sensor.controller_running", state="on"),
            call("sensor.controller_last_successful_run", state=now),
        ]

        energy_controller.set_state.assert_has_calls(expected_calls, any_order=True)
