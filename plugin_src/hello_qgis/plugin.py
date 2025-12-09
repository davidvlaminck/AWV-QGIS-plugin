# -*- coding: utf-8 -*-
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsMessageLog, Qgis
from qgis.utils import iface

import tempfile

import os
import sys
import subprocess
import threading

import importlib
import traceback
from qgis.core import QgsMessageLog, Qgis
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.PyQt.QtCore import QTimer

VERSION = "1.1.1"

def _log(msg, level=Qgis.Info):
    QgsMessageLog.logMessage(msg, "HelloQGIS", level)
    print(msg)

def venv_path_for_plugin(plugin_dir: str, name: str = "venv") -> str:
    return os.path.join(plugin_dir, name)

def venv_site_packages(venv_path: str) -> str:
    """
    Robustly determine site-packages inside a venv for current Python version.
    """
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        os.path.join(venv_path, "lib", pyver, "site-packages"),
        os.path.join(venv_path, "Lib", "site-packages"),  # Windows style
        os.path.join(venv_path, "lib", "site-packages"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            _log(f"Found site-packages at: {p}")
            return p

    # fallback: try running the venv python to print site-packages
    venv_py = os.path.join(venv_path, "bin", "python")
    _log(f"Trying to get site-packages by running venv python at: {venv_py}")
    if os.path.isfile(venv_py):
        try:
            rc = subprocess.run([venv_py, "-c", "import site, sys; print('\\n'.join(site.getsitepackages()))"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            out = rc.stdout.decode("utf-8", errors="replace").strip().splitlines()
            if out:
                # return first existing
                for p in out:
                    if os.path.isdir(p):
                        return p
        except Exception:
            pass
    return None

def ensure_venv_and_update(plugin_dir: str, packages: list, venv_name: str = "venv", upgrade: bool = True):
    """
    Ensure a venv exists at plugin_dir/venv_name and install/upgrade packages.
    Runs in background thread because pip can block.
    """
    venv_dir = venv_path_for_plugin(plugin_dir, venv_name)
    _log(f'venv_dir: {venv_dir}')
    def _worker():
        tag = "HelloQGIS"
        venv_dir = venv_path_for_plugin(plugin_dir, venv_name)
        _log(f'venv_dir: {venv_dir}')
        try:
            _log(f"ensure_venv_and_update: venv_dir={venv_dir}")
            # create venv if missing
            if not os.path.isdir(venv_dir):
                _log("Creating venv...")
                rc = subprocess.run([sys.executable, "-m", "venv", venv_dir], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                if rc.returncode != 0:
                    raise RuntimeError("Failed to create venv:\n" + rc.stdout.decode("utf-8", errors="replace"))
            venv_py = os.path.join(venv_dir, "bin", "python")
            if not os.path.isfile(venv_py):
                raise RuntimeError("venv python not found at " + venv_py)

            # upgrade pip
            _log("Upgrading pip in venv...")
            subprocess.run([venv_py, "-m", "pip", "install", "uv"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            # install or upgrade packages
            for pkg in packages:
                cmd = [venv_py, "-m", "uv", "pip", "install", "--upgrade", pkg] if upgrade else [venv_py, "-m", "pip", "install", pkg]
                _log("Running: " + " ".join(cmd))
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                out = proc.stdout.decode("utf-8", errors="replace")
                _log(f"pip output for {pkg}:\n{out}")
                if proc.returncode != 0:
                    raise RuntimeError(f"pip install failed for {pkg}:\n{out}")

            # success: notify main thread
            def _ok():
                QMessageBox.information(None, "Venv ready", f"Venv updated at:\n{venv_dir}\nPackages: {', '.join(packages)}\nYou may need to restart QGIS for some packages.")
            QTimer.singleShot(0, _ok)

        except Exception as e:
            tb = traceback.format_exc()
            _log("Venv update failed:\n" + tb, level=Qgis.Critical)
            def _err():
                QMessageBox.critical(None, "Venv update failed", f"{e}\n\nZie Log Messages (HelloQGIS) voor details.")
            QTimer.singleShot(0, _err)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

def add_venv_to_syspath(plugin_dir: str, venv_name: str = "venv"):
    """
    Add the venv site-packages to sys.path at runtime so imports work.
    Call this early in plugin init (before imports of venv packages).
    """
    venv_dir = venv_path_for_plugin(plugin_dir, venv_name)
    _log(f'venv_dir: {venv_dir}')
    sp = venv_site_packages(venv_dir)
    if sp and sp not in sys.path:
        sys.path.insert(0, sp)
        importlib.invalidate_caches()
        _log(f"Inserted venv site-packages into sys.path: {sp}")
    else:
        _log(f"No venv site-packages found at {venv_dir} (site-packages={sp})", level=Qgis.Warning)



class HelloQGISPlugin(QObject):
    def __init__(self, iface_):
        super().__init__()
        self.iface = iface_
        self.action = None

    def initGui(self):
        self.action = QAction(QIcon(), f"Hello QGIS ({VERSION})", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
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

    def run(self):
        QMessageBox.information(self.iface.mainWindow(), "Hello QGIS",
                                f"Hello from version {VERSION}!")

        # same package listing behavior as before
        plugin_dir = os.path.dirname(__file__)
        ensure_venv_and_update(plugin_dir, ["otlmow-model"])

        add_venv_to_syspath(plugin_dir, venv_name="venv")
        try:
            import otlmow_model
            _log("otlmow_model imported, testing usage...", Qgis.Info)
            from otlmow_model.OtlMowModel.Classes.Onderdeel.Camera import Camera
            camera = Camera()
            camera.toestand = 'in-gebruik'
            _log("otlmow_model import succeeded", Qgis.Info)
        except Exception:
            QgsMessageLog.logMessage("otlmow_model import failed after adding venv:\n" + traceback.format_exc(),
                                     "HelloQGIS", Qgis.Warning)
