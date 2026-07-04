import pytest
from unittest.mock import Mock
import unittest

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
            "chp_production": "sensor.chp_production",
        },
        "miner_heater": {"power_limit_entity": "number.miner_power_limit"},
    }
    return app


from datetime import datetime, timezone
from unittest.mock import call


class TestSystemState:
    def test_from_home_assistant_success(self, mock_app):
        """Test successful creation of SystemState from Home Assistant."""
        mock_app.args["dry_run_switch_entity"] = "input_boolean.dry_run"
        mock_app.get_state.side_effect = [
            "off",  # dry_run_switch
            "-1500.0",  # grid_power
            "85.5",  # battery_soc
            "-500.0",  # battery_power
            "2.0",  # solar_production (in kW)
            "100.0",  # chp_production
            "1000.0",  # miner_consumption
            "1200.0",  # miner_power_limit
        ]

        state = SystemState.from_home_assistant(mock_app)

        assert state is not None
        assert not state.is_dry_run
        assert state.grid_power == -1500.0
        assert state.battery_soc == 85.5
        assert state.battery_power == -500.0
        assert state.solar_production == 2000.0  # aW
        assert state.chp_production == 100.0
        assert state.miner_consumption == 1000.0
        assert state.miner_power_limit == 1200.0
        assert state.grid_import == 0
        assert state.grid_export == 1500.0
        assert state.battery_charging == 0
        assert state.battery_discharging == 500.0
        # solar_surplus = battery_power - grid_power - chp_production
        # (net formula: battery discharge and grid import reduce the surplus)
        assert state.solar_surplus == 900.0
        assert state.total_surplus == 1000.0
        # house = solar + chp + grid_power - battery_power - miner
        #       = 2000 + 100 - 1500 + 500 - 1000
        assert state.house_consumption == 100.0
        assert state.miner_surplus == 1900.0
        assert "T" in state.last_updated

    def test_publish_to_ha(self, mock_app):
        """Test that all state variables are published to HA correctly."""
        now = datetime.now(timezone.utc).isoformat()
        state = SystemState(
            solar_surplus=1500.234,
            total_surplus=1600.234,
            house_consumption=500.0,
            miner_surplus=1500.123,
            chp_production=100.0,
            battery_soc=85.567,
            battery_power=-500.789,
            battery_charging=0.0,
            battery_discharging=500.789,
            grid_power=-1000.0,
            grid_import=0.0,
            grid_export=1000.0,
            solar_production=2000.123,
            miner_consumption=950.0,
            miner_power_limit=1200.0,
            last_updated=now,
            is_dry_run=True,
            miner_intended_power_limit=1500.0,
            miner_intended_switch_state="on",
            battery_intended_charge_switch_state="off",
        )

        publish_entities = {
            "solar_surplus": "sensor.controller_solar_surplus",
            "total_surplus": "sensor.controller_total_surplus",
            "chp_production": "sensor.controller_chp_production",
            "battery_soc": "sensor.controller_battery_soc",
            "battery_power": "sensor.controller_battery_power",
            "battery_charging": "sensor.controller_battery_charging",
            "battery_discharging": "sensor.controller_battery_discharging",
            "grid_power": "sensor.controller_grid_power",
            "grid_import": "sensor.controller_grid_import",
            "grid_export": "sensor.controller_grid_export",
            "solar_production": "sensor.controller_solar_production",
            "miner_consumption": "sensor.controller_miner_consumption",
            "miner_power_limit": "sensor.controller_miner_power_limit",
            "is_dry_run": "binary_sensor.controller_is_dry_run",
            "miner_intended_power_limit": "sensor.controller_miner_intended_power_limit",
            "miner_intended_switch_state": "sensor.controller_miner_intended_switch_state",
            "battery_intended_charge_switch_state": "sensor.controller_battery_intended_charge_switch_state",
            "controller_running": "binary_sensor.controller_running",
            "last_successful_run": "sensor.controller_last_successful_run",
        }

        state.publish_to_ha(mock_app, publish_entities)

        expected_calls = [
            # Standard sensor values
            call(
                "sensor.controller_solar_surplus",
                state=1500.23,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_total_surplus",
                state=1600.23,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_chp_production",
                state=100.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_battery_soc",
                state=85.57,
                attributes={"unit_of_measurement": "%"},
            ),
            call(
                "sensor.controller_battery_power",
                state=-500.79,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_battery_charging",
                state=0.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_battery_discharging",
                state=500.79,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_grid_power",
                state=-1000.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_grid_import",
                state=0.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_grid_export",
                state=1000.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_solar_production",
                state=2000.12,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_miner_consumption",
                state=950.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_miner_power_limit",
                state=1200.0,
                attributes={"unit_of_measurement": "W"},
            ),
            # Boolean and intended states
            call("binary_sensor.controller_is_dry_run", state="on", attributes={}),
            call(
                "sensor.controller_miner_intended_power_limit",
                state=1500.0,
                attributes={"unit_of_measurement": "W"},
            ),
            call(
                "sensor.controller_miner_intended_switch_state",
                state="on",
                attributes={},
            ),
            call(
                "sensor.controller_battery_intended_charge_switch_state",
                state="off",
                attributes={},
            ),
            # Controller status
            call("binary_sensor.controller_running", state="on"),
            call("sensor.controller_last_successful_run", state=now),
        ]

        mock_app.set_state.assert_has_calls(expected_calls, any_order=True)
        assert mock_app.set_state.call_count == len(expected_calls)


class TestSystemStateFromHomeAssistant:
    def test_returns_none_on_unavailable_sensor(self, mock_app):
        """A non-numeric core sensor aborts state creation."""
        mock_app.get_state.side_effect = [
            "unavailable",  # grid_power
        ]

        state = SystemState.from_home_assistant(mock_app)

        assert state is None
        mock_app.error.assert_called_once()

    def test_miner_consumption_unavailable_treated_as_zero(self, mock_app):
        """The miner sensor may be unknown/unavailable while it is off."""
        mock_app.get_state.side_effect = [
            "0.0",  # grid_power
            "50.0",  # battery_soc
            "0.0",  # battery_power
            "1.0",  # solar_production (kW)
            "0.0",  # chp_production
            "unavailable",  # miner_consumption
            None,  # miner_power_limit
        ]

        state = SystemState.from_home_assistant(mock_app)

        assert state is not None
        assert state.miner_consumption == 0.0
        assert state.miner_power_limit == 0.0

    def test_solar_surplus_clamped_to_production(self, mock_app):
        """Surplus can never exceed actual solar production."""
        mock_app.get_state.side_effect = [
            "-3000.0",  # grid_power (3 kW export)
            "50.0",  # battery_soc
            "0.0",  # battery_power
            "1.0",  # solar_production (1 kW)
            "0.0",  # chp_production
            "0.0",  # miner_consumption
            "0.0",  # miner_power_limit
        ]

        state = SystemState.from_home_assistant(mock_app)

        assert state.solar_surplus == 1000.0

    def test_dry_run_switch_on(self, mock_app):
        mock_app.args["dry_run_switch_entity"] = "input_boolean.dry_run"
        mock_app.get_state.side_effect = [
            "on",  # dry_run_switch
            "0.0",  # grid_power
            "50.0",  # battery_soc
            "0.0",  # battery_power
            "0.0",  # solar_production
            "0.0",  # chp_production
            "0.0",  # miner_consumption
            "0.0",  # miner_power_limit
        ]

        state = SystemState.from_home_assistant(mock_app)

        assert state.is_dry_run


class TestValidateSensors:
    def test_all_valid(self, mock_app):
        mock_app.get_state.return_value = "42.0"

        assert SystemState.validate_sensors(mock_app, mock_app.args["sensors"])

    def test_missing_sensor(self, mock_app):
        mock_app.get_state.return_value = None

        assert not SystemState.validate_sensors(mock_app, mock_app.args["sensors"])
        mock_app.error.assert_called_once()

    def test_non_numeric_sensor(self, mock_app):
        mock_app.get_state.return_value = "unavailable"

        assert not SystemState.validate_sensors(mock_app, mock_app.args["sensors"])

    def test_miner_consumption_may_be_unavailable(self, mock_app):
        def get_state(entity_id, **kwargs):
            if entity_id == "sensor.miner_consumption":
                return "unavailable"
            return "10.0"

        mock_app.get_state.side_effect = get_state

        assert SystemState.validate_sensors(mock_app, mock_app.args["sensors"])


class TestSystemStateActions:
    def test_execute_actions_normal_run(self, mock_app):
        """Test that actions are executed correctly in a normal run."""
        state = SystemState(
            # Sensor values are not relevant for this test
            solar_surplus=0,
            total_surplus=0,
            chp_production=0,
            battery_soc=0,
            battery_power=0,
            battery_charging=0,
            battery_discharging=0,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=0,
            miner_consumption=0,
            miner_power_limit=0,
            house_consumption=0,
            miner_surplus=0,
            last_updated="now",
            # Set dry run to False
            is_dry_run=False,
            # Set intended actions
            miner_intended_switch_state="on",
            miner_intended_power_limit=3000.0,
            battery_intended_charge_switch_state="off",
        )
        # Add necessary configs to mock_app.args
        mock_app.args["miner_heater"] = {
            "switch_entity": "switch.miner",
            "power_limit_entity": "number.miner_power",
        }
        mock_app.args["battery_handler"] = {
            "disable_charge_switch": "switch.battery_disable_charge"
        }

        # Mock current states
        def get_state_side_effect(entity_id, **kwargs):
            if entity_id == "switch.miner":
                return "off"
            if entity_id == "number.miner_power":
                return {"state": "0", "attributes": {}}
            if entity_id == "switch.battery_disable_charge":
                return "on"

        mock_app.get_state.side_effect = get_state_side_effect

        state.execute_actions(mock_app)

        # Assert miner actions
        mock_app.turn_on.assert_any_call("switch.miner")
        mock_app.set_state.assert_any_call(
            "number.miner_power", state=3000.0, attributes=unittest.mock.ANY
        )
        # Assert battery actions
        mock_app.turn_off.assert_any_call("switch.battery_disable_charge")

    def test_execute_actions_dry_run(self, mock_app):
        """Test that actions are logged but not executed in a dry run."""
        state = SystemState(
            solar_surplus=0,
            total_surplus=0,
            chp_production=0,
            battery_soc=0,
            battery_power=0,
            battery_charging=0,
            battery_discharging=0,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=0,
            miner_consumption=0,
            miner_power_limit=0,
            house_consumption=0,
            miner_surplus=0,
            last_updated="now",
            is_dry_run=True,
            miner_intended_switch_state="on",
            miner_intended_power_limit=3000.0,
            battery_intended_charge_switch_state="off",
        )
        mock_app.args["miner_heater"] = {
            "switch_entity": "switch.miner",
            "power_limit_entity": "number.miner_power",
        }
        mock_app.args["battery_handler"] = {
            "disable_charge_switch": "switch.battery_disable_charge"
        }

        def get_state_side_effect(entity_id, **kwargs):
            if entity_id == "switch.miner":
                return "off"
            if entity_id == "switch.battery_disable_charge":
                return "on"

        mock_app.get_state.side_effect = get_state_side_effect

        state.execute_actions(mock_app)

        # Assert no actions were taken
        mock_app.turn_on.assert_not_called()
        mock_app.set_state.assert_not_called()
        mock_app.turn_off.assert_not_called()

        # Assert logs were made
        expected_logs = [
            call("[DRY RUN] Would have turned on switch.miner"),
            call(
                "[DRY RUN] Would have set power limit for number.miner_power to 3000.0 W."
            ),
            call(
                "[DRY RUN] Would have turned OFF to enable charging for switch.battery_disable_charge"
            ),
        ]
        mock_app.log.assert_has_calls(expected_logs, any_order=True)

    def _make_state(self, **overrides):
        defaults = dict(
            solar_surplus=0,
            total_surplus=0,
            chp_production=0,
            battery_soc=0,
            battery_power=0,
            battery_charging=0,
            battery_discharging=0,
            grid_power=0,
            grid_import=0,
            grid_export=0,
            solar_production=0,
            miner_consumption=0,
            miner_power_limit=0,
            house_consumption=0,
            miner_surplus=0,
            last_updated="now",
            is_dry_run=False,
        )
        defaults.update(overrides)
        return SystemState(**defaults)

    def test_execute_actions_chp(self, mock_app):
        """The CHP switch is toggled when the intent differs from reality."""
        state = self._make_state(chp_intended_switch_state="on")
        mock_app.args["chp_handler"] = {"switch_entity": "switch.chp"}
        mock_app.get_state.side_effect = lambda entity_id, **kw: "off"

        state.execute_actions(mock_app)

        mock_app.turn_on.assert_called_once_with("switch.chp")

    def test_execute_actions_chp_no_change(self, mock_app):
        """No CHP toggle when the switch already matches the intent."""
        state = self._make_state(chp_intended_switch_state="on")
        mock_app.args["chp_handler"] = {"switch_entity": "switch.chp"}
        mock_app.get_state.side_effect = lambda entity_id, **kw: "on"

        state.execute_actions(mock_app)

        mock_app.turn_on.assert_not_called()
        mock_app.turn_off.assert_not_called()

    def test_execute_actions_wallbox(self, mock_app):
        """The wallbox power limit is set via the number service."""
        state = self._make_state(wallbox_intended_power_limit=4200.0)
        mock_app.args["wallbox"] = {"power_limit_entity": "number.wallbox_charge_power"}

        state.execute_actions(mock_app)

        mock_app.call_service.assert_called_once_with(
            "number/set_value", entity_id="number.wallbox_charge_power", value=4200.0
        )

    def test_execute_actions_wallbox_dry_run(self, mock_app):
        """No wallbox service call in dry-run mode."""
        state = self._make_state(is_dry_run=True, wallbox_intended_power_limit=4200.0)
        mock_app.args["wallbox"] = {"power_limit_entity": "number.wallbox_charge_power"}

        state.execute_actions(mock_app)

        mock_app.call_service.assert_not_called()

    def test_execute_actions_no_intents_is_noop(self, mock_app):
        state = self._make_state()
        mock_app.args["miner_heater"] = {"switch_entity": "switch.miner"}

        state.execute_actions(mock_app)

        mock_app.turn_on.assert_not_called()
        mock_app.turn_off.assert_not_called()
        mock_app.call_service.assert_not_called()
