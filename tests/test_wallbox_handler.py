import pytest
from unittest.mock import Mock

from wallbox_handler import WallboxHandler
from system_state import SystemState


@pytest.fixture
def mock_app():
    app = Mock()
    return app


@pytest.fixture
def wallbox_handler(mock_app):
    config = {
        "power_sensor": "sensor.wallbox_power",
        "fast_charge_switch": "input_boolean.wallbox_fast_charge",
        "power_limit_entity": "number.wallbox_charge_power",
        "min_surplus_for_charging": 500,
        "max_power": 11000,
    }
    return WallboxHandler(mock_app, config)


def make_state(**overrides):
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


def entity_states(mapping):
    """Helper building a get_state side effect from an entity->state dict."""

    def get_state(entity_id, **kwargs):
        return mapping.get(entity_id)

    return get_state


class TestWallboxHandler:
    def test_fast_charge_override_blocks_automation(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "on",
            }
        )
        state = make_state(solar_surplus=5000)

        assert wallbox_handler.evaluate_and_act(state) is False
        assert state.wallbox_intended_power_limit is None

    def test_charges_with_surplus(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "0.0",
                "number.wallbox_charge_power": "0.0",
            }
        )
        state = make_state(solar_surplus=3500)

        assert wallbox_handler.evaluate_and_act(state) is True
        assert state.wallbox_intended_power_limit == 3500.0

    def test_charge_power_capped_at_max(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "0.0",
                "number.wallbox_charge_power": "0.0",
            }
        )
        state = make_state(solar_surplus=15000)

        wallbox_handler.evaluate_and_act(state)

        assert state.wallbox_intended_power_limit == 11000.0

    def test_own_draw_counts_as_available_power(self, wallbox_handler, mock_app):
        """While charging, the wallbox's draw must not shrink the target.

        Otherwise the limit oscillates: charging at 3 kW consumes the
        surplus, which would immediately drive the limit back to zero.
        """
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "3000.0",
                "number.wallbox_charge_power": "3000.0",
            }
        )
        state = make_state(
            solar_surplus=200
        )  # almost everything eaten by the wallbox itself

        # available = 200 + 3000 = 3200; limit already 3000 -> only 200 diff,
        # above deadband, so it fine-tunes the limit instead of dropping to 0.
        assert wallbox_handler.evaluate_and_act(state) is True
        assert state.wallbox_intended_power_limit == 3200.0

    def test_stops_charging_when_no_surplus(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "300.0",
                "number.wallbox_charge_power": "3000.0",
            }
        )
        state = make_state(solar_surplus=-100)

        assert wallbox_handler.evaluate_and_act(state) is True
        assert state.wallbox_intended_power_limit == 0.0

    def test_idle_without_surplus_is_noop(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "0.0",
                "number.wallbox_charge_power": "0.0",
            }
        )
        state = make_state(solar_surplus=100)

        assert wallbox_handler.evaluate_and_act(state) is False
        assert state.wallbox_intended_power_limit is None

    def test_small_changes_within_deadband_are_skipped(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "3000.0",
                "number.wallbox_charge_power": "3020.0",
            }
        )
        state = make_state(solar_surplus=30)

        assert wallbox_handler.evaluate_and_act(state) is False
        assert state.wallbox_intended_power_limit is None

    def test_unavailable_power_sensor_treated_as_zero(self, wallbox_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {
                "input_boolean.wallbox_fast_charge": "off",
                "sensor.wallbox_power": "unavailable",
                "number.wallbox_charge_power": "0.0",
            }
        )
        state = make_state(solar_surplus=2000)

        assert wallbox_handler.evaluate_and_act(state) is True
        assert state.wallbox_intended_power_limit == 2000.0

    def test_missing_power_limit_entity_skips(self, mock_app):
        handler = WallboxHandler(mock_app, {"power_sensor": "sensor.wallbox_power"})
        state = make_state(solar_surplus=5000)

        assert handler.evaluate_and_act(state) is False
