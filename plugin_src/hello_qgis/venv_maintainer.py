import subprocess
import sys
import traceback
import urllib
from pathlib import Path
from qgis.PyQt.QtCore import QObject, QTimer, QProcess, QProcessEnvironment
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox, QProgressBar
from qgis.core import QgsMessageLog, Qgis
from qgis.utils import iface


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
            # Laat de voortgangsbalk langer staan zodat de gebruiker het ziet
            QTimer.singleShot(10000, lambda: iface.messageBar().popWidget(self.message_bar_id))
        _log(f"Venv update failed: {msg}", Qgis.Critical)

    def ensure_pip_in_venv(self, venv_py: Path):
        """
        Ensures pip is installed in the given venv by running get-pip.py if needed.
        """
        import urllib.request
        _log(f"ensure_pip_in_venv called", Qgis.Info)
        pip_path = venv_py.parent / "pip.exe" if sys.platform == "win32" else venv_py.parent / "pip"
        if pip_path.is_file():
            return  # pip already present

        # Download get-pip.py
        get_pip_url = "https://bootstrap.pypa.io/get-pip.py"
        get_pip_path = venv_py.parent / "get-pip.py"
        try:
            urllib.request.urlretrieve(get_pip_url, str(get_pip_path))
        except Exception as e:
            _log(f"Failed to download get-pip.py: {e}", Qgis.Critical)
            return

        # Run get-pip.py
        try:
            subprocess.check_call([str(venv_py), str(get_pip_path)])
        except Exception as e:
            # Check if pip is now present despite the error
            if pip_path.is_file():
                _log(f"get-pip.py returned error but pip is now present: {e}", Qgis.Warning)
            else:
                _log(f"Failed to run get-pip.py and pip is still missing: {e}", Qgis.Critical)
                QMessageBox.critical(None, "Venv update failed",
                                     f"get-pip.py failed and pip is still missing.\n\nDetails:\n{e}")
        finally:
            try:
                get_pip_path.unlink()
            except Exception:
                pass

    def _get_python_executable(self) -> str:
        """
        Returns the path to the Python executable to use for venv creation.
        On Windows, expects the user to have a recent Python (3.12+) installed outside of QGIS (user install).
        On other platforms, returns sys.executable.
        """
        _log("_get_python_executable", Qgis.Info)
        import sys
        import shutil
        from pathlib import Path

        if sys.platform == "win32":
            # Zoek naar een echte Python in PATH (geen QGIS, geen embeddable)
            python_exe = shutil.which("python.exe")
            if python_exe and "QGIS" not in python_exe and "python_embed" not in python_exe:
                return python_exe
            # Fallback: bekende locaties
            candidates = [
                Path.home() / "AppData/Local/Programs/Python/Python312/python.exe",
                Path("C:/Python312/python.exe"),
                Path("C:/Program Files/Python312/python.exe"),
            ]
            for candidate in candidates:
                if candidate.is_file():
                    return str(candidate)
            raise RuntimeError(
                "No suitable Python installation found. Please install Python 3.12 from https://python.org (user install, no admin needed)."
            )
        else:
            return sys.executable

    def build_commands(self):
        """
        On Windows, use a user-installed Python (not QGIS, not embeddable) to create a venv and install all packages with pip/uv.
        On Linux/macOS, use a venv as before.
        """
        cmds = []
        python_exe = self._get_python_executable()
        if not Path(self.venv_dir).is_dir():
            cmds.append([python_exe, "-m", "venv", str(self.venv_dir)])
        venv_py = venv_python_executable(self.venv_dir)
        cmds.append([str(venv_py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
        cmds.append([str(venv_py), "-m", "pip", "install", "uv"])
        cmds.extend([str(venv_py), "-m", "uv", "pip", "install", "--upgrade", pkg] for pkg in self.packages)
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
        just_ran = self.commands[self.step - 1] if self.step > 0 else []
        is_venv_creation = (
                len(just_ran) >= 3 and
                just_ran[1:3] == ["-m", "venv"]
        )
        if is_venv_creation:
            pip_path = self.venv_dir / ("Scripts" if sys.platform == "win32" else "bin") / (
                "pip.exe" if sys.platform == "win32" else "pip")
            if not pip_path.is_file():
                self.ensure_pip_in_venv(self.venv_py)
        if exitCode != 0:
            # Toon de laatste 20 regels van de output in de messagebar
            last_lines = "\n".join(self.output.strip().splitlines()[-20:])
            self._fail_progress(f"Command failed with exit code {exitCode}. Laatste output:\n{last_lines}")
            if self.on_done:
                self.on_done(False, self.venv_dir, self.output)
            QMessageBox.critical(None, "Venv update failed",
                                 f"Command failed with exit code {exitCode}.\nZie log voor details.\n\nLaatste output:\n{last_lines}")
            return
        self.run_next_command()


# -------------------------
# ensure venv and update (with uv fallback) - instrumented
# -------------------------
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
