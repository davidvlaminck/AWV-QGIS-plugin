# -*- coding: utf-8 -*-
import importlib
import subprocess
import sys
import traceback
from pathlib import Path

from qgis.PyQt.QtCore import QObject, QTimer, QProcess
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QProgressBar
from qgis.core import QgsMessageLog, Qgis
from qgis.utils import iface

VERSION = "1.1.1"


# -------------------------
# Logging helper
# -------------------------
def _log(msg, level=Qgis.Info):
    """Log only warnings/errors to QGIS Log Messages and print to console."""
    try:
        QgsMessageLog.logMessage(msg, "HelloQGIS", level)
    except Exception:
        pass
    try:
        print(msg)
    except Exception:
        pass


# -------------------------
# venv helpers
# -------------------------
def venv_path_for_plugin(plugin_dir: str | Path, name: str = "venv") -> Path:
    return Path(plugin_dir) / name


def venv_python_executable(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    else:
        return venv_dir / "bin" / "python"


def venv_site_packages(venv_path: str | Path) -> str | None:
    venv_path = Path(venv_path)
    pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        venv_path / "lib" / pyver / "site-packages",
        venv_path / "Lib" / "site-packages",
        venv_path / "lib" / "site-packages",
    ]
    for p in candidates:
        if p.is_dir():
            return str(p)
    venv_py = venv_path / "bin" / "python"
    if venv_py.is_file():
        try:
            rc = subprocess.run([str(venv_py), "-c", "import site; print('\\n'.join(site.getsitepackages()))"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            out = rc.stdout.decode("utf-8", errors="replace").strip().splitlines()
            for p in out:
                p_path = Path(p)
                if p_path.is_dir():
                    return str(p_path)
        except Exception:
            _log("Exception while running venv python for site-packages:\n" + traceback.format_exc(), Qgis.Warning)
    _log("No site-packages found in venv", Qgis.Warning)
    return None


# -------------------------
# ensure venv and update (with uv fallback) - instrumented
# -------------------------
class VenvMaintainer(QObject):
    def __init__(self, plugin_dir, packages, venv_name="venv", on_done=None):
        super().__init__()
        self.plugin_dir = plugin_dir
        self.packages = packages
        self.venv_name = venv_name
        self.on_done = on_done
        self.venv_dir = venv_path_for_plugin(plugin_dir, venv_name)
        self.venv_py = venv_python_executable(self.venv_dir)
        self.step = 0
        self.output = ""
        self.message_bar_id = None
        self.commands = self.build_commands()

        # set up process
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.handle_finished)

        # set up progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(len(self.commands))
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Venv update: %p%")

        self.start()

    def start(self):
        self._show_progress("Venv update started...")
        self.run_next_command()

    def _show_progress(self, msg):
        self.progress_bar.setFormat(f"{msg} (%p%)")
        if iface and hasattr(iface, "messageBar"):
            if self.message_bar_id is not None:
                iface.messageBar().popWidget(self.message_bar_id)
            self.message_bar_id = iface.messageBar().pushWidget(self.progress_bar, Qgis.Info)

    def _update_progress(self, msg=None):
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        if msg:
            self.progress_bar.setFormat(f"{msg} (%p%)")

    def _finish_progress(self):
        if iface and hasattr(iface, "messageBar"):
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setFormat("Venv update completed!")
            QTimer.singleShot(2000, lambda: iface.messageBar().popWidget(self.message_bar_id))

    def _fail_progress(self, msg):
        if iface and hasattr(iface, "messageBar"):
            self.progress_bar.setFormat(f"Venv update failed: {msg}")
            QTimer.singleShot(5000, lambda: iface.messageBar().popWidget(self.message_bar_id))

    def build_commands(self):
        cmds = []
        if not Path(self.venv_dir).is_dir():
            cmds.append([sys.executable, "-m", "venv", str(self.venv_dir)])
        cmds.extend(
            (
                [str(self.venv_py), "-m", "pip", "install", "--upgrade", "pip"],
                [str(self.venv_py), "-m", "pip", "install", "uv"],
            )
        )
        cmds.extend([str(self.venv_py), "-m", "uv", "pip", "install", "--upgrade", pkg] for pkg in self.packages)
        return cmds

    def run_next_command(self):
        if self.step >= len(self.commands):
            self._finish_progress()
            if self.on_done:
                self.on_done(True, self.venv_dir, self.output)
            _log(f"Venv updated at:\n{self.venv_dir}\nPackages: {', '.join(self.packages)}", Qgis.Info)
            return
        cmd = self.commands[self.step]
        self.step += 1
        self._update_progress()
        self.output += f"\n\nRunning: {' '.join(cmd)}\n"
        self.process.start(cmd[0], cmd[1:])

    def handle_stdout(self):
        out = self.process.readAllStandardOutput().data().decode()
        self.output += out

    def handle_stderr(self):
        err = self.process.readAllStandardError().data().decode()
        self.output += err
        if err:
            _log(err, Qgis.Info)

    def handle_finished(self, exitCode, _):
        if exitCode != 0:
            self._fail_progress(f"Command failed with exit code {exitCode}")
            if self.on_done:
                self.on_done(False, self.venv_dir, self.output)
            QMessageBox.critical(None, "Venv update failed",
                                 f"Command failed with exit code {exitCode}.\nSee log for details.")
            return
        self.run_next_command()


def maintain_venv_and_packages(plugin_dir: Path, packages: list, venv_name: str = "venv", upgrade: bool = True,
                               on_done=None, timeout_per_cmd=900, plugin_instance=None):
    """
    Create or update a venv in <plugin_dir>/<venv_name> and install/upgrade specified packages.
    Uses QProcess-based async version.
    Keeps reference to process object.
    """
    process = VenvMaintainer(plugin_dir, packages, venv_name, on_done)
    if plugin_instance is not None:
        plugin_instance._venv_update_process = process
    return process

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
