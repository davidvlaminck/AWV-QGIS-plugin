#!/usr/bin/env python3
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"
DIST_DIR = ROOT / "dist"
DIST_DIR.mkdir(exist_ok=True)

EXCLUDE_DIRS = {
    ".git", ".svn", "__pycache__", ".mypy_cache", ".idea", ".vscode",
    "node_modules", "dist", "build", ".pytest_cache"
}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}

def read_metadata(metadata_path: Path) -> dict:
    meta = {}
    txt = metadata_path.read_text(encoding="utf-8")
    for line in txt.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta

def zip_plugin_flat(plugin_dir: Path, zip_path: Path):
    """Zip plugin_dir contents at ZIP root (no top-level folder)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in plugin_dir.rglob("*"):
            if p.is_dir():
                continue
            if p.name in EXCLUDE_FILES:
                continue
            # Skip any file that lives under an excluded directory
            if any(part in EXCLUDE_DIRS for part in p.parts):
                continue
            rel = p.relative_to(plugin_dir)
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

        print(f"Packing {plugin_dir.name} -> {zip_name} (flat)")
        zip_plugin_flat(plugin_dir, zip_path)

if __name__ == "__main__":
    main()
