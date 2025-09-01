#!/usr/bin/env python3
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

# Where your built plugin ZIPs live
DIST_DIR = Path(__file__).resolve().parent.parent / "dist"

# Base URL where these ZIPs will be hosted (GitHub Pages URL)
BASE_URL = "https://davidvlaminck.github.io/AWV-QGIS-plugin"

def read_metadata_from_zip(zip_path: Path) -> dict:
    """Extract metadata.txt from the plugin ZIP and parse it into a dict."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Find metadata.txt inside the top-level folder
        meta_file = next((n for n in zf.namelist() if n.endswith("metadata.txt")), None)
        if not meta_file:
            raise RuntimeError(f"No metadata.txt found in {zip_path}")
        with zf.open(meta_file) as f:
            lines = f.read().decode("utf-8").splitlines()
    meta = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta

def build_plugins_xml(plugins_info: list, xml_path: Path):
    """Generate plugins.xml for QGIS."""
    plugins_el = ET.Element("plugins")
    for info in plugins_info:
        plugin_el = ET.SubElement(
            plugins_el,
            "pyqgis_plugin",
            name=info["name"],
            version=info["version"],
            qgis_minimum_version=info.get("qgisMinimumVersion", "3.0"),
            qgis_maximum_version=info.get("qgisMaximumVersion", "3.99"),
        )
        ET.SubElement(plugin_el, "description").text = info.get("description", "")
        ET.SubElement(plugin_el, "about").text = info.get("about", "")
        ET.SubElement(plugin_el, "version").text = info["version"]
        ET.SubElement(plugin_el, "author").text = info.get("author", "")
        ET.SubElement(plugin_el, "email").text = info.get("email", "")
        ET.SubElement(plugin_el, "homepage").text = info.get("homepage", "")
        ET.SubElement(plugin_el, "download_url").text = f"{BASE_URL}/{info['zip_name']}"
        ET.SubElement(plugin_el, "experimental").text = info.get("experimental", "False")
        ET.SubElement(plugin_el, "deprecated").text = info.get("deprecated", "False")
        ET.SubElement(plugin_el, "tags").text = info.get("tags", "")
        ET.SubElement(plugin_el, "tracker").text = info.get("tracker", "")
        ET.SubElement(plugin_el, "repository").text = f"{BASE_URL}/plugins.xml"

    tree = ET.ElementTree(plugins_el)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)

def main():
    plugins_info = []
    for zip_path in sorted(DIST_DIR.glob("*.zip")):
        meta = read_metadata_from_zip(zip_path)
        meta["zip_name"] = zip_path.name
        plugins_info.append(meta)

    if not plugins_info:
        raise RuntimeError("No plugin ZIPs found in dist/")

    xml_path = DIST_DIR / "plugins.xml"
    build_plugins_xml(plugins_info, xml_path)
    print(f"Generated {xml_path} with {len(plugins_info)} plugin(s)")

if __name__ == "__main__":
    main()
