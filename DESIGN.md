# DESIGN.md: Modular AppDaemon Energy Controller

This document outlines the design of the modular, AppDaemon-based energy controller.

## 1. Core Architecture

*   **EnergyController** (`energy_controller.py`): The central AppDaemon class that acts as the orchestrator. Once per minute it gathers the system state, lets each device handler record its intended actions, publishes the state to Home Assistant, and executes the intents.

*   **SystemState** (`system_state.py`): A dataclass holding one consistent snapshot of the system per control cycle — raw sensor values plus derived values (surpluses, house consumption) plus the *intended actions* recorded by the handlers. It also owns the three lifecycle steps:
    *   `from_home_assistant()` — reads and validates all sensors, computes derived values. Returns `None` when any core sensor is unreadable, in which case the cycle is skipped and `binary_sensor.controller_running` is set to `off`.
    *   `publish_to_ha()` — publishes every state field and intent to configurable entities.
    *   `execute_actions()` — the ONLY place that touches devices. Compares each intent against the actual device state, executes only real changes, and honours the global dry-run switch.

*   **Device Handlers**: One class per device, each implementing `evaluate_and_act(state)` (urgent, reactive control) and `execute_planned_action(state, plan, minute_of_day)` (plan-based control, not yet wired into the controller):
    *   `MinerHeaterHandler` — turns the Bitcoin miner on when `miner_surplus` exceeds the activation threshold and steps its power limit in `power_step` increments, throttled by `min_write_interval_seconds` via a `last_write` attribute on the power-limit entity.
    *   `ChpHandler` — turns the CHP plant on when grid import exceeds `power_draw_threshold`. Interlock: if the miner is running, it first requests the miner off (overriding the miner's own intent for that cycle) and only starts the CHP in a later cycle once the miner is off. Toggles are rate-limited via the entity's `last_changed`.
    *   `BatteryHandler` — disables battery charging (via the inverted `disable_charge_switch`) when the SOC is already high and the only significant source is the CHP (no meaningful solar, exports below CHP production), so the battery is not cycled from expensive CHP power.
    *   `WallboxHandler` — sets the wallbox charge power to the available solar surplus (capped at `max_power`). The wallbox's own draw counts as available power to prevent the limit from oscillating; a small deadband suppresses noise-level rewrites. A manual fast-charge switch disables all automatic control.

    Handler order matters: the `ChpHandler` runs after the `MinerHeaterHandler` so its interlock can override the miner intent within the same cycle.

*   **AttributionEngine** (`attribution_engine.py`, optional): A pure observation feature. `split_power_flows()` splits a `SystemState` into producer/consumer dicts (with the unmeasured remainder as `house_load`); `calculate_flows()` attributes producer power to consumers using configured priority lists (waterfall logic) and the result matrix is published as attributes of a single sensor.

*   **OptimizationPlan** (`optimization_plan.py`): A container for a pre-computed 24h schedule per handler (minute resolution). Currently only a dummy-plan generator exists and the controller does not execute plans.

*   **Configuration-Driven**: Everything — entity IDs, thresholds, which handlers exist at all — is defined in `apps.yaml`. Handler sections and the attribution section are optional.

## 2. Control Cycle

```
run_every (60 s)
  └─ control_loop()
       ├─ SystemState.from_home_assistant()      # read + derive; None -> skip cycle
       ├─ handler.evaluate_and_act(state)        # each handler records intents
       ├─ state.publish_to_ha()                  # observability
       ├─ state.execute_actions()                # single point of device access + dry run
       └─ attribution (optional)                 # split_power_flows -> calculate_flows -> publish
```

## 3. Derived Values

With sign conventions *grid_power > 0 = import* and *battery_power > 0 = charging*:

*   `solar_surplus = battery_power - grid_power - chp_production`, clamped to at most `solar_production`. Net formula: battery discharge and grid import reduce the surplus.
*   `total_surplus = solar_surplus + chp_production`
*   `house_consumption = solar_production + chp_production + grid_power - battery_power - miner_consumption` — the signed `grid_power` keeps this correct while exporting.
*   `miner_surplus = solar_production - house_consumption` — solar power not needed by the house, i.e. power currently used for mining, battery charging or export.

## 4. Dry-Run Mode

`dry_run_switch_entity` points at an `input_boolean`. While it is `on`, `execute_actions()` logs `[DRY RUN]` messages instead of calling services, but all state and intents are still published, so behaviour can be observed safely in Home Assistant before arming the controller.

## 5. Testing

*   Unit tests per module under `tests/`, using plain `unittest.mock` objects for the AppDaemon API.
*   End-to-end tests (`tests/test_e2e_controller.py`) subclass the real `EnergyController` with a `FakeHass` in-memory entity store and drive full control cycles through realistic scenarios (sunny surplus day, dry run, sensor failure, CHP/miner interlock handover, battery CHP protection).
*   The AppDaemon runtime is not required: `tests/conftest.py` stubs `appdaemon.plugins.hass.hassapi` and puts `apps/` on `sys.path` exactly like AppDaemon does.
