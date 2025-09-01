# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QObject
from qgis.utils import iface
import os

VERSION = "1.1.1"

class HelloQGISPlugin(QObject):
    def __init__(self, iface_):
        super().__init__()
        self.iface = iface_
        self.action = None

    def initGui(self):
        # Simple action that shows a message
        self.action = QAction(QIcon(), f"Hello QGIS ({VERSION})", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&Hello QGIS", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Hello QGIS", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        QMessageBox.information(self.iface.mainWindow(), "Hello QGIS",
                                f"Hello from version {VERSION}!")
