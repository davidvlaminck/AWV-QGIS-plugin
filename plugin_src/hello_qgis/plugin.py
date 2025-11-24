# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QObject
from qgis.utils import iface

import sys
import importlib
import subprocess
import threading
import traceback

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QObject

import os

VERSION = "1.1.1"


def _is_package_available(package_import_name: str) -> bool:
    """Return True if package can be imported in the current interpreter."""
    try:
        return importlib.util.find_spec(package_import_name) is not None
    except Exception:
        return False


def _run_pip_install(package_spec: str) -> (bool, str):
    """
    Run pip install using the same Python interpreter (sys.executable).
    Returns (success, output_or_error).
    """
    try:
        # Use -q for quieter output; remove if you want verbose logs
        cmd = [sys.executable, "-m", "pip", "install", package_spec]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        out = proc.stdout.decode("utf-8", errors="replace")
        success = proc.returncode == 0
        return success, out
    except Exception as e:
        return False, f"Exception while running pip: {e}\n{traceback.format_exc()}"


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
        self.ensure_package_installed(package_import_name="otlmow_model", package_spec="otlmow-model")

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Hello QGIS", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        QMessageBox.information(self.iface.mainWindow(), "Hello QGIS",
                                f"Hello from version {VERSION}!")

    def ensure_package_installed(self, package_import_name: str = "otlmow_model", package_spec: str = "otlmow-model"):
        """
        Ensure the package is importable. If not, attempt to install it using pip in a background thread.
        - package_import_name: the module name used for import (e.g., 'otlmow_model')
        - package_spec: the pip spec (e.g., 'otlmow-model' or 'otlmow-model==1.2.3')
        """

        # Quick check first
        if _is_package_available(package_import_name):
            self.iface.messageBar().pushMessage("Dependency", f"'{package_import_name}' already installed.", level=0,
                                                duration=3)
            return True

        # Ask user for consent (recommended)
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            "Install dependency",
            f"The plugin requires the Python package '{package_import_name}'.\n"
            "Do you want to install it now into the QGIS Python environment?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            self.iface.messageBar().pushMessage("Dependency", "Installation cancelled by user.", level=1, duration=5)
            return False

        # Run installation in background thread
        def _install_thread():
            try:
                self.iface.messageBar().pushMessage("Dependency", f"Installing {package_spec}...", level=0, duration=5)
                success, output = _run_pip_install(package_spec)
                if success:
                    # verify import now
                    if _is_package_available(package_import_name):
                        self.iface.messageBar().pushMessage("Dependency",
                                                            f"Installed '{package_import_name}' successfully.", level=0,
                                                            duration=5)
                        # Optionally show a dialog to tell user to restart QGIS or reload plugin
                        QMessageBox.information(self.iface.mainWindow(), "Installation complete",
                                                f"'{package_import_name}' was installed successfully.\n"
                                                "You may need to restart QGIS or reload the plugin for changes to take effect.")
                    else:
                        # pip reported success but import still fails
                        self.iface.messageBar().pushMessage("Dependency",
                                                            f"Installed but import failed: {package_import_name}",
                                                            level=2, duration=8)
                        QMessageBox.warning(self.iface.mainWindow(), "Install completed but import failed",
                                            f"pip reported success but the module '{package_import_name}' could not be imported.\n\nOutput:\n{output[:1000]}")
                else:
                    # installation failed
                    self.iface.messageBar().pushMessage("Dependency", f"Failed to install '{package_import_name}'.",
                                                        level=2, duration=8)
                    QMessageBox.critical(self.iface.mainWindow(), "Installation failed",
                                         f"Could not install '{package_spec}'.\n\nOutput:\n{output[:2000]}")
            except Exception as e:
                self.iface.messageBar().pushMessage("Dependency", "Unexpected error during install.", level=2,
                                                    duration=8)
                QMessageBox.critical(self.iface.mainWindow(), "Installation error",
                                     f"Unexpected error: {e}\n{traceback.format_exc()}")

        t = threading.Thread(target=_install_thread, daemon=True)
        t.start()
        return None  # installation is running asynchronously

