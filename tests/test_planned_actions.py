import pytest
from unittest.mock import Mock

from battery_handler import BatteryHandler
from miner_heater_handler import MinerHeaterHandler
from optimization_plan import OptimizationPlan
from system_state import SystemState


@pytest.fixture
def mock_app():
    app = Mock()
    app.get_state.return_value = "off"
    return app


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


class TestMinerPlannedActions:
    @pytest.fixture
    def handler(self, mock_app):
        return MinerHeaterHandler(
            mock_app,
            {
                "switch_entity": "switch.miner",
                "power_limit_entity": "number.miner_power_limit",
            },
        )

    def test_planned_turn_on(self, handler, mock_app):
        mock_app.get_state.return_value = "off"
        plan = OptimizationPlan(plan={"miner_heater": ["on"] * 1440})
        state = make_state()

        handler.execute_planned_action(state, plan, minute_of_day=0)

        assert state.miner_intended_switch_state == "on"
        assert state.miner_intended_power_limit is None

    def test_planned_turn_off_resets_power_limit(self, handler, mock_app):
        mock_app.get_state.return_value = "on"
        plan = OptimizationPlan(plan={"miner_heater": ["off"] * 1440})
        state = make_state()

        handler.execute_planned_action(state, plan, minute_of_day=0)

        assert state.miner_intended_switch_state == "off"
        assert state.miner_intended_power_limit == 0

    def test_planned_noop_when_already_matching(self, handler, mock_app):
        mock_app.get_state.return_value = "on"
        plan = OptimizationPlan(plan={"miner_heater": ["on"] * 1440})
        state = make_state()

        handler.execute_planned_action(state, plan, minute_of_day=0)

        assert state.miner_intended_switch_state is None


class TestBatteryPlannedActions:
    @pytest.fixture
    def handler(self, mock_app):
        return BatteryHandler(
            mock_app, {"disable_charge_switch": "switch.disable_charge"}
        )

    def test_planned_disable(self, handler, mock_app):
        mock_app.get_state.return_value = "off"
        plan = OptimizationPlan(plan={"battery_handler": ["on"] * 1440})
        state = make_state()

        handler.execute_planned_action(state, plan, minute_of_day=0)

        assert state.battery_intended_charge_switch_state == "on"

    def test_planned_noop_when_already_matching(self, handler, mock_app):
        mock_app.get_state.return_value = "on"
        plan = OptimizationPlan(plan={"battery_handler": ["on"] * 1440})
        state = make_state()

        handler.execute_planned_action(state, plan, minute_of_day=0)

        assert state.battery_intended_charge_switch_state is None

    def test_unconfigured_switch_is_safe(self, mock_app):
        handler = BatteryHandler(mock_app, {})
        plan = OptimizationPlan(plan={"battery_handler": ["on"] * 1440})
        state = make_state()

        handler.execute_planned_action(state, plan, minute_of_day=0)

        assert state.battery_intended_charge_switch_state is None
