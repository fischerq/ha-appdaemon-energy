"""End-to-end tests: the full EnergyController control loop running against
a faked Home Assistant state machine.

These tests exercise the real code path used in production: sensor reading,
state computation, all device handlers, action execution and state
publishing - only the Home Assistant API surface is simulated.
"""

import copy
from datetime import datetime, timezone, timedelta

import pytest

from energy_controller import EnergyController

LONG_AGO = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
JUST_NOW = datetime.now(timezone.utc).isoformat()


class FakeHass(EnergyController):
    """EnergyController wired to an in-memory entity store instead of HA."""

    def __init__(self, args, entities):
        # Deliberately do NOT call Hass.__init__ - there is no AppDaemon runtime.
        self.args = args
        self.entities = copy.deepcopy(entities)
        self.turn_on_calls = []
        self.turn_off_calls = []
        self.service_calls = []
        self.scheduled = []
        self.logs = []
        self.errors = []

    # --- AppDaemon API surface ---
    def log(self, msg, level="INFO"):
        self.logs.append(msg)

    def error(self, msg, **kwargs):
        self.errors.append(msg)

    def get_state(self, entity_id=None, attribute=None, default=None, **kwargs):
        entity = self.entities.get(entity_id)
        if entity is None:
            return default
        if attribute == "all":
            return entity
        if attribute == "last_changed":
            return entity.get("last_changed")
        if attribute:
            return entity.get("attributes", {}).get(attribute, default)
        return entity.get("state")

    def set_state(self, entity_id, state=None, attributes=None, **kwargs):
        entity = self.entities.setdefault(entity_id, {"state": None, "attributes": {}})
        entity["state"] = state
        if attributes:
            entity.setdefault("attributes", {}).update(attributes)

    def turn_on(self, entity_id, **kwargs):
        self.turn_on_calls.append(entity_id)
        self.set_state(entity_id, state="on")
        self.entities[entity_id]["last_changed"] = datetime.now(
            timezone.utc
        ).isoformat()

    def turn_off(self, entity_id, **kwargs):
        self.turn_off_calls.append(entity_id)
        self.set_state(entity_id, state="off")
        self.entities[entity_id]["last_changed"] = datetime.now(
            timezone.utc
        ).isoformat()

    def call_service(self, service, **kwargs):
        self.service_calls.append((service, kwargs))
        if service == "number/set_value":
            self.set_state(kwargs["entity_id"], state=kwargs["value"])

    def run_every(self, callback, start, interval, **kwargs):
        self.scheduled.append((callback, start, interval))

    # --- test helpers ---
    def state_of(self, entity_id):
        return self.entities[entity_id]["state"]


def make_args(**overrides):
    args = {
        "dry_run_switch_entity": "input_boolean.dry_run",
        "sensors": {
            "grid_power": "sensor.grid_power",
            "battery_soc": "sensor.battery_soc",
            "battery_power": "sensor.battery_power",
            "solar_production": "sensor.solar_production",
            "miner_consumption": "sensor.miner_consumption",
            "chp_production": "sensor.chp_production",
        },
        "miner_heater": {
            "switch_entity": "switch.miner",
            "power_limit_entity": "number.miner_power_limit",
            "activation_threshold": 2000,
            "max_power": 6000,
            "power_step": 1000,
            "min_wait_time": 3,
        },
        "chp_handler": {
            "switch_entity": "switch.chp",
            "power_draw_threshold": 1000,
            "min_wait_time": 3,
        },
        "battery_handler": {
            "disable_charge_switch": "switch.battery_disable_charge",
            "min_soc_for_chp_charging": 50,
            "min_chp_production_for_logic": 100,
            "max_solar_for_chp_logic": 50,
        },
        "wallbox": {
            "power_sensor": "sensor.wallbox_power",
            "fast_charge_switch": "input_boolean.wallbox_fast_charge",
            "power_limit_entity": "number.wallbox_charge_power",
            "min_surplus_for_charging": 500,
            "max_power": 11000,
        },
        "publish_entities": {
            "solar_surplus": "sensor.controller_solar_surplus",
            "total_surplus": "sensor.controller_total_surplus",
            "house_consumption": "sensor.controller_house_consumption",
            "miner_surplus": "sensor.controller_miner_surplus",
            "miner_intended_switch_state": "sensor.controller_miner_intended_switch_state",
            "miner_intended_power_limit": "sensor.controller_miner_intended_power_limit",
            "controller_running": "binary_sensor.controller_running",
            "last_successful_run": "sensor.controller_last_successful_run",
        },
        "priority": {
            "production": ["pv", "chp", "battery", "grid"],
            "consumption": ["house_load", "battery", "wallbox", "miner", "grid"],
        },
        "publish_attribution_entity": "sensor.energy_flow_attribution",
    }
    args.update(overrides)
    return args


def make_entities(**overrides):
    entities = {
        "input_boolean.dry_run": {"state": "off"},
        "sensor.grid_power": {"state": "0.0"},
        "sensor.battery_soc": {"state": "50.0"},
        "sensor.battery_power": {"state": "0.0"},
        "sensor.solar_production": {"state": "0.0"},  # kW
        "sensor.miner_consumption": {"state": "0.0"},
        "sensor.chp_production": {"state": "0.0"},
        "sensor.wallbox_power": {"state": "0.0"},
        "switch.miner": {"state": "off", "last_changed": LONG_AGO},
        "switch.chp": {"state": "off", "last_changed": LONG_AGO},
        "switch.battery_disable_charge": {"state": "off", "last_changed": LONG_AGO},
        "input_boolean.wallbox_fast_charge": {"state": "off"},
        "number.miner_power_limit": {"state": "0.0", "attributes": {}},
        "number.wallbox_charge_power": {"state": "0.0", "attributes": {}},
    }
    for entity_id, values in overrides.items():
        entities.setdefault(entity_id, {}).update(values)
    return entities


def run_controller(args, entities):
    controller = FakeHass(args, entities)
    controller.initialize()
    controller.control_loop(None)
    return controller


class TestSunnySurplusDay:
    """5 kW solar, 3 kW export, battery charging 500 W: the miner starts,
    ramps to the surplus, and the wallbox begins charging."""

    @pytest.fixture
    def controller(self):
        entities = make_entities(
            **{
                "sensor.grid_power": {"state": "-3000.0"},
                "sensor.battery_power": {"state": "500.0"},
                "sensor.battery_soc": {"state": "80.0"},
                "sensor.solar_production": {"state": "5.0"},
                "sensor.miner_consumption": {"state": "unknown"},
            }
        )
        return run_controller(make_args(), entities)

    def test_miner_turned_on_with_power_limit(self, controller):
        # miner_surplus = solar(5000) - house(1500) = 3500 -> on, limit 3000
        assert "switch.miner" in controller.turn_on_calls
        assert controller.state_of("number.miner_power_limit") == 3000
        assert (
            "last_write"
            in controller.entities["number.miner_power_limit"]["attributes"]
        )

    def test_wallbox_charging_started(self, controller):
        # available = solar_surplus(3500) + wallbox draw(0)
        assert (
            "number/set_value",
            {"entity_id": "number.wallbox_charge_power", "value": 3500.0},
        ) in controller.service_calls

    def test_chp_stays_off(self, controller):
        assert controller.state_of("switch.chp") == "off"

    def test_state_published(self, controller):
        assert controller.state_of("sensor.controller_solar_surplus") == 3500.0
        assert controller.state_of("sensor.controller_house_consumption") == 1500.0
        assert controller.state_of("sensor.controller_miner_surplus") == 3500.0
        assert controller.state_of("binary_sensor.controller_running") == "on"

    def test_attribution_published(self, controller):
        entity = controller.entities["sensor.energy_flow_attribution"]
        assert entity["state"] == 5000.0
        flows = entity["attributes"]["flow_matrix"]
        assert flows["pv"]["house_load"] == 1500
        assert flows["pv"]["battery"] == 500
        assert flows["pv"]["grid"] == 3000


class TestDryRun:
    """With the dry-run switch on, intents are published but nothing is touched."""

    @pytest.fixture
    def controller(self):
        entities = make_entities(
            **{
                "input_boolean.dry_run": {"state": "on"},
                "sensor.grid_power": {"state": "-3000.0"},
                "sensor.battery_power": {"state": "500.0"},
                "sensor.solar_production": {"state": "5.0"},
            }
        )
        return run_controller(make_args(), entities)

    def test_no_actions_executed(self, controller):
        assert controller.turn_on_calls == []
        assert controller.turn_off_calls == []
        assert controller.service_calls == []
        assert controller.state_of("switch.miner") == "off"
        assert controller.state_of("number.miner_power_limit") == "0.0"

    def test_intents_published(self, controller):
        assert (
            controller.state_of("sensor.controller_miner_intended_switch_state") == "on"
        )
        assert (
            controller.state_of("sensor.controller_miner_intended_power_limit") == 3000
        )


class TestSensorFailure:
    def test_unavailable_sensor_skips_cycle(self):
        entities = make_entities(**{"sensor.grid_power": {"state": "unavailable"}})
        controller = run_controller(make_args(), entities)

        assert controller.state_of("binary_sensor.controller_running") == "off"
        assert controller.turn_on_calls == []
        assert controller.service_calls == []


class TestChpMinerInterlock:
    """High grid draw with the miner running: cycle 1 shuts the miner down,
    cycle 2 starts the CHP."""

    def test_two_cycle_handover(self):
        entities = make_entities(
            **{
                "sensor.grid_power": {"state": "4500.0"},
                "sensor.solar_production": {"state": "0.2"},
                "sensor.battery_soc": {"state": "40.0"},
                "sensor.miner_consumption": {"state": "2000.0"},
                "switch.miner": {"state": "on", "last_changed": LONG_AGO},
                "number.miner_power_limit": {"state": "2000.0", "attributes": {}},
            }
        )
        controller = FakeHass(make_args(), entities)
        controller.initialize()

        # Cycle 1: the miner must be shut down before the CHP may start.
        controller.control_loop(None)
        assert "switch.miner" in controller.turn_off_calls
        assert controller.state_of("switch.chp") == "off"

        # The miner is now off; grid draw drops by its consumption.
        controller.entities["sensor.grid_power"]["state"] = "2500.0"
        controller.entities["sensor.miner_consumption"]["state"] = "0.0"

        # Cycle 2: grid draw is still high and the miner is off -> CHP starts.
        controller.control_loop(None)
        assert "switch.chp" in controller.turn_on_calls
        assert controller.state_of("switch.chp") == "on"


class TestBatteryChpProtection:
    """CHP-only production with a full-enough battery: charging is disabled
    so the battery is not cycled from expensive CHP power."""

    def test_charging_disabled(self):
        entities = make_entities(
            **{
                "sensor.chp_production": {"state": "4000.0"},
                "sensor.grid_power": {"state": "-200.0"},
                "sensor.battery_power": {"state": "3800.0"},
                "sensor.battery_soc": {"state": "60.0"},
                "sensor.solar_production": {"state": "0.02"},
                "switch.chp": {"state": "on", "last_changed": JUST_NOW},
            }
        )
        controller = run_controller(make_args(), entities)

        assert "switch.battery_disable_charge" in controller.turn_on_calls
        assert controller.state_of("switch.battery_disable_charge") == "on"

    def test_charging_reenabled_when_solar_returns(self):
        entities = make_entities(
            **{
                "sensor.chp_production": {"state": "4000.0"},
                "sensor.grid_power": {"state": "-200.0"},
                "sensor.battery_power": {"state": "3800.0"},
                "sensor.battery_soc": {"state": "60.0"},
                "sensor.solar_production": {"state": "2.0"},
                "switch.chp": {"state": "on", "last_changed": JUST_NOW},
                "switch.battery_disable_charge": {
                    "state": "on",
                    "last_changed": LONG_AGO,
                },
            }
        )
        controller = run_controller(make_args(), entities)

        assert "switch.battery_disable_charge" in controller.turn_off_calls


class TestInitialization:
    def test_handlers_and_engine_initialized(self):
        controller = FakeHass(make_args(), make_entities())
        controller.initialize()

        handler_names = [type(h).__name__ for h in controller.device_handlers]
        assert handler_names == [
            "MinerHeaterHandler",
            "ChpHandler",
            "BatteryHandler",
            "WallboxHandler",
        ]
        assert controller.engine is not None
        assert len(controller.scheduled) == 1

    def test_without_optional_config(self):
        args = make_args()
        del args["priority"]
        del args["wallbox"]
        del args["chp_handler"]
        controller = FakeHass(args, make_entities())
        controller.initialize()

        assert controller.engine is None
        handler_names = [type(h).__name__ for h in controller.device_handlers]
        assert handler_names == ["MinerHeaterHandler", "BatteryHandler"]

        # The loop still runs end to end without the optional parts.
        controller.control_loop(None)
        assert controller.state_of("binary_sensor.controller_running") == "on"

    def test_failed_validation_does_not_abort(self):
        entities = make_entities(**{"sensor.grid_power": {"state": "unavailable"}})
        controller = FakeHass(make_args(), entities)
        controller.initialize()

        assert controller.scheduled, "the control loop must still be scheduled"
        assert controller.errors
