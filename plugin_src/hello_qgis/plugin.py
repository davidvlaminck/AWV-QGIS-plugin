# python
# File: `plugin_src/hello_qgis/plugin.py`
# Refactored for clarity: smaller helper methods, preserved behavior.

# -*- coding: utf-8 -*-
import datetime
import subprocess
from pathlib import Path
import json
from typing import Optional

from qgis.PyQt.QtCore import QObject, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QInputDialog
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFields, QgsField,
    QgsFeature, QgsGeometry, QgsWkbTypes, QgsCoordinateReferenceSystem,
    QgsCoordinateTransform, QgsFeatureRequest, QgsEditorWidgetSetup
)
from qgis.core import Qgis

from .venv_maintainer import maintain_venv_and_packages

VERSION = "1.1.1"


class HelloQGISPlugin(QObject):
    """
    Main plugin class.
    Behavior unchanged; methods split for readability.
    """
    def __init__(self, iface_):
        super().__init__()
        self.iface = iface_
        self.action_venv = None
        self.action_import_geojson = None
        self.action_export_selected_to_geojson = None

    # -------------------------
    # GUI wiring
    # -------------------------
    def initGui(self):
        self._create_actions()
        self.maintain_venv_and_packages()

    def _update_export_action_state(self, *args, **kwargs):
        # Enable the export action if one or more vector layers are selected
        selected_layers = self._get_selected_vector_layers()
        if hasattr(self, "action_export_selected_to_geojson") and self.action_export_selected_to_geojson:
            self.action_export_selected_to_geojson.setEnabled(bool(selected_layers))

    def _get_selected_vector_layers(self):
        # Returns a list of selected QgsVectorLayer objects
        selected_layers = []
        for node in self.iface.layerTreeView().selectedLayers():
            if isinstance(node, QgsVectorLayer):
                selected_layers.append(node)
        return selected_layers

    # python
    # python
    def export_selected_layers_to_geojson(self):
        """
        Diagnostic export: logs per-layer feature counts and how many features lack geometry,
        then performs the same merge/export logic so you can inspect results.
        """
        selected_layers = self._get_selected_vector_layers()
        if not selected_layers:
            self.iface.messageBar().pushWarning("Export", "No vector layers selected.")
            return

        # quick diagnostics: layer names and counts
        diag_lines = []
        for layer in selected_layers:
            try:
                total = 0
                no_geom = 0
                for feat in layer.getFeatures():
                    total += 1
                    try:
                        geom = feat.geometry()
                        if geom is None or geom.isEmpty():
                            no_geom += 1
                    except Exception:
                        no_geom += 1
                diag_lines.append(f"{layer.name()}: total={total}, no_geom={no_geom}")
            except Exception as e:
                diag_lines.append(f"{layer.name()}: error counting features: {e}")

        # show diagnostic summary in message bar (short) and print full to console / log
        summary = "; ".join(diag_lines[:3]) + (f"; ... ({len(diag_lines)} layers)" if len(diag_lines) > 3 else "")
        self.iface.messageBar().pushMessage("Export diag", summary, level=0, duration=5)
        # also print full diagnostics to stdout (check QGIS logs)
        for line in diag_lines:
            print("[hello_qgis] export diag:", line)

        output_path = self._prompt_export_path()
        if not output_path:
            return

        from qgis.core import QgsProject
        target_crs = QgsProject.instance().crs() if QgsProject.instance().crs().isValid() else None

        all_features = []
        crs = None

        for layer in selected_layers:
            layer_feats, layer_crs = self._geojson_features_from_layer(layer, target_crs)
            if layer_crs and not crs:
                crs = layer_crs
            all_features.extend(layer_feats)

        # after collecting, log how many features were gathered
        print("[hello_qgis] export diag: collected_features =", len(all_features))
        self.iface.messageBar().pushMessage("Export diag", f"collected features: {len(all_features)}", level=0,
                                            duration=4)

        if not all_features:
            self.iface.messageBar().pushWarning("Export", "No features to export.")
            return

        merged_geojson = {
            "type": "FeatureCollection",
            "name": Path(output_path).stem,
            "features": all_features
        }
        if crs:
            merged_geojson["crs"] = crs

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(merged_geojson, f, ensure_ascii=False, indent=2)

        # After writing, validate with otlmow_converter
        try:
            from otlmow_converter.OtlmowConverter import OtlmowConverter
            # Try to load the file using the converter (ignore the result)
            OtlmowConverter.from_file_to_objects(file_path=output_path)
            self.iface.messageBar().pushMessage("Export", f"Exported and validated: {output_path}", level=Qgis.Info, duration=5)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self.iface.mainWindow(), "Export validation failed", f"Validation failed:\n{tb}")
            print(tb)

    def _geojson_features_from_layer(self, layer, target_crs):
        """
        Return (features_list, crs_obj) for a layer.
        Each feature is a dict matching GeoJSON Feature structure.
        Geometries are reprojected to `target_crs` if provided; features without geometry get None.
        Property values are normalized to JSON-serializable types.
        """
        from qgis.core import QgsCoordinateTransform, QgsGeometry, QgsProject, QgsWkbTypes

        transform = None
        layer_crs_obj = None
        try:
            if layer.crs() and layer.crs().isValid():
                layer_crs_obj = {"type": "name", "properties": {"name": layer.crs().authid()}}
        except Exception:
            layer_crs_obj = None

        if target_crs and (not layer.crs() or layer.crs() != target_crs):
            try:
                transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
            except Exception:
                transform = None

        features = []
        field_names = [f.name() for f in layer.fields()]

        # Iterate all features; include those without geometry
        for feat in layer.getFeatures():
            props = {}
            for name in field_names:
                try:
                    raw_val = feat[name]
                except Exception:
                    try:
                        raw_val = feat.attribute(name)
                    except Exception:
                        raw_val = None
                props[name] = self._serialize_value(raw_val)

            geom = None
            try:
                geom_obj = feat.geometry()
            except Exception:
                geom_obj = None

            # For NoGeometry layers or features with empty geometry, keep geometry as None
            if geom_obj and not geom_obj.isEmpty():
                g = QgsGeometry(geom_obj)
                if transform:
                    try:
                        g.transform(transform)
                    except Exception:
                        pass
                try:
                    geom = json.loads(g.asJson())
                except Exception:
                    geom = None

            features.append({
                "type": "Feature",
                "properties": props,
                "geometry": geom
            })

        return features, layer_crs_obj

    def _serialize_value(self, val):
        """
        Convert Qt / QGIS / common Python types to JSON-serializable values.
        """
        from qgis.PyQt.QtCore import QDateTime, QDate, QTime, QVariant, Qt
        import datetime
        if val is None:
            return None

        # Unwrap QVariant where applicable
        try:
            if isinstance(val, QVariant):
                # toPyObject may not exist in PyQt6/PyQt5 builds; fallback to Python conversion
                try:
                    val = val.toPyObject()
                except Exception:
                    try:
                        val = val.value()
                    except Exception:
                        pass
        except Exception:
            pass

        # Qt date/time types
        try:
            if isinstance(val, QDateTime):
                return val.toString(Qt.ISODate)
            if isinstance(val, QDate):
                return val.toString(Qt.ISODate)
            if isinstance(val, QTime):
                return val.toString("HH:mm:ss")
        except Exception:
            pass

        # Native Python datetime
        if isinstance(val, (datetime.datetime, datetime.date)):
            return val.isoformat()

        # Bytes
        if isinstance(val, (bytes, bytearray)):
            try:
                return val.decode("utf-8")
            except Exception:
                return list(val)

        # Lists / tuples
        if isinstance(val, (list, tuple)):
            return [self._serialize_value(v) for v in val]

        # Dicts
        if isinstance(val, dict):
            return {k: self._serialize_value(v) for k, v in val.items()}

        # Numpy types (best-effort)
        try:
            import numpy as np
            if isinstance(val, (np.integer, np.floating)):
                return float(val)
            if isinstance(val, np.ndarray):
                return val.tolist()
        except Exception:
            pass

        # Basic JSON types
        if isinstance(val, (str, int, float, bool)):
            return val

        # Fallback to string
        try:
            return str(val)
        except Exception:
            return None

    def _prompt_export_path(self) -> Optional[Path]:
        path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Export Selected Layers to GeoJSON",
            "",
            "GeoJSON files (*.geojson *.json);;"
        )
        return Path(path) or None

    def _group_layers_by_geomtype(self, layers):
        geomtype_to_layers = {}
        for layer in layers:
            gtype = QgsWkbTypes.displayString(layer.wkbType())
            if not gtype or gtype == "Unknown":
                gtype = "NoGeometry"
            geomtype_to_layers.setdefault(gtype, []).append(layer)
        return geomtype_to_layers

    def _export_layer_to_file(self, layer, dest_path) -> bool:
        from qgis.core import QgsVectorFileWriter, QgsProject
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GeoJSON"
        options.fileEncoding = "UTF-8"
        options.precision = 3
        result, error_message = QgsVectorFileWriter.writeAsVectorFormatV2(
            layer,
            dest_path,
            QgsProject.instance().transformContext(),
            options
        )
        if result != QgsVectorFileWriter.NoError:
            self.iface.messageBar().pushWarning("Export", f"Failed to export: {error_message}")
            return False
        return True

    def _cleanup_temp_files(self, files: list):
        import os
        for f in files:
            try:
                os.remove(f)
            except Exception:
                pass

    def _merge_layers_to_memory(self, layers):
        """
        Merges all features from the given layers into a single memory layer.
        Supports layers with different geometry types and CRS.
        Features are reprojected to the project CRS if needed.
        """
        if not layers:
            return None

        # Use 'Unknown' geometry type for mixed geometry, and project CRS or first layer's CRS
        crs = QgsProject.instance().crs() if QgsProject.instance().crs().isValid() else layers[0].crs()
        uri = f"Unknown?crs={crs.authid()}"
        merged_layer = QgsVectorLayer(uri, "MergedExport", "memory")
        prov = merged_layer.dataProvider()

        # Use the union of all fields
        all_fields = QgsFields()
        field_names = set()
        for layer in layers:
            for field in layer.fields():
                if field.name() not in field_names:
                    all_fields.append(field)
                    field_names.add(field.name())
        prov.addAttributes(all_fields)
        merged_layer.updateFields()

        # Add all features, including those without geometry
        for layer in layers:
            # Reproject features if CRS does not match
            transform = None
            if layer.crs() != crs:
                transform = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
            for feat in layer.getFeatures():
                new_feat = QgsFeature(all_fields)
                attrs = []
                for field in all_fields:
                    idx = layer.fields().indexFromName(field.name())
                    attrs.append(feat[idx] if idx != -1 else None)
                new_feat.setAttributes(attrs)
                if feat.hasGeometry() and not feat.geometry().isEmpty():
                    geom = feat.geometry()
                    if transform:
                        geom = QgsGeometry(geom)
                        geom.transform(transform)
                    new_feat.setGeometry(geom)
                else:
                    new_feat.setGeometry(QgsGeometry())
                prov.addFeature(new_feat)
        merged_layer.updateExtents()
        return merged_layer

    def unload(self):
        self._cleanup_process()
        self._remove_actions()

    def _create_actions(self) -> None:
        """
        Creates and registers all plugin actions, including import and export.
        Uses custom icons for import (upload.svg) and export (download.svg) actions.
        """
        icon_dir = Path(__file__).parent / "icons"
        upload_icon = QIcon(str(icon_dir / "upload.svg"))
        download_icon = QIcon(str(icon_dir / "download.svg"))

        # self.action_venv = QAction(QIcon(), f"Hello QGIS ({VERSION})", self.iface.mainWindow())
        # self.action_venv.triggered.connect(self.maintain_venv_and_packages)
        # self.iface.addPluginToMenu("&Hello QGIS", self.action_venv)
        # self.iface.addToolBarIcon(self.action_venv)

        self.action_import_geojson = QAction(upload_icon, "Import GeoJSON (via plugin)", self.iface.mainWindow())
        self.action_import_geojson.triggered.connect(self.import_geojson)
        self.iface.addPluginToMenu("&GeoJSON Importer", self.action_import_geojson)
        self.iface.addToolBarIcon(self.action_import_geojson)

        # Export selected layers to GeoJSON action
        self.action_export_selected_to_geojson = QAction(download_icon, "Export Selected Layers to GeoJSON",
                                                         self.iface.mainWindow())
        self.action_export_selected_to_geojson.setEnabled(False)
        self.action_export_selected_to_geojson.triggered.connect(self.export_selected_layers_to_geojson)
        self.iface.addPluginToMenu("&GeoJSON Exporter", self.action_export_selected_to_geojson)
        self.iface.addToolBarIcon(self.action_export_selected_to_geojson)

        # Connect to layer selection changed to enable/disable the export action
        self.iface.layerTreeView().selectionModel().selectionChanged.connect(self._update_export_action_state)

    def _remove_actions(self) -> None:
        if self.action_venv:
            try:
                self.iface.removePluginMenu("&Hello QGIS", self.action_venv)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.action_venv)
            except Exception:
                pass
            self.action_venv = None

        if self.action_import_geojson:
            try:
                self.iface.removePluginMenu("&GeoJSON Importer", self.action_import_geojson)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.action_import_geojson)
            except Exception:
                pass
            self.action_import_geojson = None

        if hasattr(self, "action_export_selected_to_geojson") and self.action_export_selected_to_geojson:
            try:
                self.iface.removePluginMenu("&GeoJSON Exporter", self.action_export_selected_to_geojson)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.action_export_selected_to_geojson)
            except Exception:
                pass
            self.action_export_selected_to_geojson = None

    def _cleanup_process(self) -> None:
        if hasattr(self, "_venv_update_process"):
            try:
                self._venv_update_process.process.kill()
            except Exception:
                pass
            self._venv_update_process = None

    # -------------------------
    # Venv maintenance
    # -------------------------
    def maintain_venv_and_packages(self):
        plugin_dir = Path(__file__).parent
        packages_to_maintain = ["otlmow-model", "otlmow-converter"]
        self.iface.messageBar().pushMessage(
            "Dependency",
            "Venv update started; see Log Messages (HelloQGIS) for progress.",
            level=0, duration=5
        )
        maintain_venv_and_packages(
            plugin_dir=plugin_dir,
            packages=packages_to_maintain,
            venv_name="venv",
            on_done=self.on_venv_ready,
            plugin_instance=self
        )

    def on_venv_ready(self, success, venv_dir, output):
        """
        Callback after venv and packages are ready. Ensures otlmow_model and otlmow_converter are importable.
        """
        if not success:
            self.iface.messageBar().pushWarning("Dependency", "Venv update failed.")
            return

        import sys
        import importlib

        def venv_site_packages(venv_path: Path) -> Optional[str]:
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
                    rc = subprocess.run(
                        [str(venv_py), "-c", "import site; print('\\n'.join(site.getsitepackages()))"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
                    )
                    out = rc.stdout.decode("utf-8", errors="replace").strip().splitlines()
                    for p in out:
                        p_path = Path(p)
                        if p_path.is_dir():
                            return str(p_path)
                except Exception:
                    pass
            return None

        sp = venv_site_packages(Path(venv_dir))
        if sp and sp not in sys.path:
            sys.path.insert(0, sp)
            importlib.invalidate_caches()

        try:
            import otlmow_model  # noqa: F401
            import otlmow_converter  # noqa: F401
        except Exception as e:
            self.iface.messageBar().pushWarning("Dependency", f"Could not import required modules: {e}")
            return

    # -------------------------
    # GeoJSON import flow
    # -------------------------
    def import_geojson(self):
        path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(), "Open GeoJSON", "",
            "GeoJSON files (*.geojson *.json);;All files (*)"
        )
        if not path:
            # allow paste
            text, ok = QInputDialog.getMultiLineText(self.iface.mainWindow(), "Paste GeoJSON", "GeoJSON:")
            if not ok or not text.strip():
                return
            geojson_text = text
            layer_name = "Imported GeoJSON"
        else:
            with open(path, 'r', encoding='utf-8') as f:
                geojson_text = f.read()
            layer_name = Path(path).stem

        self.load_geojson_to_memory(geojson_text, layer_name)

    def load_geojson_to_memory(self, geojson_text: str, layer_name: str) -> None:
        """
        Loads a GeoJSON string as memory vector layers grouped by typeURI.
        Each unique typeURI value gets its own layer, with fields and geometry.
        """
        tmp_path = self._write_temp_geojson(geojson_text)
        features = self._parse_features_from_geojson(tmp_path)
        if not features:
            self.iface.messageBar().pushWarning("GeoJSON Import", "No features found")
            return

        grouped = self._group_features_by_typeuri(features)
        for type_uri, feats in grouped.items():
            self._create_layer_for_typeuri(type_uri, feats, layer_name)

    # -------------------------
    # File / parsing helpers
    # -------------------------
    def _write_temp_geojson(self, geojson_text: str) -> str:
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False, mode="w", encoding="utf-8") as tmpfile:
            tmpfile.write(geojson_text)
            return tmpfile.name

    def _parse_features_from_geojson(self, tmp_path: str) -> list[dict]:
        with open(tmp_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        return geojson_data.get("features", [])

    def _group_features_by_typeuri(self, features: list[dict]) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for feat in features:
            props = feat.get("properties", {})
            type_uri = props.get("typeURI", "UnknownType")
            grouped.setdefault(type_uri, []).append(feat)
        return grouped

    # -------------------------
    # Layer creation
    # -------------------------
    def _create_layer_for_typeuri(self, type_uri: str, feats: list[dict], layer_name: str) -> None:
        this_layer_name = f"{layer_name}_{type_uri.split('/')[-1] if '/' in type_uri else type_uri}"
        geom_type = self._get_geometry_type(feats)
        fields = self._build_fields_from_properties(feats)
        crs_authid = self._get_crs_from_geojson(feats)

        mem_layer = self._create_memory_layer(this_layer_name, geom_type, fields, crs_authid)
        self._add_features_to_layer(mem_layer, feats, geom_type)
        QgsProject.instance().addMapLayer(mem_layer)

    def _create_memory_layer(
            self,
            layer_name: str,
            geom_type: Optional[str],
            fields: QgsFields,
            crs_authid: str = "EPSG:31370"
    ) -> QgsVectorLayer:
        """
        Create a memory layer. For geometryless groups use 'None' as the geometry type
        so the provider is a no-geometry layer and will accept attribute-only features.
        """
        if not geom_type:
            uri = f"None?crs={crs_authid}"
        else:
            qgis_geom = {
                'Point': 'Point',
                'MultiPoint': 'MultiPoint',
                'LineString': 'LineString',
                'MultiLineString': 'MultiLineString',
                'Polygon': 'Polygon',
                'MultiPolygon': 'MultiPolygon'
            }.get(geom_type, 'Unknown')
            if qgis_geom != 'Unknown':
                qgis_geom += "Z"
            uri = f"{qgis_geom}?crs={crs_authid}"
        mem_layer = QgsVectorLayer(uri, layer_name, "memory")
        prov = mem_layer.dataProvider()
        prov.addAttributes(fields)
        mem_layer.updateFields()
        try:
            mem_layer.setCrs(QgsCoordinateReferenceSystem(crs_authid))
        except Exception:
            pass
        return mem_layer
    # -------------------------
    # Geometry and feature helpers
    # -------------------------
    def _get_geometry_type(self, feats: list[dict]) -> Optional[str]:
        for feat in feats[:10]:
            first_geom = feat.get('geometry')
            if first_geom and 'type' in first_geom:
                return first_geom['type']
        return None

    def _add_features_to_layer(self, mem_layer: QgsVectorLayer, feats: list[dict], geom_type: Optional[str]) -> None:
        """
        Adds features to the memory layer.
        If the target layer is geometryless (geom_type is None) do *not* set geometries,
        so attribute-only features are preserved.
        """
        from qgis.core import QgsFeature, QgsGeometry
        no_geom_count = 0

        for feat_json in feats:
            f = QgsFeature(mem_layer.fields())
            props = feat_json.get('properties', {}) or {}
            attrs = [props.get(field.name()) for field in mem_layer.fields()]
            f.setAttributes(attrs)

            # Only construct/set geometry when the memory layer expects geometry
            if geom_type:
                geom_data = feat_json.get('geometry')
                geom = QgsGeometry()
                if geom_data:
                    gtype = geom_data.get("type")
                    coords = geom_data.get("coordinates", [])
                    if gtype == "Point":
                        geom = self._geom_from_point(coords)
                    elif gtype == "Polygon":
                        geom = self._geom_from_polygon(geom_data, coords)
                    elif gtype == "LineString":
                        geom = self._geom_from_linestring(geom_data, coords)
                    else:
                        geom = self._geom_from_json(geom_data)
                # set geometry (may be empty if missing)
                f.setGeometry(geom)
            else:
                # No geometry
                no_geom_count += 1

            # For geometryless layers we keep the feature geometry unset/absent
            mem_layer.dataProvider().addFeature(f)
        mem_layer.updateExtents()
        print(f"[hello_qgis] import diag: {mem_layer.name()}: total={len(feats)}, no_geom={no_geom_count}")

    def _geom_from_point(self, coords: list) -> QgsGeometry:
        from qgis.core import QgsPoint, QgsGeometry
        geom = QgsGeometry()
        if coords:
            if len(coords) == 3:
                geom = QgsGeometry.fromPoint(QgsPoint(coords[0], coords[1], coords[2]))
            elif len(coords) == 2:
                geom = QgsGeometry.fromPoint(QgsPoint(coords[0], coords[1], 0))
        return geom

    def _geom_from_polygon(self, geom_data: dict, coords: list) -> QgsGeometry:
        from qgis.core import QgsPoint, QgsGeometry
        # Always 3D
        if coords and isinstance(coords[0][0], (float, int)):
            # Single ring, 2D
            ring = [QgsPoint(x, y, 0) for x, y in coords]
            rings = [ring]
        elif coords and isinstance(coords[0][0], list):
            # 3D or 2D rings
            rings = []
            for ring_coords in coords:
                if len(ring_coords) > 0 and len(ring_coords[0]) == 3:
                    ring = [QgsPoint(x, y, z) for x, y, z in ring_coords]
                else:
                    ring = [QgsPoint(x, y, 0) for x, y in ring_coords]
                rings.append(ring)
        else:
            rings = []

        if rings:
            def ring_to_wkt(ring):
                return ", ".join(f"{pt.x()} {pt.y()} {pt.z()}" for pt in ring)
            wkt_rings = ", ".join(f"({ring_to_wkt(ring)})" for ring in rings)
            wkt = f"POLYGON Z ({wkt_rings})"
            geom = QgsGeometry.fromWkt(wkt)
        else:
            geom_json = json.dumps(geom_data).encode('utf-8')
            try:
                geom = QgsGeometry.fromJson(geom_json)
            except Exception:
                geom = QgsGeometry()
        return geom

    def _geom_from_linestring(self, geom_data: dict, coords: list) -> QgsGeometry:
        from qgis.core import QgsPoint, QgsGeometry
        if coords and isinstance(coords[0], list):
            if len(coords[0]) == 3:
                line = [QgsPoint(x, y, z) for x, y, z in coords]
            elif len(coords[0]) == 2:
                line = [QgsPoint(x, y, 0) for x, y in coords]
            else:
                line = []
            if line:
                from qgis.core import QgsLineString  # noqa: F401
                geom = QgsGeometry.fromPolyline(line)
            else:
                geom = self._geom_from_json(geom_data)
        else:
            geom = self._geom_from_json(geom_data)
        return geom

    def _geom_from_json(self, geom_data: dict) -> QgsGeometry:
        from qgis.core import QgsGeometry
        geom_json = json.dumps(geom_data).encode('utf-8')
        try:
            geom = QgsGeometry.fromJson(geom_json)
        except Exception:
            geom = QgsGeometry()
        return geom

    # -------------------------
    # Field building helpers
    # -------------------------
    def _build_fields_from_properties(self, feats: list[dict]) -> QgsFields:
        """
        Uses otlmow_model and otlmow_converter to determine the type of each field using typeURI.
        """
        from otlmow_model.OtlmowModel.BaseClasses.OTLObject import dynamic_create_instance_from_uri
        from otlmow_converter.DotnotationHelper import DotnotationHelper

        props = {}
        type_uri = None
        for feat in feats:
            props = feat.get('properties', {})
            type_uri = props.get("typeURI")
            if props and type_uri:
                break

        fields = QgsFields()
        instance = None
        if type_uri:
            try:
                instance = dynamic_create_instance_from_uri(type_uri)
            except Exception:
                instance = None

        sorted_keys = sorted(props.keys())
        for k in sorted_keys:
            native_type = None
            attr = None
            field = None
            if instance:
                try:
                    attr = DotnotationHelper.get_attribute_by_dotnotation(instance, dotnotation=k)
                    field = getattr(attr, "field", None)
                    native_type = getattr(field, "native_type", None)
                except Exception:
                    native_type = None

            if k == 'typeURI':
                typeuri_field = QgsField(k, QVariant.String)
                typeuri_field.setReadOnly(True)
                fields.append(typeuri_field)
                continue

            if attr is not None and getattr(attr, "kardinaliteit_max", None) != '1':
                # Multi-valued fields are stored as strings
                fields.append(QgsField(k, QVariant.String))
                continue

            from otlmow_model.OtlmowModel.BaseClasses.KeuzelijstField import KeuzelijstField

            if field is not None and issubclass(field, KeuzelijstField):
                self._append_enum_field(fields, k, field)
                continue

            if native_type is not None:
                if native_type is bool:
                    fields.append(QgsField(k, QVariant.Bool))
                elif native_type is int:
                    fields.append(QgsField(k, QVariant.Int))
                elif native_type is float:
                    fields.append(QgsField(k, QVariant.Double))
                elif native_type is str:
                    fields.append(QgsField(k, QVariant.String))
                elif native_type is datetime.datetime:
                    fields.append(QgsField(k, QVariant.DateTime))
                elif native_type is datetime.date:
                    fields.append(QgsField(k, QVariant.Date))
                else:
                    self.iface.messageBar().pushWarning(
                        "GeoJSON Import",
                        f"Unrecognized type for field '{k}: {native_type}', using string."
                    )
                    fields.append(QgsField(k, QVariant.String))
            else:
                self.iface.messageBar().pushWarning(
                    "GeoJSON Import",
                    f"native type missing for field '{k}', using string."
                )
                fields.append(QgsField(k, QVariant.String))
        return fields

    def _append_enum_field(self, fields: QgsFields, key: str, field_class) -> None:
        """
        Create and append a QgsField configured as a ValueMap (enum) using
        allowed values from the KeuzelijstField. Behavior unchanged.
        """
        allowed_values = [k for k, v in field_class.options.items() if v.status != 'verwijderd']
        enum_field = QgsField(key, QVariant.String)
        enum_field.setEditorWidgetSetup(
            QgsEditorWidgetSetup("ValueMap", {'map': {v: v for v in allowed_values}})
        )
        fields.append(enum_field)

    # -------------------------
    # CRS helpers
    # -------------------------
    def _get_crs_from_geojson(self, feats: list[dict]) -> str:
        """
        Extracts the CRS authid from the GeoJSON data.
        Prefers a top-level 'crs' property, then checks the first feature's geometry, and finally defaults to EPSG:31370.
        """
        if hasattr(self, "last_geojson_text"):
            try:
                geojson_obj = json.loads(self.last_geojson_text)
                crs_top = geojson_obj.get("crs", {})
                if crs_top:
                    props = crs_top.get("properties", {})
                    name = props.get("name")
                    if name:
                        return name
            except Exception:
                pass

        for feat in feats:
            geom = feat.get("geometry", {})
            crs = geom.get("crs", {})
            props = crs.get("properties", {})
            name = props.get("name")
            if name:
                return name

        return "EPSG:31370"

    # kept for parity with original semantics: no reprojecting done here
    def _reproject_and_add_layer(self, mem_layer: QgsVectorLayer) -> None:
        QgsProject.instance().addMapLayer(mem_layer)