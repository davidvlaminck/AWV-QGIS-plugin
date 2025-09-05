# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from qgis.PyQt.QtCore import QSettings, QTimer
from qgis.PyQt.QtWidgets import QAction, QInputDialog, QLineEdit
from qgis.PyQt.QtGui import QIcon
import os

class CookiePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        plugin_dir = os.path.dirname(__file__)
        self.icon_full = os.path.join(plugin_dir, "cookie_full.svg")
        self.icon_empty = os.path.join(plugin_dir, "cookie_empty.svg")

    def initGui(self):
        """Create the toolbar button and menu entry."""
        self.action = QAction(QIcon(self.icon_empty), "Set Cookie", self.iface.mainWindow())
        self.action.triggered.connect(self.ask_for_cookie)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Cookie Plugin", self.action)

        # Start a timer to check every 60 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_cookie_status)
        self.timer.start(60 * 1000)  # milliseconds

        # Check cookie status at startup
        self.check_cookie_status()

    def unload(self):
        """Remove the plugin menu item and icon."""
        self.iface.removeToolBarIcon(self.action)
        self.iface.removePluginMenu("&Cookie Plugin", self.action)


    def ask_for_cookie(self):
        """Prompt the user for a cookie string and save it to QSettings with expiry."""
        cookie, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "Enter Cookie",
            "Cookie:",
            QLineEdit.Normal
        )
        if ok and cookie:
            expiry_time = datetime.now() + timedelta(hours=12)
            settings = QSettings()
            settings.setValue("SharedPlugins/CookieValue", cookie)
            settings.setValue("SharedPlugins/CookieExpiry", expiry_time.isoformat())
            self.iface.messageBar().pushInfo(
                "Cookie Plugin",
                f"Cookie saved. Expires at {expiry_time.strftime('%Y-%m-%d %H:%M')}"
            )
            self.update_icon(True)

    def check_cookie_status(self):
        """Check if a valid cookie exists and update icon/tooltip."""
        settings = QSettings()
        cookie = settings.value("SharedPlugins/CookieValue", "")
        expiry_str = settings.value("SharedPlugins/CookieExpiry", "")

        if cookie and expiry_str:
            try:
                expiry_time = datetime.fromisoformat(expiry_str)
                if datetime.now() < expiry_time:
                    # Cookie is still valid
                    self.update_icon(True)
                    return
            except Exception:
                pass

        # If we reach here, cookie is missing or expired
        self.clear_cookie()

    def clear_cookie(self):
        """Clear cookie and expiry from settings."""
        settings = QSettings()
        settings.remove("SharedPlugins/CookieValue")
        settings.remove("SharedPlugins/CookieExpiry")
        self.update_icon(False)

    def update_icon(self, has_cookie):
        """Change tooltip and icon based on cookie status."""
        if has_cookie:
            self.action.setToolTip("Cookie is set and valid")
            self.action.setIcon(QIcon(self.icon_full))
        else:
            self.action.setToolTip("No valid cookie set")
            self.action.setIcon(QIcon(self.icon_empty))