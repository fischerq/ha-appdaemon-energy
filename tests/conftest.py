"""Shared test setup.

Makes the AppDaemon app modules importable the same way AppDaemon does
(the apps directory goes directly onto sys.path) and provides a minimal
stub of the `appdaemon` package so the test suite does not depend on the
heavyweight AppDaemon runtime being installed.
"""

import sys
import types
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

try:
    import appdaemon.plugins.hass.hassapi  # noqa: F401
except ImportError:
    appdaemon_mod = types.ModuleType("appdaemon")
    plugins_mod = types.ModuleType("appdaemon.plugins")
    hass_mod = types.ModuleType("appdaemon.plugins.hass")
    hassapi_mod = types.ModuleType("appdaemon.plugins.hass.hassapi")

    class Hass:
        """Minimal stand-in for appdaemon's Hass base class."""

    hassapi_mod.Hass = Hass
    hass_mod.hassapi = hassapi_mod
    plugins_mod.hass = hass_mod
    appdaemon_mod.plugins = plugins_mod

    sys.modules["appdaemon"] = appdaemon_mod
    sys.modules["appdaemon.plugins"] = plugins_mod
    sys.modules["appdaemon.plugins.hass"] = hass_mod
    sys.modules["appdaemon.plugins.hass.hassapi"] = hassapi_mod
