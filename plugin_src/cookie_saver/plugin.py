# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import QAction, QInputDialog, QLineEdit
from qgis.PyQt.QtGui import QIcon

class CookiePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        """Create the toolbar button and menu entry."""
        self.action = QAction(QIcon(), "Set Cookie", self.iface.mainWindow())
        self.action.triggered.connect(self.ask_for_cookie)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Cookie Plugin", self.action)

    def unload(self):
        """Remove the plugin menu item and icon."""
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&Cookie Plugin", self.action)

    def ask_for_cookie(self):
        """Prompt the user for a cookie string and save it to QSettings."""
        cookie, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "Enter Cookie",
            "Cookie:",
            QLineEdit.Normal
        )
        if ok and cookie:
            settings = QSettings()
            settings.setValue("SharedPlugins/CookieValue", cookie)
            self.iface.messageBar().pushInfo("Cookie Plugin", "Cookie saved.")

