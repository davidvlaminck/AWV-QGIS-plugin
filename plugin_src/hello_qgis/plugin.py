# -*- coding: utf-8 -*-
from pathlib import Path
import json

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


# -------------------------
# Plugin class
# -------------------------
class HelloQGISPlugin(QObject):
    def __init__(self, iface_):
        super().__init__()
        self.iface = iface_
        self.action_venv = None
        self.action_import_geojson = None

    def initGui(self):
        self.action_venv = QAction(QIcon(), f"Hello QGIS ({VERSION})", self.iface.mainWindow())
        self.action_venv.triggered.connect(self.maintain_venv_and_packages)
        self.iface.addPluginToMenu("&Hello QGIS", self.action_venv)
        self.iface.addToolBarIcon(self.action_venv)

        self.action_import_geojson = QAction(QIcon(), "Import GeoJSON (via plugin)", self.iface.mainWindow())
        self.action_import_geojson.triggered.connect(self.import_geojson)
        self.iface.addPluginToMenu("&GeoJSON Importer", self.action_import_geojson)
        self.iface.addToolBarIcon(self.action_import_geojson)

        #self.maintain_venv_and_packages()

    def unload(self):
        if hasattr(self, "_venv_update_process"):
            try:
                self._venv_update_process.process.kill()
            except Exception:
                pass
            self._venv_update_process = None
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

    def maintain_venv_and_packages(self):
        plugin_dir = Path(__file__).parent
        packages_to_maintain = ["otlmow-model", "otlmow-converter"]
        self.iface.messageBar().pushMessage("Dependency",
                                            "Venv update started; see Log Messages (HelloQGIS) for progress.",
                                            level=0, duration=5)
        maintain_venv_and_packages(plugin_dir=plugin_dir, packages=packages_to_maintain, venv_name="venv",
                                   on_done=None, plugin_instance=self)

    def import_geojson(self):
        path, _ = QFileDialog.getOpenFileName(self.iface.mainWindow(), "Open GeoJSON", "",
                                              "GeoJSON files (*.geojson *.json);;All files (*)")
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
            # Use the file name (without extension) as the layer name
            layer_name = Path(path).stem

        self.load_geojson_to_memory(geojson_text, layer_name)

    def load_geojson_to_memory(self, geojson_text, layer_name):
        """
        Loads a GeoJSON string as a memory vector layer with fields and geometry.

        This uses QGIS's native GeoJSON support for robust field and geometry handling.
        """
        # Write the GeoJSON to a temporary file (QgsVectorLayer can also load from a string with "ogr" provider, but file is more robust)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False, mode="w", encoding="utf-8") as tmpfile:
            tmpfile.write(geojson_text)
            tmp_path = tmpfile.name

        # Load the GeoJSON as a vector layer
        layer = QgsVectorLayer(tmp_path, layer_name, "ogr")
        if not layer.isValid():
            self.iface.messageBar().pushWarning("GeoJSON Import", "Failed to load GeoJSON as vector layer")
            return

        # Change the type of the 'isActief' field to boolean and 'toestand' to enum, preserving field order
        layer.startEditing()
        idx_actief = layer.fields().indexFromName("isActief")
        idx_toestand = layer.fields().indexFromName("toestand")
        valid_toestand_options = ["in-gebruik", "in-ontwerp", "uit-gebruik"]
        if idx_actief != -1 or idx_toestand != -1:
            old_fields = layer.fields()
            new_fields = []
            for i in range(len(old_fields)):
                field = old_fields[i]
                if field.name() == "isActief":
                    new_fields.append(QgsField("isActief", QVariant.Bool))
                elif field.name() == "toestand":
                    enum_field = QgsField("toestand", QVariant.String)
                    enum_field.setEditorWidgetSetup(
                        QgsEditorWidgetSetup("ValueMap", {'map': {v: v for v in valid_toestand_options}})
                    )
                    new_fields.append(enum_field)
                else:
                    new_fields.append(field)
            geometry_type_str = QgsWkbTypes.displayString(layer.wkbType())
            new_layer = QgsVectorLayer(f"{geometry_type_str}?crs={layer.crs().authid()}", layer.name(), "memory")
            new_layer.dataProvider().addAttributes(new_fields)
            new_layer.updateFields()
            for feat in layer.getFeatures():
                new_feat = QgsFeature(new_layer.fields())
                attrs = list(feat.attributes())
                if idx_actief != -1 and idx_actief < len(attrs):
                    attrs[idx_actief] = bool(attrs[idx_actief]) if attrs[idx_actief] is not None else None
                if idx_toestand != -1 and idx_toestand < len(attrs):
                    val = attrs[idx_toestand]
                    attrs[idx_toestand] = val if val in valid_toestand_options else None
                new_feat.setAttributes(attrs)
                new_feat.setGeometry(feat.geometry())
                new_layer.dataProvider().addFeature(new_feat)
            new_layer.updateExtents()
            QgsProject.instance().addMapLayer(new_layer)
            layer.rollBack()
            return
        layer.commitChanges()

        # Optionally reproject to project CRS
        project_crs = QgsProject.instance().crs()
        if project_crs.isValid() and layer.crs() != project_crs:
            layer.setCrs(project_crs)

        QgsProject.instance().addMapLayer(layer)
