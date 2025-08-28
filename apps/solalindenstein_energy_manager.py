import appdaemon.plugins.hass.hassapi as hass

# Define a class for your app, inheriting from Hass.
class SolalindensteinEnergyManager(hass.Hass):

    # The initialize() method is the entry point for the app.
    def initialize(self):
        """
        This method is called when the app is initialized.
        """
        # Use self.log() to print messages to the AppDaemon log.
        self.log("Hello from your Solalindenstein AppDaemon app!")
        self.log("If you see this, your git-based workflow is correctly configured.")