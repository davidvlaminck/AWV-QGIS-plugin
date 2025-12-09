# -*- coding: utf-8 -*-
from pathlib import Path

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .venv_maintainer import maintain_venv_and_packages

VERSION = "1.1.1"

# -------------------------
# Plugin class
# -------------------------
class HelloQGISPlugin(QObject):
    def __init__(self, iface_):
        super().__init__()
        self.iface = iface_
        self.action = None

    def initGui(self):
        self.action = QAction(QIcon(), f"Hello QGIS ({VERSION})", self.iface.mainWindow())
        self.action.triggered.connect(self.on_action_triggered)
        self.iface.addPluginToMenu("&Hello QGIS", self.action)
        self.iface.addToolBarIcon(self.action)

        self.on_action_triggered()

    def unload(self):
        if hasattr(self, "_venv_update_process"):
            try:
                self._venv_update_process.process.kill()
            except Exception:
                pass
            self._venv_update_process = None
        if self.action:
            try:
                self.iface.removePluginMenu("&Hello QGIS", self.action)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.action)
            except Exception:
                pass
            self.action = None

    def on_action_triggered(self):
        plugin_dir = Path(__file__).parent
        packages_to_maintain = ["otlmow-model", "otlmow-converter"]
        self.iface.messageBar().pushMessage("Dependency",
                                            "Venv update started; see Log Messages (HelloQGIS) for progress.",
                                            level=0, duration=5)
        maintain_venv_and_packages(plugin_dir=plugin_dir, packages=packages_to_maintain, venv_name="venv",
                                   on_done=None, plugin_instance=self)
