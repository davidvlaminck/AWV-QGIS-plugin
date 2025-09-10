from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsWkbTypes, QgsFeatureRequest, QgsMessageLog, Qgis,
    QgsPointXY, QgsCoordinateTransform, QgsProject
)
from qgis.gui import QgsMapTool, QgsRubberBand
from pathlib import Path
from qgis.PyQt.QtGui import QIcon


class CustomSplitTool(QgsMapTool):
    def __init__(self, iface, layer, fid, original_asset_id, before_ids):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.layer = layer
        self.fid = fid
        self.original_asset_id = original_asset_id
        self.before_ids = set(before_ids)

        # Geometry storage
        self.parts_points_layer = []     # list of parts in layer CRS
        self.current_points_layer = []
        self.current_points_map = []

        # Visuals
        self.live_band = self._make_band()
        self.part_bands = []

        # CRS transform
        self.tx_map_to_layer = QgsCoordinateTransform(
            self.canvas.mapSettings().destinationCrs(),
            self.layer.crs(),
            QgsProject.instance()
        )

        self.setCursor(Qt.CrossCursor)
        self.canvas.setFocus()

    # ---------- Rubber band helpers ----------
    def _make_band(self):
        band = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        band.setColor(QColor(255, 0, 0))
        band.setWidth(2)
        return band

    def _clear_bands(self):
        self.live_band.reset(QgsWkbTypes.LineGeometry)
        for b in self.part_bands:
            b.reset(QgsWkbTypes.LineGeometry)
            self.canvas.scene().removeItem(b)
        self.part_bands.clear()

    # ---------- Capture events ----------
    def canvasMoveEvent(self, event):
        if not self.current_points_map:
            self.live_band.reset(QgsWkbTypes.LineGeometry)
            return
        self.live_band.reset(QgsWkbTypes.LineGeometry)
        for pt in self.current_points_map:
            self.live_band.addPoint(pt)
        self.live_band.addPoint(QgsPointXY(event.mapPoint()))

    def canvasReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Snap to map
            snap_match = self.canvas.snappingUtils().snapToMap(event.mapPoint())
            if snap_match.isValid():
                map_pt = snap_match.point()
            else:
                map_pt = QgsPointXY(event.mapPoint())

            # Transform to layer CRS
            layer_pt = self.tx_map_to_layer.transform(map_pt)

            self.current_points_layer.append(layer_pt)
            self.current_points_map.append(map_pt)
            return

        if event.button() == Qt.RightButton:
            if self.current_points_layer:
                if len(self.current_points_layer) >= 2:
                    self.parts_points_layer.append(self.current_points_layer[:])
                    band = self._make_band()
                    for pt in self.current_points_map:
                        band.addPoint(pt)
                    self.part_bands.append(band)
                self.current_points_layer.clear()
                self.current_points_map.clear()
                self.live_band.reset(QgsWkbTypes.LineGeometry)
            else:
                self.finish_capture()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Backspace and self.current_points_layer:
            self.current_points_layer.pop()
            self.current_points_map.pop()
            self.canvasMoveEvent(event)
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            if self.current_points_layer:
                self.current_points_layer.clear()
                self.current_points_map.clear()
                self.live_band.reset(QgsWkbTypes.LineGeometry)
            else:
                self._clear_bands()
                self.canvas.unsetMapTool(self)
            event.accept()
            return
        super().keyPressEvent(event)

    def deactivate(self):
        self._clear_bands()
        super().deactivate()

    # ---------- Split logic ----------
    def finish_capture(self):
        if not self.parts_points_layer:
            self.canvas.unsetMapTool(self)
            return
        self.run_split(self.parts_points_layer)
        self.parts_points_layer.clear()
        self._clear_bands()
        self.canvas.unsetMapTool(self)

    def run_split(self, parts_points_layer):
        self.layer.beginEditCommand("Custom Split with assetId handling")

        for idx, pts in enumerate(parts_points_layer, start=1):
            if len(pts) < 2:
                continue
            result = self.layer.splitFeatures(pts, True)

            if result == Qgis.GeometryOperationResult.NothingHappened:
                self.iface.messageBar().pushInfo(
                    "Custom Split",
                    f"Part {idx} did not intersect the selected feature — no changes made."
                )
                continue
            elif result != Qgis.GeometryOperationResult.Success:
                self.iface.messageBar().pushCritical(
                    "Custom Split",
                    f"Split failed for part {idx} (code {result})."
                )
                self.layer.destroyEditCommand()
                return

        pieces = self._get_split_pieces()
        if not pieces:
            self.layer.destroyEditCommand()
            return

        largest_id = max(
            pieces,
            key=lambda f: f.geometry().area() if self.layer.geometryType() == QgsWkbTypes.PolygonGeometry else f.geometry().length()
        ).id()

        attr_idx = self.layer.fields().indexFromName('assetId.identificator')
        if attr_idx < 0:
            self.layer.destroyEditCommand()
            return

        for f in pieces:
            self.layer.changeAttributeValue(
                f.id(),
                attr_idx,
                self.original_asset_id if f.id() == largest_id else None
            )

        self.layer.endEditCommand()
        self.layer.triggerRepaint()
        QgsMessageLog.logMessage(
            f"Custom Split complete: kept assetId for feature {largest_id}, cleared for {len(pieces)-1} others",
            "AssetsSplit", Qgis.Info
        )

    def _get_split_pieces(self):
        after_ids = {f.id() for f in self.layer.getFeatures()}
        created_ids = list(after_ids - self.before_ids)
        target_ids = set(created_ids)
        target_ids.add(self.fid)
        req = QgsFeatureRequest().setFilterFids(list(target_ids))
        return list(self.layer.getFeatures(req))


class AssetsSplitPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.split_action = None
        self.split_tool = None

    def initGui(self):
        icon_path = Path(__file__).parent / "mActionSplitFeaturesStar.svg"
        self.split_action = QAction(QIcon(str(icon_path)), "", self.iface.mainWindow())
        self.split_action.setToolTip("Split feature, but only keeps the assetId on the largest feature")
        self.split_action.setStatusTip("Split feature, but only keeps the assetId on the largest feature")
        self.split_action.triggered.connect(self.activate_custom_split)
        self.iface.addToolBarIcon(self.split_action)

    def activate_custom_split(self):
        layer = self.iface.activeLayer()
        if not layer or layer.geometryType() not in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
            self.iface.messageBar().pushWarning("Custom Split", "Select a line or polygon layer.")
            return
        if not layer.isEditable():
            layer.startEditing()
        selected = layer.selectedFeatures()
        if len(selected) != 1:
            self.iface.messageBar().pushWarning("Custom Split", "Select exactly one feature to split.")
            return
        fid = selected[0].id()
        original_asset_id = selected[0]['assetId.identificator']
        before_ids = [f.id() for f in layer.getFeatures()]
        self.split_tool = CustomSplitTool(self.iface, layer, fid, original_asset_id, before_ids)
        self.iface.mapCanvas().setMapTool(self.split_tool)

    def unload(self):
        self.iface.removeToolBarIcon(self.split_action)
        self.split_action = None
        self.split_tool = None
