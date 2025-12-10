#!/usr/bin/env python3
import shutil
import tempfile
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).parent.parent
PLUGINS_DIR = ROOT / "plugin_src"
DIST_DIR = ROOT / "dist"
BASE_URL = "https://davidvlaminck.github.io/AWV-QGIS-plugin"
DIST_DIR.mkdir(exist_ok=True)

# Clear out any existing files in dist/
for item in DIST_DIR.iterdir():
    if item.is_file() or item.is_symlink():
        item.unlink()
    elif item.is_dir():
        shutil.rmtree(item)


def read_metadata(metadata_path: Path) -> dict:
    """Read key=value pairs from metadata.txt into a dict."""
    meta = {}
    txt = metadata_path.read_text(encoding="utf-8")
    for line in txt.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta

def zip_plugin(plugin_dir: Path, plugin_name: str, zip_path: Path):
    """
    Create a ZIP containing a single top-level folder named `plugin_name`
    with all files from plugin_dir inside it.
    """
    if zip_path.exists():
        zip_path.unlink()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_plugin_dir = Path(tmpdir) / plugin_name
        shutil.copytree(plugin_dir, tmp_plugin_dir)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in tmp_plugin_dir.rglob("*"):
                if p.is_file():
                    rel = p.relative_to(Path(tmpdir))
                    zf.write(p, rel.as_posix())

def zip_plugins():
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
        zip_plugin(plugin_dir, plugin_name, zip_path)


def read_metadata_from_zip(zip_path: Path) -> dict:
    """Extract metadata.txt from the plugin ZIP and parse it into a dict."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        # Expect metadata.txt in the top-level folder
        meta_file = next((n for n in zf.namelist() if n.count("/") == 1 and n.endswith("metadata.txt")), None)
        if not meta_file:
            raise RuntimeError(f"No top-level metadata.txt found in {zip_path}")
        with zf.open(meta_file) as f:
            lines = f.read().decode("utf-8").splitlines()
    meta = {}
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            meta[k.strip()] = v.strip()
    return meta

def build_plugins_xml(plugins_info: list, xml_path: Path):
    """Generate plugins.xml for QGIS with proper version tags."""
    plugins_el = ET.Element("plugins")
    for info in plugins_info:
        plugin_el = ET.SubElement(
            plugins_el,
            "pyqgis_plugin",
            name=info["name"],
            version=info["version"]
        )
        # QGIS expects these as child elements, not attributes
        ET.SubElement(plugin_el, "qgis_minimum_version").text = info.get("qgisMinimumVersion", "3.0")
        ET.SubElement(plugin_el, "qgis_maximum_version").text = info.get("qgisMaximumVersion", "3.99")

        ET.SubElement(plugin_el, "description").text = info.get("description", "")
        ET.SubElement(plugin_el, "about").text = info.get("about", "")
        ET.SubElement(plugin_el, "version").text = info["version"]
        ET.SubElement(plugin_el, "author").text = info.get("author", "")
        ET.SubElement(plugin_el, "email").text = info.get("email", "")
        ET.SubElement(plugin_el, "homepage").text = info.get("homepage", "")
        ET.SubElement(plugin_el, "download_url").text = f"{BASE_URL}/dist/{info['zip_name']}"
        ET.SubElement(plugin_el, "experimental").text = info.get("experimental", "False")
        ET.SubElement(plugin_el, "deprecated").text = info.get("deprecated", "False")
        ET.SubElement(plugin_el, "tags").text = info.get("tags", "")
        ET.SubElement(plugin_el, "tracker").text = info.get("tracker", "")
        ET.SubElement(plugin_el, "repository").text = f"{BASE_URL}/plugins.xml"

    tree = ET.ElementTree(plugins_el)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)

def create_xml():
    plugins_info = []
    for zip_path in sorted(DIST_DIR.glob("*.zip")):
        meta = read_metadata_from_zip(zip_path)
        meta["zip_name"] = zip_path.name
        plugins_info.append(meta)

    if not plugins_info:
        raise RuntimeError("No plugin ZIPs found in dist/")

    xml_path = ROOT / "plugins.xml"
    build_plugins_xml(plugins_info, xml_path)
    print(f"Generated {xml_path} with {len(plugins_info)} plugin(s)")

if __name__ == "__main__":
    zip_plugins()
    create_xml()

