import appdaemon.plugins.hass.hassapi as hass
import json
from datetime import datetime

class EnergyController(hass.Hass):

    def initialize(self):
        self.log("Hello from the Solalindenstein AppDaemon Energy Controller!")
        self.log("The energy controller.")

        # Read configuration from apps.yaml
        self.planner_sensor = self.args.get("planner_sensor")
        self.realtime_pv_sensor = self.args.get("realtime_pv_sensor")
        self.grid_power_sensor = self.args.get("grid_power_sensor")
        self.devices = self.args.get("devices", [])

        # Schedule the main loop to run every minute
        self.run_every(self.execute_plan_loop, "now", 60)

    def execute_plan_loop(self, kwargs):
        """
        The main loop that reads the dispatch plan, validates it, and controls the devices.
        """
        self.log("Executing plan loop")

        # Get the dispatch plan from the EMHASS sensor
        planner_state = self.get_state(self.planner_sensor, attribute="all")
        if not planner_state:
            self.log("Planner sensor not found or unavailable", level="ERROR")
            return

        dispatch_plan_str = planner_state["attributes"].get("optim_results_deferrable_loads")
        if not dispatch_plan_str:
            self.log("Dispatch plan not found in planner sensor attributes", level="ERROR")
            return

        try:
            dispatch_plan = json.loads(dispatch_plan_str)
        except json.JSONDecodeError:
            self.log("Malformed dispatch plan JSON", level="ERROR")
            return

        # Get the current time slot
        now = datetime.now()
        current_slot = now.hour * 2 # Assuming 30-minute intervals

        # Iterate through devices
        for device in self.devices:
            device_name = device.get("name")
            device_plan = dispatch_plan.get(device_name, {}).get("state")

            if not device_plan:
                self.log(f"No plan found for device: {device_name}")
                continue

            planned_state = device_plan[current_slot] if len(device_plan) > current_slot else 0

            if planned_state == 1:
                # Plan is to turn on the device, validate real-time conditions
                if self.validate_realtime_conditions(device):
                    self.control_device(device, "on")
                else:
                    self.log(f"Real-time conditions not met for {device_name}, keeping it off.")
                    self.control_device(device, "off") # Ensure it's off if conditions fail
            else:
                # Plan is to turn off the device
                self.control_device(device, "off")

    def validate_realtime_conditions(self, device):
        """
        To check if the real-time conditions in Home Assistant allow for the planned action to be executed.
        """
        # Get real-time sensor data
        pv_power_str = self.get_state(self.realtime_pv_sensor)
        grid_power_str = self.get_state(self.grid_power_sensor)

        if pv_power_str is None or grid_power_str is None:
            self.log("Unable to read real-time sensor data", level="WARNING")
            return False

        try:
            pv_power = float(pv_power_str)
            grid_power = float(grid_power_str)
        except ValueError:
            self.log("Invalid sensor data, not a number", level="WARNING")
            return False

        # Calculate surplus
        pv_surplus = pv_power - grid_power
        device_power = device.get("power", 0)

        # Validation logic: turn on only if there is enough PV surplus
        is_valid = pv_surplus >= device_power
        return is_valid

    def control_device(self, device, state):
        """
        To send the actual turn_on or turn_off command to the device's switch entity.
        """
        switch_entity = device.get("switch")
        current_state = "on" if self.get_state(switch_entity) == "on" else "off"

        if state == "on" and current_state == "off":
            self.log(f"Turning on {device.get('name')}")
            self.turn_on(switch_entity)
        elif state == "off" and current_state == "on":
            self.log(f"Turning off {device.get('name')}")
            self.turn_off(switch_entity)
