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
from qgis.PyQt.QtCore import QObject, QTimer

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
        # single connection to a single handler
        self.action = QAction(QIcon(), f"Hello QGIS ({VERSION})", self.iface.mainWindow())
        self.action.triggered.connect(self.on_action_triggered)
        self.iface.addPluginToMenu("&Hello QGIS", self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
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
        """
        Called when the toolbar/menu action is clicked.
        Ensure dependency first, then run the plugin action.
        """
        # If package already available, proceed immediately
        if _is_package_available("otlmow_model"):
            self.run()
            return

        # Ask user for consent on the main thread
        reply = QMessageBox.question(
            self.iface.mainWindow(),
            "Install dependency",
            "The plugin requires the Python package 'otlmow_model'.\n"
            "Do you want to install it now into the QGIS Python environment?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            self.iface.messageBar().pushMessage("Dependency", "Installation cancelled by user.", level=1, duration=5)
            return

        # Start background install; UI updates scheduled back on main thread
        def _install_thread():
            success, output = _run_pip_install("otlmow-model")
            # schedule UI handling on main thread
            def _after_install():
                if success and _is_package_available("otlmow_model"):
                    self.iface.messageBar().pushMessage("Dependency", "Installed 'otlmow_model' successfully.", level=0, duration=5)
                    QMessageBox.information(self.iface.mainWindow(), "Installation complete",
                                            "'otlmow_model' was installed successfully.\nYou may need to restart QGIS or reload the plugin.")
                    # now run the plugin action
                    self.run()
                elif success and not _is_package_available("otlmow_model"):
                    self.iface.messageBar().pushMessage("Dependency", "Installed but import failed.", level=2, duration=8)
                    QMessageBox.warning(self.iface.mainWindow(), "Install completed but import failed",
                                        "pip reported success but the module could not be imported.\n\nOutput:\n" + output[:1000])
                else:
                    self.iface.messageBar().pushMessage("Dependency", "Failed to install 'otlmow_model'.", level=2, duration=8)
                    QMessageBox.critical(self.iface.mainWindow(), "Installation failed",
                                         "Could not install 'otlmow-model'.\n\nOutput:\n" + output[:2000])

            QTimer.singleShot(0, _after_install)

        t = threading.Thread(target=_install_thread, daemon=True)
        t.start()

    from qgis.core import QgsMessageLog, Qgis
    import tempfile
    import os
    from qgis.PyQt.QtWidgets import QMessageBox

    def run(self):
        # collect installed packages
        try:
            import subprocess
            proc = subprocess.run([sys.executable, "-m", "pip", "list", "--format=freeze"],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            full_text = proc.stdout.decode("utf-8", errors="replace")
            pkgs = full_text.splitlines()
        except Exception as e:
            pkgs = [f"Error enumerating packages: {e}"]

        # prepare short and full outputs
        full_text = "\n".join(pkgs)
        short_text = full_text
        # truncate for message box if too long
        max_chars = 1000
        if len(short_text) > max_chars:
            short_text = short_text[:max_chars].rsplit("\n", 1)[0] + "\n…(truncated)"

        # show in message bar and message box
        self.iface.messageBar().pushMessage("Hello QGIS", f"Hello from version {VERSION}!", level=0, duration=5)
        QMessageBox.information(self.iface.mainWindow(), f"Hello QGIS ({VERSION})",
                                "Installed packages:\n\n" + short_text)

        # log full list to QGIS log and print to console
        self.QgsMessageLog.logMessage(f"Installed packages for plugin {VERSION}:\n{full_text}", "HelloQGIS", self.Qgis.Info)
        print(f"Installed packages for plugin {VERSION}:\n{full_text}")

        # if very long, also write to a temp file and tell the user where it is
        if len(full_text) > 5000:
            try:
                fd, path = tempfile.mkstemp(prefix="hello_qgis_pkgs_", suffix=".txt")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(full_text)
                self.QgsMessageLog.logMessage(f"Full package list written to: {path}", "HelloQGIS", self.Qgis.Info)
                QMessageBox.information(self.iface.mainWindow(), "Package list saved",
                                        f"The full package list is long and was written to:\n{path}")
            except Exception as e:
                self.QgsMessageLog.logMessage(f"Failed to write package list to temp file: {e}", "HelloQGIS", self.Qgis.Warning)
