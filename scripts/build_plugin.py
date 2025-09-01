#!/usr/bin/env python3
import re
import shutil
import zipfile
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugin_src"
DIST_DIR = ROOT / "dist"
DIST_DIR.mkdir(exist_ok=True)

def read_metadata(metadata_path: Path) -> dict:
    """Read key=value pairs from metadata.txt into a dict."""
    meta = {}
    txt = metadata_path.read_text(encoding="utf-8")
    for line in txt.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta

def zip_plugin(plugin_dir: Path, plugin_name: str, version: str, zip_path: Path):
    """
    Create a ZIP containing a single top-level folder named `plugin_name`
    with all files from plugin_dir inside it.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_plugin_dir = Path(tmpdir) / plugin_name
        shutil.copytree(plugin_dir, tmp_plugin_dir)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in tmp_plugin_dir.rglob("*"):
                if p.is_file():
                    # Make paths inside ZIP relative to tmpdir so top-level is plugin_name/
                    rel = p.relative_to(Path(tmpdir))
                    zf.write(p, rel.as_posix())

def main():
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        metadata_path = plugin_dir / "metadata.txt"
        if not metadata_path.exists():
            continue

        meta = read_metadata(metadata_path)
        plugin_name = meta.get("name")
        version = meta.get("version")

        if not plugin_name or not version:
            print(f"Skipping {plugin_dir.name}: missing name or version in metadata.txt")
            continue

        zip_name = f"{plugin_name}-{version}.zip"
        zip_path = DIST_DIR / zip_name

        print(f"Packing {plugin_dir.name} as {plugin_name} -> {zip_name}")
        zip_plugin(plugin_dir, plugin_name, version, zip_path)

if __name__ == "__main__":
    main()
