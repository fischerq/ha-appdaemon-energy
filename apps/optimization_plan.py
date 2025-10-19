
from dataclasses import dataclass, field
from typing import Dict, List, Any
from datetime import datetime

@dataclass
class OptimizationPlan:
    """A dataclass to hold the pre-computed optimization plan."""
    plan: Dict[str, List[Any]] = field(default_factory=dict)
    last_updated: str = ""

    def generate_dummy_plan(self, handlers: List[str]):
        """Generates a dummy 24h plan for all registered handlers."""
        self.plan = {}
        for handler in handlers:
            # Dummy plan: turn on for 10 minutes every hour
            self.plan[handler] = ["on" if i % 60 < 10 else "off" for i in range(24 * 60)]
        self.last_updated = datetime.now().isoformat()

    def get_action_for_handler(self, handler_name: str, minute_of_day: int) -> Any:
        """Gets the planned action for a specific handler at a given minute."""
        if handler_name in self.plan:
            return self.plan[handler_name][minute_of_day]
        return None
