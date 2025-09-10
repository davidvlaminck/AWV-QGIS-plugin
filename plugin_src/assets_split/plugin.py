from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QColor
from qgis.core import (
    QgsWkbTypes,
    QgsFeatureRequest,
    QgsMessageLog,
    Qgis,
    QgsPointXY
)
from qgis.gui import QgsMapTool, QgsRubberBand


class CustomSplitTool(QgsMapTool):
    def __init__(self, iface, layer, fid, original_asset_id, before_ids):
        super().__init__(iface.mapCanvas())
        self.iface = iface
        self.layer = layer
        self.fid = fid
        self.original_asset_id = original_asset_id
        self.before_ids = set(before_ids)

        self.parts_points = []      # list of lines, each a list of QgsPointXY
        self.current_points = []    # points for the line being drawn

        # Rubber band for live drawing
        self.rubber_band = QgsRubberBand(self.iface.mapCanvas(), QgsWkbTypes.LineGeometry)
        self.rubber_band.setColor(QColor(255, 0, 0))
        self.rubber_band.setWidth(2)

        print("DEBUG: Tool initialised for fid", fid, "assetId", original_asset_id)

    def canvasReleaseEvent(self, event):
        pt = event.mapPoint()
        if event.button() == Qt.LeftButton:
            self.current_points.append(QgsPointXY(pt))
            self.rubber_band.addPoint(QgsPointXY(pt))
            print("DEBUG: Left click at", pt)
        elif event.button() == Qt.RightButton:
            print("DEBUG: Right click at", pt)
            if self.current_points:
                # Finish current line
                self.parts_points.append(self.current_points[:])
                print("DEBUG: Finished line with", len(self.current_points), "points")
                self.current_points.clear()
                self.rubber_band.reset(QgsWkbTypes.LineGeometry)
            else:
                # No active line: finish capture
                print("DEBUG: Finishing capture with", len(self.parts_points), "parts")
                self.finish_capture()

    def finish_capture(self):
        if not self.parts_points:
            print("DEBUG: No parts captured, aborting split")
            self.iface.mapCanvas().unsetMapTool(self)
            return

        self.run_split(self.parts_points)
        self.parts_points.clear()
        self.iface.mapCanvas().unsetMapTool(self)

    def run_split(self, parts_points):
        self.layer.beginEditCommand("Custom Split with assetId handling")

        for idx, pts in enumerate(parts_points, start=1):
            if len(pts) < 2:
                print(f"DEBUG: Skipping part {idx} (less than 2 points)")
                continue

            print(f"DEBUG: Calling splitFeatures for part {idx} with {len(pts)} points")
            result = self.layer.splitFeatures(pts, True)
            print("DEBUG: splitFeatures result code:", result)

            if result != 0:  # 0 means success
                self.iface.messageBar().pushCritical("Custom Split", f"Split failed for part {idx}.")
                self.layer.destroyEditCommand()
                return

        # Find new features by diffing IDs
        after_ids = {f.id() for f in self.layer.getFeatures()}
        created_ids = list(after_ids - self.before_ids)
        print("DEBUG: New feature IDs:", created_ids)

        # Pieces = original feature + any new features from diff
        target_ids = set(created_ids)
        target_ids.add(self.fid)

        req = QgsFeatureRequest().setFilterFids(list(target_ids))
        pieces = list(self.layer.getFeatures(req))

        if not pieces:
            print("DEBUG: No pieces found after split")
            self.layer.destroyEditCommand()
            return

        # Find largest
        largest_id = None
        largest_measure = -1
        for f in pieces:
            measure = f.geometry().area() if self.layer.geometryType() == QgsWkbTypes.PolygonGeometry else f.geometry().length()
            print(f"DEBUG: Piece {f.id()} measure: {measure}")
            if measure > largest_measure:
                largest_measure = measure
                largest_id = f.id()

        # Update assetId for all pieces
        attr_idx = self.layer.fields().indexFromName('assetId.identificator')
        if attr_idx < 0:
            self.iface.messageBar().pushCritical("Custom Split", "Field 'assetId.identificator' not found.")
            self.layer.destroyEditCommand()
            return

        for f in pieces:
            new_val = self.original_asset_id if f.id() == largest_id else None
            self.layer.changeAttributeValue(f.id(), attr_idx, new_val)

        self.layer.endEditCommand()
        self.layer.triggerRepaint()

        QgsMessageLog.logMessage(
            f"Custom Split complete: kept assetId for feature {largest_id}, cleared for {len(pieces)-1} others",
            "AssetsSplit",
            Qgis.Info
        )
        print(f"DEBUG: Kept assetId for {largest_id}, cleared for {len(pieces)-1} others")

class AssetsSplitPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.split_action = None
        self.split_tool = None

    def initGui(self):
        self.split_action = QAction("Custom Split", self.iface.mainWindow())
        self.split_action.triggered.connect(self.activate_custom_split)
        self.iface.addToolBarIcon(self.split_action)

    def activate_custom_split(self):
        layer = self.iface.activeLayer()
        print("DEBUG: Active layer name:", layer.name() if layer else None)
        print("DEBUG: Selected feature count:", layer.selectedFeatureCount() if layer else None)

        if not layer or layer.geometryType() not in (QgsWkbTypes.LineGeometry, QgsWkbTypes.PolygonGeometry):
            self.iface.messageBar().pushWarning("Custom Split", "Select a line or polygon layer.")
            return

        if not layer.isEditable():
            layer.startEditing()

        selected = layer.selectedFeatures()
        print("DEBUG: Selected IDs:", [f.id() for f in selected])

        if len(selected) != 1:
            self.iface.messageBar().pushWarning("Custom Split", "Select exactly one feature to split.")
            return

        fid = selected[0].id()
        original_asset_id = selected[0]['assetId.identificator']

        before_ids = [f.id() for f in layer.getFeatures()]
        print("DEBUG: Count of features before split:", len(before_ids))

        self.split_tool = CustomSplitTool(self.iface, layer, fid, original_asset_id, before_ids)
        self.iface.mapCanvas().setMapTool(self.split_tool)

    def unload(self):
        self.iface.removeToolBarIcon(self.split_action)
        self.split_action = None
        self.split_tool = None
