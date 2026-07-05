import pytest
from unittest.mock import Mock

from attribution_engine import AttributionEngine, split_power_flows
from system_state import SystemState


@pytest.fixture
def mock_app():
    return Mock()


@pytest.fixture
def engine(mock_app):
    return AttributionEngine(
        mock_app,
        production_priority=["pv", "chp", "battery", "grid"],
        consumption_priority=["house_load", "battery", "wallbox", "miner", "grid"],
    )


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


class TestCalculateFlows:
    def test_single_producer_single_consumer(self, engine):
        flows = engine.calculate_flows({"pv": 1000}, {"house_load": 600})

        assert flows == {"pv": {"house_load": 600}}

    def test_waterfall_across_producers(self, engine):
        """A consumer drains the highest-priority producer first."""
        flows = engine.calculate_flows({"pv": 500, "grid": 2000}, {"house_load": 1500})

        assert flows["pv"]["house_load"] == 500
        assert flows["grid"]["house_load"] == 1000

    def test_consumer_priority_order(self, engine):
        """Higher-priority consumers are satisfied before lower-priority ones."""
        flows = engine.calculate_flows(
            {"pv": 2000}, {"miner": 1500, "house_load": 1500}
        )

        assert flows["pv"]["house_load"] == 1500
        assert flows["pv"]["miner"] == 500

    def test_unmet_demand_logs_warning(self, engine, mock_app):
        engine.calculate_flows({"pv": 100}, {"house_load": 500})

        warnings = [
            c for c in mock_app.log.call_args_list if c.kwargs.get("level") == "WARNING"
        ]
        assert warnings, "expected a warning about unattributed demand"

    def test_unknown_keys_are_ignored_with_warning(self, engine, mock_app):
        flows = engine.calculate_flows(
            {"pv": 100, "diesel": 100}, {"house_load": 50, "sauna": 50}
        )

        assert flows["pv"]["house_load"] == 50
        assert flows["diesel"]["house_load"] == 0
        assert flows["pv"]["sauna"] == 0

    def test_zero_and_empty_inputs(self, engine):
        assert engine.calculate_flows({}, {}) == {}
        assert engine.calculate_flows({"pv": 0}, {"house_load": 0}) == {
            "pv": {"house_load": 0}
        }

    def test_float_amounts(self, engine):
        flows = engine.calculate_flows({"pv": 100.15}, {"house_load": 100.15})

        assert flows["pv"]["house_load"] == 100.15


class TestSplitPowerFlows:
    def test_typical_sunny_day(self):
        state = make_state(
            solar_production=5000,
            grid_power=-3000,
            grid_export=3000,
            battery_power=500,
            battery_charging=500,
            miner_consumption=0,
        )

        producers, consumers = split_power_flows(state)

        assert producers == {"pv": 5000}
        assert consumers == {"grid": 3000, "battery": 500, "house_load": 1500}

    def test_night_import_with_battery(self):
        state = make_state(
            grid_power=200,
            grid_import=200,
            battery_power=-400,
            battery_discharging=400,
        )

        producers, consumers = split_power_flows(state)

        assert producers == {"grid": 200, "battery": 400}
        assert consumers == {"house_load": 600}

    def test_wallbox_included(self):
        state = make_state(solar_production=6000)

        producers, consumers = split_power_flows(state, wallbox_power=4000)

        assert consumers["wallbox"] == 4000
        assert consumers["house_load"] == 2000

    def test_inconsistent_sensors_clamp_house_load_to_zero(self):
        state = make_state(solar_production=100, miner_consumption=500)

        _, consumers = split_power_flows(state)

        assert consumers["house_load"] == 0
