import pytest
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta

from chp_handler import ChpHandler
from optimization_plan import OptimizationPlan
from system_state import SystemState

LONG_AGO = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
JUST_NOW = datetime.now(timezone.utc).isoformat()


@pytest.fixture
def mock_app():
    app = Mock()
    app.args = {
        "miner_heater": {
            "switch_entity": "switch.miner",
            "min_wait_time": 3,
        }
    }
    return app


@pytest.fixture
def chp_handler(mock_app):
    config = {
        "switch_entity": "switch.chp",
        "power_draw_threshold": 1000,
        "min_wait_time": 3,
    }
    return ChpHandler(mock_app, config)


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


def entity_states(states, last_changed=None):
    last_changed = last_changed or {}

    def get_state(entity_id, attribute=None, **kwargs):
        if attribute == "last_changed":
            return last_changed.get(entity_id, LONG_AGO)
        return states.get(entity_id)

    return get_state


class TestChpEvaluateAndAct:
    def test_turns_on_when_grid_import_high_and_miner_off(self, chp_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "off", "switch.miner": "off"}
        )
        state = make_state(grid_import=2500)

        assert chp_handler.evaluate_and_act(state) is True
        assert state.chp_intended_switch_state == "on"

    def test_interlock_requests_miner_off_before_starting(self, chp_handler, mock_app):
        """With the miner running, the CHP must first shut the miner down."""
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "off", "switch.miner": "on"}
        )
        state = make_state(grid_import=2500, miner_intended_switch_state="on")

        assert chp_handler.evaluate_and_act(state) is True
        # The CHP is NOT started this cycle...
        assert state.chp_intended_switch_state is None
        # ...but the miner shutdown is requested, overriding the miner's intent.
        assert state.miner_intended_switch_state == "off"
        assert state.miner_intended_power_limit == 0

    def test_interlock_respects_miner_min_wait(self, chp_handler, mock_app):
        """A recently toggled miner is left alone."""
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "off", "switch.miner": "on"},
            last_changed={"switch.miner": JUST_NOW},
        )
        state = make_state(grid_import=2500)

        assert chp_handler.evaluate_and_act(state) is False
        assert state.miner_intended_switch_state is None

    def test_turns_off_when_grid_import_low(self, chp_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "on", "switch.miner": "off"}
        )
        state = make_state(grid_import=200)

        assert chp_handler.evaluate_and_act(state) is True
        assert state.chp_intended_switch_state == "off"

    def test_no_toggle_within_min_wait_time(self, chp_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "on", "switch.miner": "off"},
            last_changed={"switch.chp": JUST_NOW},
        )
        state = make_state(grid_import=200)

        assert chp_handler.evaluate_and_act(state) is False
        assert state.chp_intended_switch_state is None

    def test_steady_state_no_action(self, chp_handler, mock_app):
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "on", "switch.miner": "off"}
        )
        state = make_state(grid_import=2500)

        assert chp_handler.evaluate_and_act(state) is False
        assert state.chp_intended_switch_state is None

    def test_naive_last_changed_treated_as_utc(self, chp_handler, mock_app):
        """HA reports last_changed in UTC; naive timestamps must not be
        interpreted as local time."""
        naive_long_ago = (
            (datetime.now(timezone.utc) - timedelta(hours=1))
            .replace(tzinfo=None)
            .isoformat()
        )
        mock_app.get_state.side_effect = entity_states(
            {"switch.chp": "off", "switch.miner": "off"},
            last_changed={"switch.chp": naive_long_ago},
        )
        state = make_state(grid_import=2500)

        assert chp_handler.evaluate_and_act(state) is True


class TestChpPlannedAction:
    def test_planned_action_executed(self, chp_handler, mock_app):
        mock_app.get_state.side_effect = entity_states({"switch.chp": "off"})
        plan = OptimizationPlan(plan={"chp_handler": ["on"] * 1440})
        state = make_state()

        chp_handler.execute_planned_action(state, plan, minute_of_day=100)

        assert state.chp_intended_switch_state == "on"

    def test_planned_action_noop_when_state_matches(self, chp_handler, mock_app):
        mock_app.get_state.side_effect = entity_states({"switch.chp": "on"})
        plan = OptimizationPlan(plan={"chp_handler": ["on"] * 1440})
        state = make_state()

        chp_handler.execute_planned_action(state, plan, minute_of_day=100)

        assert state.chp_intended_switch_state is None

    def test_no_plan_for_handler(self, chp_handler, mock_app):
        plan = OptimizationPlan()
        state = make_state()

        chp_handler.execute_planned_action(state, plan, minute_of_day=100)

        assert state.chp_intended_switch_state is None
