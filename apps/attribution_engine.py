import appdaemon.plugins.hass.hassapi as hass


def split_power_flows(state, wallbox_power=0.0):
    """
    Splits a SystemState snapshot into producer and consumer power dicts
    for the AttributionEngine. The unmeasured remainder is attributed to
    'house_load'.

    Args:
        state: A SystemState instance.
        wallbox_power: The current wallbox draw in W (not part of SystemState).

    Returns:
        A (producers, consumers) tuple of dicts in Watts.
    """
    producers = {}
    consumers = {}

    if state.solar_production > 0:
        producers["pv"] = state.solar_production
    if state.chp_production > 0:
        producers["chp"] = state.chp_production
    if state.grid_import > 0:
        producers["grid"] = state.grid_import
    if state.battery_discharging > 0:
        producers["battery"] = state.battery_discharging

    if state.grid_export > 0:
        consumers["grid"] = state.grid_export
    if state.battery_charging > 0:
        consumers["battery"] = state.battery_charging
    if state.miner_consumption > 0:
        consumers["miner"] = state.miner_consumption
    if wallbox_power > 0:
        consumers["wallbox"] = wallbox_power

    residual_load = sum(producers.values()) - sum(consumers.values())
    consumers["house_load"] = round(max(residual_load, 0.0), 2)

    return producers, consumers


class AttributionEngine:
    """
    Calculates the energy flow from producers to consumers based on priority.
    """

    def __init__(
        self, app: hass.Hass, production_priority: list, consumption_priority: list
    ):
        """
        Initializes the engine with static priority lists.

        Args:
            app: The AppDaemon app instance for logging.
            production_priority: Ordered list of producer keys (e.g., ['pv', 'battery', 'grid']).
            consumption_priority: Ordered list of consumer keys (e.g., ['house_load', 'battery', 'miner']).
        """
        self.app = app
        self.prod_priority = production_priority
        self.con_priority = consumption_priority
        self.app.log(
            f"AttributionEngine initialized with priorities: PROD={self.prod_priority}, CON={self.con_priority}"
        )

    def calculate_flows(self, producers: dict, consumers: dict) -> dict:
        """
        Performs the priority-based attribution (waterfall logic).

        Args:
            producers: A dict of available power: {'pv': 5000, 'grid': 1000}
            consumers: A dict of requested power: {'house_load': 1500, 'miner': 2000}

        Returns:
            A nested dict (the "attribution matrix"):
            {
                'pv': {'house_load': 1500, 'miner': 500},
                'grid': {'miner': 1500}
            }
        """
        # Create mutable copies to track remaining power
        prod_available = producers.copy()

        # Initialize the result matrix with all-zero flows
        flow_matrix = {
            prod_key: {con_key: 0 for con_key in consumers} for prod_key in producers
        }

        unknown_consumers = set(consumers) - set(self.con_priority)
        if unknown_consumers:
            self.app.log(
                f"Consumers not in the priority list are ignored: {sorted(unknown_consumers)}",
                level="WARNING",
            )
        unknown_producers = set(producers) - set(self.prod_priority)
        if unknown_producers:
            self.app.log(
                f"Producers not in the priority list are ignored: {sorted(unknown_producers)}",
                level="WARNING",
            )

        # --- CORE LOGIC ---
        # Iterate through consumers IN ORDER of their priority
        for con_key in self.con_priority:
            if con_key not in consumers:
                continue  # Skip if this consumer is not active

            power_needed = consumers.get(con_key, 0)
            if power_needed <= 0:
                continue

            # Iterate through producers IN ORDER of their priority to meet this need
            for prod_key in self.prod_priority:
                if prod_key not in prod_available:
                    continue

                power_available = prod_available.get(prod_key, 0)
                if power_available <= 0:
                    continue

                # Determine power to draw from this producer
                power_to_draw = min(power_needed, power_available)

                # Assign the flow
                flow_matrix[prod_key][con_key] = round(power_to_draw, 2)

                # Update remaining balances
                power_needed -= power_to_draw
                prod_available[prod_key] -= power_to_draw

                # Use a small tolerance so float residue does not keep the
                # loop scanning producers for effectively-zero demand.
                if power_needed <= 1e-9:
                    break  # This consumer's demand is met, move to next consumer

            if power_needed > 1e-9:
                self.app.log(
                    f"Consumer '{con_key}' has {power_needed:.1f}W of unattributed demand.",
                    level="WARNING",
                )

        return flow_matrix
