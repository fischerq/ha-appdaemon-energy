import appdaemon.plugins.hass.hassapi as hass

class AttributionEngine:
    """
    Calculates the energy flow from producers to consumers based on priority.
    """

    def __init__(self, app: hass.Hass, production_priority: list, consumption_priority: list):
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
        self.app.log(f"AttributionEngine initialized with priorities: PROD={self.prod_priority}, CON={self.con_priority}")

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
        flow_matrix = {prod_key: {con_key: 0 for con_key in consumers} for prod_key in producers}

        # --- CORE LOGIC ---
        # Iterate through consumers IN ORDER of their priority
        for con_key in self.con_priority:
            if con_key not in consumers:
                continue # Skip if this consumer is not active

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
                flow_matrix[prod_key][con_key] = power_to_draw
                
                # Update remaining balances
                power_needed -= power_to_draw
                prod_available[prod_key] -= power_to_draw

                if power_needed == 0:
                    break # This consumer's demand is met, move to next consumer
        
        return flow_matrix