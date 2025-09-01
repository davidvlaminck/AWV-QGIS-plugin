#!/usr/bin/env python3
import re
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Usage: python scripts/make_repo.py https://localhost:8000/
# base_url must end with a slash; the script will put zips in repo/ and write plugins.xml

ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
REPO_DIR = ROOT / "repo"

def parse_zip(zip_name: str):
    # Expect format: <pluginName>-<version>.zip, e.g., hello_qgis-1.1.0.zip
    m = re.match(r"^(.+)-(\d+\.\d+\.\d+)\.zip$", zip_name)
    if not m:
        return None, None
    return m.group(1), m.group(2)

def version_key(v: str):
    return tuple(int(x) for x in v.split("."))

def main():
    if len(sys.argv) != 2:
        print("Usage: make_repo.py <base_url_with_trailing_slash>")
        sys.exit(1)
    base_url = sys.argv[1]
    if not base_url.endswith("/"):
        base_url += "/"

    REPO_DIR.mkdir(exist_ok=True)

    zips = [p for p in DIST_DIR.glob("*.zip")]
    latest = {}
    for z in zips:
        name, ver = parse_zip(z.name)
        if not name:
            continue
        if name not in latest or version_key(ver) > version_key(latest[name][1]):
            latest[name] = (z, ver)

    # Copy latest zips into repo/ for hosting
    for name, (zip_path, ver) in latest.items():
        target = REPO_DIR / zip_path.name
        if target.resolve() != zip_path.resolve():
            target.write_bytes(zip_path.read_bytes())

    # Write plugins.xml
    items = []
    for name, (zip_path, ver) in sorted(latest.items()):
        download_url = base_url + zip_path.name
        # Minimal metadata: adjust as needed
        item = f"""  <pyqgis_plugin name="{escape(name)}" version="{escape(ver)}" qgis_minimum_version="3.22" qgis_maximum_version="3.99">
    <description>Minimal plugin served from a custom repository</description>
    <about>This plugin demonstrates custom QGIS plugin repos and updates.</about>
    <version>{escape(ver)}</version>
    <author>Your Name</author>
    <email>you@example.com</email>
    <homepage>https://example.invalid/{escape(name)}</homepage>
    <download_url>{escape(download_url)}</download_url>
    <experimental>False</experimental>
    <deprecated>False</deprecated>
    <tags>demo,custom-repo</tags>
    <tracker>https://example.invalid/{escape(name)}/issues</tracker>
    <repository>{escape(base_url)}plugins.xml</repository>
  </pyqgis_plugin>"""
        items.append(item)

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<plugins>
{items}
</plugins>
""".format(items="\n".join(items))

    (REPO_DIR / "plugins.xml").write_text(xml, encoding="utf-8")
    print(f"Wrote {REPO_DIR / 'plugins.xml'}")
    print("Zips available:")
    for z in sorted(REPO_DIR.glob("*.zip")):
        print(" -", z.name)

if __name__ == "__main__":
    main()
