from optimization_plan import OptimizationPlan


class TestOptimizationPlan:
    def test_dummy_plan_covers_full_day(self):
        plan = OptimizationPlan()
        plan.generate_dummy_plan(["miner_heater", "chp_handler"])

        assert set(plan.plan) == {"miner_heater", "chp_handler"}
        assert all(len(actions) == 24 * 60 for actions in plan.plan.values())
        assert plan.last_updated

    def test_dummy_plan_pattern(self):
        plan = OptimizationPlan()
        plan.generate_dummy_plan(["miner_heater"])

        actions = plan.plan["miner_heater"]
        assert actions[0] == "on"
        assert actions[9] == "on"
        assert actions[10] == "off"
        assert actions[59] == "off"
        assert actions[60] == "on"

    def test_get_action_for_handler(self):
        plan = OptimizationPlan(plan={"miner_heater": ["on", "off"]})

        assert plan.get_action_for_handler("miner_heater", 0) == "on"
        assert plan.get_action_for_handler("miner_heater", 1) == "off"

    def test_get_action_unknown_handler(self):
        plan = OptimizationPlan()

        assert plan.get_action_for_handler("miner_heater", 0) is None

    def test_get_action_out_of_range(self):
        plan = OptimizationPlan(plan={"miner_heater": ["on"] * 10})

        assert plan.get_action_for_handler("miner_heater", 10) is None
        assert plan.get_action_for_handler("miner_heater", -1) is None
