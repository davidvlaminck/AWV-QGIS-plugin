#!/usr/bin/env python3
import os
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = ROOT / "plugins"
DIST_DIR = ROOT / "dist"
DIST_DIR.mkdir(exist_ok=True)

def read_version(metadata_path: Path) -> str:
    txt = metadata_path.read_text(encoding="utf-8")
    m = re.search(r"^version\s*=\s*([^\r\n]+)$", txt, re.MULTILINE)
    if not m:
        raise RuntimeError(f"version not found in {metadata_path}")
    return m.group(1).strip()

def zipdir(src_dir: Path, zip_path: Path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in src_dir.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(src_dir.parent)
            zf.write(p, rel.as_posix())

def main():
    for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
        if not plugin_dir.is_dir():
            continue
        metadata = plugin_dir / "metadata.txt"
        if not metadata.exists():
            continue
        version = read_version(metadata)
        # plugin folder name without version suffix (e.g., hello_qgis)
        base_name = plugin_dir.name.split("-")[0]
        zip_name = f"{base_name}-{version}.zip"
        zip_path = DIST_DIR / zip_name
        print(f"Packing {plugin_dir.name} -> {zip_name}")
        zipdir(plugin_dir, zip_path)

if __name__ == "__main__":
    main()