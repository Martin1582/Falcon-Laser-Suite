import sys
import threading
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QRectF, QObject, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from laser_control.application_controller import ApplicationController
from laser_control.artwork_import import ArtworkImportService, ArtworkSourceType, RasterImageSource, VectorArtworkSource, supported_file_filter
from laser_control.artwork_interaction import ArtworkSnapService
from laser_control.artwork_scaling import AutoFitResult, AutoFitService, autofit_to_transform
from laser_control.artwork_transform import ArtworkBounds, ArtworkTransform, normalize_paths, transform_paths
from laser_control.console_log_panel import ConsoleLogPanel
from laser_control.diagnostic_log import DiagnosticLog
from laser_control.gcode import (
    CUT_MODE,
    ENGRAVE_MODE,
    build_layered_polyline_gcode,
    build_multi_item_layered_polyline_gcode,
    build_rectangle_frame_gcode,
)
from laser_control.geometry_optimizer import GeometryOptimizationOptions
from laser_control.fill_toolpath import FillToolpath, build_layer_fill_toolpaths
from laser_control.layers import LayerType, active_output_layers, build_default_layers, layer_from_dict, layer_to_dict
from laser_control.job_history import (
    JobHistoryEntry,
    append_job_history,
    export_job_history,
    import_job_history,
    load_job_history,
    now_timestamp,
)
from laser_control.laser_intelligence_engine import LaserIntelligenceEngine, LaserIntelligenceResult
from laser_control.machine_actions import MachineActionRegistry
from laser_control.machine_profile_dialog import MachineProfileDialog
from laser_control.machine_log import MachineActionLog, MachineLogStatus
from laser_control.machine_panel import MachinePanel
from laser_control.machine_profiles import DEFAULT_MACHINE_PROFILE, MachineProfile, MachineProfileRepository
from laser_control.material_recommendations import material_deviation_warnings
from laser_control.material_db import delete_material, find_material, load_materials, upsert_material
from laser_control.models import MaterialProfile
from laser_control.profiles import DEFAULT_PROFILES
from laser_control.preview_model import JobPreviewModel, PreviewArtworkItem, PreviewHeadPosition, PreviewOptions, build_multi_item_preview_model, build_preview_model
from laser_control.qt_panels import LayerPanel, PreflightDialog, WorkspaceScanPanel
from laser_control.project import ArtworkItem, LaserProject, laser_project_from_dict, load_project, new_item_id, project_to_dict, save_project, transform_to_dict
from laser_control.serial_autodetect import find_laser_port
from laser_control.serial_grbl import list_serial_ports
from laser_control.services.assistant_service import AssistantService
from laser_control.services.job_service import JobPreparation, JobService
from laser_control.services.profile_service import ProfileService
from laser_control.status_panel import StatusPanel
from laser_control.svg_import import path_bounds
from laser_control.svg_optimization import SvgOptimizationResult, SvgVectorAnalysis, analyze_svg_paths, optimize_svg_paths
from laser_control.workflow_controller import JobContext, WorkflowController
from laser_control.workspace_coordinates import WorkspaceCoordinateMapper


AUTO_FIT_MARGIN_MM = 0.5
MATERIAL_SHAPE_RECTANGLE = "Rechteck"
MATERIAL_SHAPE_CIRCLE = "Kreis"
JOB_ORIGIN_LOWER_LEFT = "Links unten"
JOB_ORIGIN_CENTER = "Mitte"


class WorkerSignals(QObject):
    log = Signal(str)
    progress = Signal(str, int, int)
    error = Signal(str)
    finished = Signal(bool)
    port_detected = Signal(str)


class WorkAreaPreview(QWidget):
    artwork_position_requested = Signal(float, float)
    artwork_selection_changed = Signal(bool)
    artwork_item_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(360, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.width_mm = 300.0
        self.height_mm = 200.0
        self.paths = []
        self.preview_model = build_preview_model([], [], self.width_mm, self.height_mm)
        self.background_color = QColor("#1f1f1f")
        self.border_color = QColor("#777777")
        self.path_color = QColor("#ff6b5f")
        self.safe_area_color = QColor("#4d8dff")
        self.origin_color = QColor("#6dd47e")
        self.material_surface_color = QColor("#282b30")
        self.material_shadow_color = QColor("#15171a")
        self.grid_color = QColor("#3a3d43")
        self.head_color = QColor("#d93025")
        self.head_ring_color = QColor("#f2f2f2")
        self.material_shape = MATERIAL_SHAPE_RECTANGLE
        self.margin_mm = AUTO_FIT_MARGIN_MM
        self.job_origin = JOB_ORIGIN_LOWER_LEFT
        self.layers = []
        self.artwork_bounds = None
        self.artwork_selected = False
        self.snap_enabled = True
        self.snap_service = ArtworkSnapService()
        self.snap_vertical_guide_mm: float | None = None
        self.snap_horizontal_guide_mm: float | None = None
        self._dragging_artwork = False
        self._drag_offset_mm = (0.0, 0.0)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_preview(
        self,
        width_mm: float,
        height_mm: float,
        paths: list,
        material_shape: str = MATERIAL_SHAPE_RECTANGLE,
        margin_mm: float = AUTO_FIT_MARGIN_MM,
        job_origin: str = JOB_ORIGIN_LOWER_LEFT,
        layers: list | None = None,
    ) -> None:
        self.width_mm = max(1.0, width_mm)
        self.height_mm = max(1.0, height_mm)
        self.paths = paths
        self.material_shape = material_shape
        self.margin_mm = max(0.0, margin_mm)
        self.job_origin = job_origin
        self.layers = layers or []
        self.preview_model = build_preview_model(self.paths, self.layers, self.width_mm, self.height_mm)
        self.update()

    def set_artwork_interaction(self, bounds, snap_enabled: bool = True) -> None:
        self.artwork_bounds = bounds
        self.snap_enabled = snap_enabled
        if bounds is None:
            self._set_artwork_selected(False)
        self.update()

    def _coordinate_mapper(self) -> WorkspaceCoordinateMapper:
        margin = 18
        available_w = max(1, self.width() - margin * 2)
        available_h = max(1, self.height() - margin * 2)
        scale = min(available_w / self.width_mm, available_h / self.height_mm)
        area_w = self.width_mm * scale
        area_h = self.height_mm * scale
        return WorkspaceCoordinateMapper(
            (self.width() - area_w) / 2,
            (self.height() - area_h) / 2,
            self.width_mm,
            self.height_mm,
            scale,
        )

    def set_preview_model(
        self,
        model: JobPreviewModel,
        material_shape: str = MATERIAL_SHAPE_RECTANGLE,
        margin_mm: float = AUTO_FIT_MARGIN_MM,
        job_origin: str = JOB_ORIGIN_LOWER_LEFT,
    ) -> None:
        self.preview_model = model
        self.width_mm = model.work_width_mm
        self.height_mm = model.work_height_mm
        self.paths = [path.points for layer in model.render_layers for path in layer.paths]
        self.layers = []
        self.material_shape = material_shape
        self.margin_mm = max(0.0, margin_mm)
        self.job_origin = job_origin
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), self.background_color)

        mapper = self._coordinate_mapper()
        scale = mapper.scale_px_per_mm
        area_w = self.width_mm * scale
        area_h = self.height_mm * scale
        origin_x = mapper.origin_x_px
        origin_y = mapper.origin_y_px
        options = self.preview_model.options

        area_rect = QRectF(origin_x, origin_y, area_w, area_h)
        if options.show_work_area:
            self._draw_work_area(painter, area_rect, mapper, area_w, area_h)

        if options.show_bounds and self.preview_model.bounds is not None:
            min_x = self.preview_model.bounds.min_x
            min_y = self.preview_model.bounds.min_y
            max_x = self.preview_model.bounds.max_x
            max_y = self.preview_model.bounds.max_y
            out_of_bounds = min_x < 0 or min_y < 0 or max_x > self.width_mm or max_y > self.height_mm
            bounds_pen = QPen(QColor("#d93025") if out_of_bounds else self.safe_area_color, 2 if out_of_bounds else 1)
            bounds_pen.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(bounds_pen)
            painter.drawRect(QRectF(*mapper.rect_to_screen(min_x, min_y, max_x, max_y)))
            label_x, label_y = mapper.to_screen(min_x, max_y)
            painter.drawText(
                int(label_x + 6),
                int(label_y + 14),
                f"Job {self.preview_model.bounds.width_mm:.1f} x {self.preview_model.bounds.height_mm:.1f} mm",
            )

        render_layers = self.preview_model.render_layers
        if options.show_artwork:
            for raster in self.preview_model.raster_sources:
                self._draw_raster_source(painter, raster, mapper)

        has_render_paths = any(layer.paths for layer in render_layers) or bool(self.preview_model.raster_sources)
        if has_render_paths:
            layer_colors = ["#ff6b5f", "#fbbc04", "#6dd47e", "#c58cff"]
            first_start_drawn = False
            for layer_index, layer in enumerate(render_layers):
                if not options.show_artwork:
                    continue
                color = QColor(layer_colors[layer_index % len(layer_colors)])
                offset = layer_index * 1.5
                for polyline_index, preview_path in enumerate(sorted(layer.paths, key=lambda item: item.order)):
                    polyline = preview_path.points
                    if len(polyline) < 2:
                        continue
                    if preview_path.path_type == "overscan":
                        if not options.show_overscan or len(polyline) < 4:
                            continue
                        overscan_pen = QPen(QColor("#f29900"), 1)
                        overscan_pen.setStyle(Qt.PenStyle.DashLine)
                        painter.setPen(overscan_pen)
                        for start, end in ((polyline[0], polyline[1]), (polyline[2], polyline[3])):
                            sx1, sy1 = mapper.to_screen(*start)
                            sx2, sy2 = mapper.to_screen(*end)
                            painter.drawLine(int(sx1), int(sy1), int(sx2), int(sy2))
                        continue
                    painter.setPen(QPen(color, 1 if preview_path.path_type == "fill" else 2))
                    if not first_start_drawn and self.preview_model.start_position is not None:
                        start_x, start_y = self.preview_model.start_position
                        screen_x, screen_y = mapper.to_screen(start_x, start_y)
                        painter.setBrush(self.origin_color)
                        painter.drawEllipse(
                            QRectF(screen_x - 4, screen_y - 4, 8, 8)
                        )
                        first_start_drawn = True
                    if polyline_index == 0:
                        label_x, label_y = mapper.to_screen(polyline[0][0], polyline[0][1])
                        painter.drawText(
                            int(label_x + 6),
                            int(label_y + 12 + layer_index * 14),
                            f"{layer.order}: {layer.name}",
                        )
                    for index in range(1, len(polyline)):
                        x1, y1 = polyline[index - 1]
                        x2, y2 = polyline[index]
                        sx1, sy1 = mapper.to_screen(x1, y1)
                        sx2, sy2 = mapper.to_screen(x2, y2)
                        painter.drawLine(
                            int(sx1 + offset),
                            int(sy1 + offset),
                            int(sx2 + offset),
                            int(sy2 + offset),
                        )
        else:
            painter.setPen(QPen(self.border_color, 1))
            painter.drawText(
                area_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Noch kein Motiv geladen.\nSVG, PNG oder JPG importieren\noder Datei einfach hier hineinziehen.",
            )

        if options.show_gcode_path and self.preview_model.gcode_segments:
            self._draw_gcode_overlay(painter, mapper)

        if options.show_head_position and self.preview_model.head_position is not None:
            self._draw_head_position(painter, mapper)
        self._draw_artwork_item_bounds(painter, mapper)
        self._draw_artwork_selection(painter, mapper)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton or self.artwork_bounds is None:
            super().mousePressEvent(event)
            return
        workspace_x, workspace_y = self._coordinate_mapper().to_workspace(
            event.position().x(),
            event.position().y(),
        )
        bounds = self.artwork_bounds
        for item in reversed(self.preview_model.artwork_items):
            if not item.visible:
                continue
            item_bounds = item.transform.bounds if item.transform is not None else None
            if item_bounds is None and item.raster_source is not None and item.raster_source.transform is not None:
                item_bounds = item.raster_source.transform.bounds
            if item_bounds is None:
                continue
            if item_bounds.min_x <= workspace_x <= item_bounds.max_x and item_bounds.min_y <= workspace_y <= item_bounds.max_y:
                if item.item_id:
                    self.artwork_item_selected.emit(item.item_id)
                bounds = item_bounds
                self.artwork_bounds = item_bounds
                break
        inside = (
            bounds.min_x <= workspace_x <= bounds.max_x
            and bounds.min_y <= workspace_y <= bounds.max_y
        )
        self._set_artwork_selected(inside)
        if inside:
            self._dragging_artwork = True
            self._drag_offset_mm = (workspace_x - bounds.min_x, workspace_y - bounds.min_y)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.setFocus()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self._dragging_artwork or self.artwork_bounds is None:
            super().mouseMoveEvent(event)
            return
        workspace_x, workspace_y = self._coordinate_mapper().to_workspace(
            event.position().x(),
            event.position().y(),
        )
        candidate_x = workspace_x - self._drag_offset_mm[0]
        candidate_y = workspace_y - self._drag_offset_mm[1]
        snap = self.snap_service.snap(
            candidate_x,
            candidate_y,
            self.artwork_bounds.width_mm,
            self.artwork_bounds.height_mm,
            self.width_mm,
            self.height_mm,
            self.snap_enabled,
        )
        self.snap_vertical_guide_mm = snap.vertical_guide_mm
        self.snap_horizontal_guide_mm = snap.horizontal_guide_mm
        self.artwork_position_requested.emit(snap.x_mm, snap.y_mm)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._dragging_artwork:
            self._dragging_artwork = False
            self.snap_vertical_guide_mm = None
            self.snap_horizontal_guide_mm = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self.artwork_selected or self.artwork_bounds is None:
            super().keyPressEvent(event)
            return
        key_directions = {
            Qt.Key.Key_Left: (-1.0, 0.0),
            Qt.Key.Key_Right: (1.0, 0.0),
            Qt.Key.Key_Up: (0.0, 1.0),
            Qt.Key.Key_Down: (0.0, -1.0),
        }
        direction = key_directions.get(event.key())
        if direction is None:
            super().keyPressEvent(event)
            return
        modifiers = event.modifiers()
        step = 0.1 if modifiers & Qt.KeyboardModifier.ControlModifier else (
            10.0 if modifiers & Qt.KeyboardModifier.ShiftModifier else 1.0
        )
        self.artwork_position_requested.emit(
            self.artwork_bounds.min_x + direction[0] * step,
            self.artwork_bounds.min_y + direction[1] * step,
        )
        event.accept()

    def _set_artwork_selected(self, selected: bool) -> None:
        if self.artwork_selected == selected:
            return
        self.artwork_selected = selected
        self.artwork_selection_changed.emit(selected)
        self.update()

    def _draw_artwork_selection(self, painter: QPainter, mapper: WorkspaceCoordinateMapper) -> None:
        bounds = self.artwork_bounds
        if bounds is None:
            return
        if self.artwork_selected:
            selection_pen = QPen(QColor("#00bcd4"), 2)
            selection_pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(selection_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(*mapper.rect_to_screen(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y)))
            x, y = mapper.to_screen(bounds.min_x, bounds.max_y)
            painter.drawText(int(x + 6), int(y - 6), f"X {bounds.min_x:.1f} mm | Y {bounds.min_y:.1f} mm")
        guide_pen = QPen(QColor("#00bcd4"), 1)
        guide_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(guide_pen)
        if self.snap_vertical_guide_mm is not None:
            x, _ = mapper.to_screen(self.snap_vertical_guide_mm, 0.0)
            painter.drawLine(int(x), int(mapper.origin_y_px), int(x), int(mapper.origin_y_px + self.height_mm * mapper.scale_px_per_mm))
        if self.snap_horizontal_guide_mm is not None:
            _, y = mapper.to_screen(0.0, self.snap_horizontal_guide_mm)
            painter.drawLine(int(mapper.origin_x_px), int(y), int(mapper.origin_x_px + self.width_mm * mapper.scale_px_per_mm), int(y))

    def _draw_artwork_item_bounds(self, painter: QPainter, mapper: WorkspaceCoordinateMapper) -> None:
        for item in self.preview_model.artwork_items:
            if not item.visible:
                continue
            bounds = item.transform.bounds if item.transform is not None else None
            if bounds is None and item.raster_source is not None and item.raster_source.transform is not None:
                bounds = item.raster_source.transform.bounds
            if bounds is None:
                continue
            pen = QPen(QColor("#00bcd4") if item.selected else QColor("#9aa0a6"), 2 if item.selected else 1)
            pen.setStyle(Qt.PenStyle.DashLine if item.selected else Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(*mapper.rect_to_screen(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y)))
            label_x, label_y = mapper.to_screen(bounds.min_x, bounds.max_y)
            painter.drawText(int(label_x + 4), int(label_y - 4), item.name)

    def _draw_work_area(self, painter: QPainter, area_rect: QRectF, mapper: WorkspaceCoordinateMapper, area_w: float, area_h: float) -> None:
        shadow_rect = area_rect.adjusted(2, 2, 2, 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.material_shadow_color)
        if self.material_shape == MATERIAL_SHAPE_CIRCLE:
            diameter = min(area_w, area_h)
            circle_x = mapper.origin_x_px + (area_w - diameter) / 2
            circle_y = mapper.origin_y_px + (area_h - diameter) / 2
            painter.drawEllipse(QRectF(circle_x + 2, circle_y + 2, diameter, diameter))
        else:
            painter.drawRect(shadow_rect)

        painter.setBrush(self.material_surface_color)
        if self.material_shape == MATERIAL_SHAPE_CIRCLE:
            diameter = min(area_w, area_h)
            circle_x = mapper.origin_x_px + (area_w - diameter) / 2
            circle_y = mapper.origin_y_px + (area_h - diameter) / 2
            painter.setPen(QPen(self.border_color, 1))
            painter.drawEllipse(QRectF(circle_x, circle_y, diameter, diameter))
        else:
            painter.setPen(QPen(self.border_color, 1))
            painter.drawRect(area_rect)
            painter.setPen(QPen(QColor(self.material_surface_color).lighter(128), 1))
            painter.drawLine(int(area_rect.left() + 1), int(area_rect.top() + 1), int(area_rect.right() - 1), int(area_rect.top() + 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.border_color, 1))
        painter.drawText(int(mapper.origin_x_px), int(max(12, mapper.origin_y_px - 6)), f"Arbeitsbereich {self.width_mm:.0f} x {self.height_mm:.0f} mm")
        self._draw_grid(painter, mapper, area_w, area_h)

        safe_pen = QPen(self.safe_area_color, 1)
        safe_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(safe_pen)
        margin_px = self.margin_mm * mapper.scale_px_per_mm
        if self.material_shape == MATERIAL_SHAPE_CIRCLE:
            diameter = min(area_w, area_h)
            safe_diameter = max(1.0, diameter - margin_px * 2)
            safe_x = mapper.origin_x_px + (area_w - safe_diameter) / 2
            safe_y = mapper.origin_y_px + (area_h - safe_diameter) / 2
            painter.drawEllipse(QRectF(safe_x, safe_y, safe_diameter, safe_diameter))
        else:
            painter.drawRect(QRectF(mapper.origin_x_px + margin_px, mapper.origin_y_px + margin_px, max(1.0, area_w - margin_px * 2), max(1.0, area_h - margin_px * 2)))

        self._draw_origin_marker(painter, mapper, area_w, area_h)
        origin_label_x, origin_label_y = mapper.to_screen(0.0, 0.0)
        painter.drawText(int(origin_label_x + 8), int(origin_label_y - 8), "Nullpunkt")

    def _draw_grid(self, painter: QPainter, mapper: WorkspaceCoordinateMapper, area_w: float, area_h: float) -> None:
        grid_pen = QPen(self.grid_color, 1)
        grid_pen.setStyle(Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)
        spacing_mm = 50.0 if max(self.width_mm, self.height_mm) > 120 else 10.0
        x = spacing_mm
        while x < self.width_mm:
            px, _ = mapper.to_screen(x, 0.0)
            painter.drawLine(int(px), int(mapper.origin_y_px), int(px), int(mapper.origin_y_px + area_h))
            x += spacing_mm
        y = spacing_mm
        while y < self.height_mm:
            _, py = mapper.to_screen(0.0, y)
            painter.drawLine(int(mapper.origin_x_px), int(py), int(mapper.origin_x_px + area_w), int(py))
            y += spacing_mm

    def _draw_raster_source(self, painter: QPainter, source: RasterImageSource, mapper: WorkspaceCoordinateMapper) -> None:
        if not source.grayscale_data:
            return
        image = QImage(source.grayscale_data, source.pixel_width, source.pixel_height, QImage.Format.Format_Grayscale8).copy()
        if source.transform is not None:
            bounds = source.transform.bounds
            min_x, min_y, max_x, max_y = bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y
            if source.transform.rotation_deg:
                image = image.transformed(
                    QTransform().rotate(-source.transform.rotation_deg),
                    Qt.TransformationMode.SmoothTransformation,
                )
        else:
            min_x, min_y, max_x, max_y = source.bounding_box
        target = QRectF(*mapper.rect_to_screen(min_x, min_y, max_x, max_y))
        painter.drawImage(target, image)
        raster_pen = QPen(QColor("#fbbc04"), 1)
        raster_pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(raster_pen)
        painter.drawRect(target)
        painter.drawText(int(target.left() + 6), int(target.top() + 14), f"Raster: {source.file_name}")

    def _draw_gcode_overlay(self, painter: QPainter, mapper: WorkspaceCoordinateMapper) -> None:
        for segment in self.preview_model.gcode_segments:
            color = QColor("#9aa0a6") if segment.rapid else QColor("#00bcd4")
            pen = QPen(color, 1)
            if segment.rapid:
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            start_x, start_y = mapper.to_screen(segment.start_x, segment.start_y)
            end_x, end_y = mapper.to_screen(segment.end_x, segment.end_y)
            painter.drawLine(
                int(start_x),
                int(start_y),
                int(end_x),
                int(end_y),
            )

    def _draw_head_position(self, painter: QPainter, mapper: WorkspaceCoordinateMapper) -> None:
        position = self.preview_model.head_position
        if position is None:
            return
        x, y = mapper.to_screen(position.x_mm, position.y_mm)
        size = 8
        painter.setPen(QPen(self.head_ring_color, 2))
        painter.setBrush(self.head_color)
        painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.head_color, 1))
        painter.drawLine(int(x - size - 2), int(y), int(x + size + 2), int(y))
        painter.drawLine(int(x), int(y - size - 2), int(x), int(y + size + 2))
        painter.drawText(int(x + 8), int(y - 8), f"Kopf {position.source}")

    def _draw_origin_marker(self, painter: QPainter, mapper: WorkspaceCoordinateMapper, area_w: float, area_h: float) -> None:
        if self.job_origin == JOB_ORIGIN_CENTER:
            marker_x = mapper.origin_x_px + area_w / 2
            marker_y = mapper.origin_y_px + area_h / 2
        else:
            marker_x, marker_y = mapper.to_screen(0.0, 0.0)
        size = max(5.0, 2.0 * mapper.scale_px_per_mm)
        painter.setPen(QPen(self.origin_color, 2))
        painter.drawLine(int(marker_x - size), int(marker_y), int(marker_x + size), int(marker_y))
        painter.drawLine(int(marker_x), int(marker_y - size), int(marker_x), int(marker_y + size))


class LaserControlWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Laser Control")
        self.resize(1120, 720)
        self.setMinimumSize(980, 620)

        self.imported_paths = []
        self.original_imported_paths = []
        self.imported_file = None
        self.artwork_source = None
        self.artwork_transform: ArtworkTransform | None = None
        self.laser_project = LaserProject(300.0, 200.0)
        self.selected_artwork_item_id: str | None = None
        self._object_list_updating = False
        self._item_sources: dict[str, object] = {}
        self._item_vector_paths: dict[str, list] = {}
        self._item_optimized_vector_paths: dict[str, list] = {}
        self._item_svg_analyses: dict[str, SvgVectorAnalysis] = {}
        self._item_svg_optimization_results: dict[str, SvgOptimizationResult] = {}
        self._item_original_rasters: dict[str, RasterImageSource] = {}
        self._fill_toolpaths_by_item: dict[str, list[FillToolpath]] = {}
        self.svg_optimized_paths: list = []
        self.svg_analysis: SvgVectorAnalysis | None = None
        self.svg_optimization_result: SvgOptimizationResult | None = None
        self.laser_intelligence_engine = LaserIntelligenceEngine()
        self.laser_intelligence_result: LaserIntelligenceResult | None = None
        self._item_intelligence_results: dict[str, LaserIntelligenceResult] = {}
        self.raster_sources: list[RasterImageSource] = []
        self.original_raster_source: RasterImageSource | None = None
        self.autofit_result: AutoFitResult | None = None
        self.fill_toolpaths: list[FillToolpath] = []
        self.material_point_a = None
        self.material_point_b = None
        self.material_points = {1: None, 2: None, 3: None, 4: None}
        self.material_measurement = None
        self.current_project_path = None
        self.material_db_records = load_materials()
        self.profile_service = ProfileService()
        self.job_service = JobService()
        self.import_service = ArtworkImportService()
        self.autofit_service = AutoFitService()
        self.assistant_service = AssistantService()
        self.diagnostic_log = DiagnosticLog()
        self.machine_action_registry = MachineActionRegistry()
        self.action_buttons: dict[str, list[QPushButton]] = {}
        self.app_controller = ApplicationController(
            self._threadsafe_log,
            self._threadsafe_progress,
            lambda: self.serial_port.currentText() if hasattr(self, "serial_port") else "",
            self.diagnostic_log,
        )
        self.machine_action_log = MachineActionLog()
        self.workflow = WorkflowController(self.job_service, self.machine_action_log, self.log)
        self.machine_profile_repository = MachineProfileRepository()
        self.machine_profile = self.machine_profile_repository.active_profile()
        self.job_history = load_job_history()
        self.material_profiles = self.profile_service.material_profiles
        self.last_prepared_job = None
        self.dark_mode_enabled = True
        self.worker_busy = False
        self._parameter_source = "Materialprofil/Default"
        self._closing = False
        self._transform_ui_updating = False
        self._worker_threads: list[threading.Thread] = []

        self.signals = WorkerSignals()
        self.signals.log.connect(self.log)
        self.signals.progress.connect(self._set_progress)
        self.signals.error.connect(self._show_worker_error)
        self.signals.finished.connect(self._worker_finished)
        self.signals.port_detected.connect(self._apply_detected_port)
        self._machine_state_timer = QTimer(self)
        self._machine_state_timer.setInterval(250)
        self._machine_state_timer.timeout.connect(self._sync_position_indicator)
        self._machine_state_timer.start()

        self.controller = self.app_controller.controller
        self.active_connection_mode = "Simulator"

        self._build_layout()
        self.log(f"Materialprofile Speicherpfad: {self.profile_service.storage_path}")
        self.log(f"Materialprofile geladen: {len(self.profile_service.names())}")
        if self.machine_profile_repository.load_error:
            self.log(f"Maschinenprofile konnten nicht geladen werden, Default wird genutzt: {self.machine_profile_repository.load_error}")
        self._apply_machine_profile(self.machine_profile)
        self.log(f"Maschinenprofil geladen: {self.machine_profile.name}")
        self._refresh_material_db_combo()
        self._apply_mode_profile_to_controls()
        self._sync_layers_from_controls(preserve_states=False)
        self._refresh_ports()
        self._refresh_gcode()
        self._draw_preview()
        self._sync_connection_indicator()
        self.diagnostic_log.event("App gestartet.")
        self.diagnostic_log.event(f"Diagnose-Log: {self.diagnostic_log.path}")
        self.log(f"Diagnose-Log aktiv: {self.diagnostic_log.path}")

    def _build_layout(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 8)
        self.setCentralWidget(root)

        self._build_action_bar(root_layout)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        root_layout.addWidget(self.main_splitter, 1)

        self.left_sidebar = QWidget()
        self.left_sidebar.setObjectName("leftSidebar")
        self.left_sidebar.setMinimumWidth(300)
        self.left_sidebar.setMaximumWidth(340)
        left_layout = QVBoxLayout(self.left_sidebar)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(0)
        self.sidebar_toolbox = QWidget()
        self.sidebar_toolbox.setObjectName("sidebarSections")
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.sidebar_toolbox)
        left_layout.addWidget(self.sidebar_scroll)
        self.main_splitter.addWidget(self.left_sidebar)
        self.sidebar_combos = []

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.main_splitter.addWidget(content)
        self.main_splitter.setStretchFactor(0, 0)
        self.main_splitter.setStretchFactor(1, 5)
        self.main_splitter.setSizes([320, 1380])

        self._build_sidebar(self.sidebar_toolbox)
        self._build_content(content_layout)
        self._build_status_bar(root_layout)

    def _build_action_bar(self, layout: QVBoxLayout) -> None:
        action_bar = QFrame()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(0, 0, 0, 4)
        action_layout.setSpacing(8)
        self.workflow_hint = QLabel(
            "Maschine  >  Projekt & Material  >  Layer  >  Vorschau / Frame  >  Preflight / Start"
        )
        self.workflow_hint.setObjectName("workflowHint")
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setMaximumHeight(42)
        action_layout.addWidget(self.workflow_hint, 1)
        action_layout.addStretch(1)
        self.theme_switch = QCheckBox("Dark")
        self.theme_switch.setChecked(True)
        self.theme_switch.toggled.connect(self._apply_theme)
        action_layout.addWidget(self.theme_switch)
        layout.addWidget(action_bar)

    def _add_sidebar_section(self, container_layout: QVBoxLayout, title: str, body: QWidget, expanded: bool) -> QGroupBox:
        section = QGroupBox(title)
        section.setObjectName("sidebarSection")
        section.setCheckable(True)
        section.setChecked(expanded)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(8, 10, 8, 8)
        section_layout.setSpacing(6)
        section_layout.addWidget(body)
        body.setVisible(expanded)
        section.toggled.connect(body.setVisible)
        container_layout.addWidget(section)
        self.sidebar_sections[title] = section
        return section

    def _build_sidebar(self, toolbox: QWidget) -> None:
        sidebar_layout = QVBoxLayout(toolbox)
        sidebar_layout.setContentsMargins(6, 6, 6, 10)
        sidebar_layout.setSpacing(8)
        self.sidebar_sections: dict[str, QGroupBox] = {}

        machine_page = QWidget()
        machine_layout = QVBoxLayout(machine_page)
        machine_layout.setContentsMargins(0, 0, 0, 0)
        machine_layout.setSpacing(4)

        self.machine_panel = MachinePanel(self.machine_action_registry)
        self.connection_label = self.machine_panel.connection_label
        self.connection_mode = self.machine_panel.connection_mode
        self.serial_port = self.machine_panel.serial_port
        self._configure_sidebar_combo(self.connection_mode)
        self._configure_sidebar_combo(self.serial_port)
        self.machine_panel.mode_changed.connect(self._switch_controller)
        self.machine_panel.action_triggered.connect(self._trigger_machine_action)
        self.machine_panel.profile_changed.connect(self._machine_profile_changed)
        self.machine_panel.profile_editor_requested.connect(self._edit_machine_profiles)
        self.machine_panel.set_machine_profiles(
            self.machine_profile_repository.profiles(),
            self.machine_profile_repository.active_profile_id(),
        )
        for action_id, buttons in self.machine_panel.action_buttons.items():
            self.action_buttons.setdefault(action_id, []).extend(buttons)
        machine_layout.addWidget(self.machine_panel)
        self._add_sidebar_section(sidebar_layout, "Maschine", machine_page, True)

        position_page = QWidget()
        position_page_layout = QVBoxLayout(position_page)
        position_page_layout.setContentsMargins(0, 0, 0, 0)
        position_page_layout.setSpacing(6)
        jog_group = QGroupBox("Position / Jog")
        jog = QGridLayout(jog_group)
        jog.setContentsMargins(8, 8, 8, 8)
        jog.setHorizontalSpacing(8)
        jog.setVerticalSpacing(8)
        for column in range(3):
            jog.setColumnStretch(column, 1)
        jog.addWidget(self._machine_action_button("jog_y_plus", "Sidebar"), 0, 1)
        jog.addWidget(self._machine_action_button("jog_x_minus", "Sidebar"), 1, 0)
        jog.addWidget(self._machine_action_button("jog_x_plus", "Sidebar"), 1, 2)
        jog.addWidget(self._machine_action_button("jog_y_minus", "Sidebar"), 2, 1)
        position_page_layout.addWidget(jog_group)
        alignment_group = QGroupBox("Material ausrichten")
        alignment_layout = QVBoxLayout(alignment_group)
        alignment_layout.setContentsMargins(8, 8, 8, 8)
        alignment_layout.setSpacing(6)
        self.alignment_power = self._spin(1, 5, 1, suffix=" %")
        self.alignment_power.setToolTip("Sichere Pointer-Leistung, maximal 5%. Niemals Materialprofil-Power.")
        self.alignment_power.valueChanged.connect(self._alignment_power_changed)
        self.alignment_status = QLabel("Ausrichtmodus aus")
        self.alignment_status.setWordWrap(True)
        alignment_layout.addWidget(QLabel("Pointer-Leistung"))
        alignment_layout.addWidget(self.alignment_power)
        alignment_layout.addWidget(self._machine_action_button("toggle_alignment", "Sidebar"))
        alignment_layout.addWidget(self.alignment_status)
        self.workspace_scan_panel = WorkspaceScanPanel(
            self._machine_action_button("toggle_work_area_trace", "Sidebar"),
            self._button("Pointer 2s testen", self._test_alignment_pointer),
        )
        self.work_area_trace_status = self.workspace_scan_panel.status_label
        alignment_layout.addWidget(self.workspace_scan_panel)
        position_page_layout.addWidget(alignment_group)
        self._add_sidebar_section(sidebar_layout, "Positionierung", position_page, False)

        project_page = QWidget()
        project_page_layout = QVBoxLayout(project_page)
        project_page_layout.setContentsMargins(0, 0, 0, 0)
        project_page_layout.setSpacing(6)

        project = QGroupBox("Projekt")
        project_layout = QVBoxLayout(project)
        project_layout.setContentsMargins(8, 8, 8, 8)
        project_layout.setSpacing(6)
        project_layout.addWidget(self._button("Datei importieren", self._import_svg))
        self.object_table = QTableWidget(0, 4)
        self.object_table.setHorizontalHeaderLabels(["S", "A", "Name", "Typ"])
        self.object_table.verticalHeader().setVisible(False)
        self.object_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.object_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.object_table.setMinimumHeight(120)
        self.object_table.setMaximumHeight(180)
        self.object_table.setColumnWidth(0, 28)
        self.object_table.setColumnWidth(1, 28)
        self.object_table.setColumnWidth(3, 64)
        self.object_table.horizontalHeader().setStretchLastSection(False)
        self.object_table.horizontalHeader().setMinimumSectionSize(26)
        self.object_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.object_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.object_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.object_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.object_table.itemChanged.connect(self._object_table_item_changed)
        self.object_table.itemSelectionChanged.connect(self._object_table_selection_changed)
        project_layout.addWidget(self.object_table)
        self.project_empty_state = QLabel("Noch keine Motive vorhanden.\nJetzt erstes Motiv importieren.")
        self.project_empty_state.setObjectName("projectEmptyState")
        self.project_empty_state.setWordWrap(True)
        project_layout.addWidget(self.project_empty_state)
        project_layout.addWidget(self._button("Speichern", self._save_project))
        project_layout.addWidget(self._button("Laden", self._load_project))
        project_page_layout.addWidget(project)

        material = QGroupBox("Material")
        material_layout = QVBoxLayout(material)
        material_layout.setContentsMargins(8, 8, 8, 8)
        material_layout.setSpacing(6)
        self.material_measurement_label = QLabel("Nicht eingemessen")
        self.material_measurement_label.setWordWrap(True)
        material_layout.addWidget(self.material_measurement_label)
        material_layout.addWidget(self._button("Ecke 1 setzen", lambda: self._capture_material_point(1)))
        material_layout.addWidget(self._button("Ecke 2 setzen", lambda: self._capture_material_point(2)))
        material_layout.addWidget(self._button("Ecke 3 setzen", lambda: self._capture_material_point(3)))
        material_layout.addWidget(self._button("Ecke 4 setzen", lambda: self._capture_material_point(4)))
        material_layout.addWidget(self._button("Groesse uebernehmen", self._apply_material_measurement))
        self.material_db_name = QComboBox()
        self.material_db_name.setEditable(True)
        self._configure_sidebar_combo(self.material_db_name)
        material_layout.addWidget(QLabel("Name"))
        material_layout.addWidget(self.material_db_name)
        size_grid = QGridLayout()
        size_grid.setHorizontalSpacing(8)
        size_grid.setVerticalSpacing(4)
        self.material_db_width = self._double_spin(0, 2000, 0, " mm")
        self.material_db_height = self._double_spin(0, 2000, 0, " mm")
        size_grid.addWidget(QLabel("Breite"), 0, 0)
        size_grid.addWidget(self.material_db_width, 0, 1)
        size_grid.addWidget(QLabel("Hoehe"), 1, 0)
        size_grid.addWidget(self.material_db_height, 1, 1)
        size_grid.setColumnStretch(1, 1)
        material_layout.addLayout(size_grid)
        material_layout.addWidget(self._button("Material speichern", self._save_measured_material))
        self.material_db_selection = QComboBox()
        self._configure_sidebar_combo(self.material_db_selection)
        self.material_db_selection.currentTextChanged.connect(lambda _text: self._select_material_record())
        material_layout.addWidget(self.material_db_selection)
        material_layout.addWidget(self._button("Material laden", self._load_measured_material))
        material_layout.addWidget(self._button("Material loeschen", self._delete_measured_material))
        project_page_layout.addWidget(material)
        self._add_sidebar_section(sidebar_layout, "Projekt", project_page, False)

        job_page = QWidget()
        job_page_layout = QVBoxLayout(job_page)
        job_page_layout.setContentsMargins(0, 0, 0, 0)
        job_page_layout.setSpacing(4)
        job = QGroupBox("Job")
        job_layout = QVBoxLayout(job)
        job_layout.setContentsMargins(8, 8, 8, 8)
        job_layout.setSpacing(7)
        self.operation_mode = QComboBox()
        self.operation_mode.addItems([ENGRAVE_MODE, CUT_MODE])
        self._configure_sidebar_combo(self.operation_mode)
        self.operation_mode.currentTextChanged.connect(self._on_operation_mode_changed)
        job_layout.addWidget(QLabel("Modus"))
        job_layout.addWidget(self.operation_mode)
        job_layout.addWidget(QLabel("Job-Art"))
        self.job_kind = QComboBox()
        self.job_kind.addItems(["Einzelstueck"])
        self._configure_sidebar_combo(self.job_kind)
        job_layout.addWidget(self.job_kind)
        self.auto_home_after_job = QCheckBox("Auto-Home nach Einzelstueck")
        self.auto_home_after_job.setToolTip("Nach erfolgreichem Einzelstueck automatisch Home anfahren.")
        self.auto_home_after_job.setChecked(True)
        self.auto_home_after_job.toggled.connect(lambda _checked: self._settings_changed())
        job_layout.addWidget(self.auto_home_after_job)
        job_layout.addWidget(self._machine_action_button("frame", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("dry_run", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("start_job", "Sidebar"))
        pause_row = QHBoxLayout()
        pause_row.setSpacing(8)
        pause_row.addWidget(self._machine_action_button("pause", "Sidebar"))
        pause_row.addWidget(self._machine_action_button("resume", "Sidebar"))
        job_layout.addLayout(pause_row)
        job_layout.addWidget(self._machine_action_button("stop", "Sidebar"))
        job_layout.addWidget(self._machine_action_button("emergency_stop", "Sidebar"))
        job_page_layout.addWidget(job)
        self._add_sidebar_section(sidebar_layout, "Job", job_page, True)

        diagnostics_page = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_page)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        diagnostics_layout.setSpacing(6)
        machine_diagnostics = QGroupBox("Maschinendiagnose")
        machine_diagnostics_layout = QVBoxLayout(machine_diagnostics)
        machine_diagnostics_layout.setContentsMargins(8, 8, 8, 8)
        machine_diagnostics_layout.setSpacing(6)
        machine_diagnostics_layout.addWidget(self._machine_action_button("status", "Diagnose"))
        machine_diagnostics_layout.addWidget(self._machine_action_button("settings", "Diagnose"))
        machine_diagnostics_layout.addWidget(self._button("Diagnose exportieren", self._export_diagnostics))
        diagnostics_layout.addWidget(machine_diagnostics)

        svg_quality = QGroupBox("SVG-Optimierung")
        svg_quality_layout = QVBoxLayout(svg_quality)
        svg_quality_layout.setContentsMargins(8, 8, 8, 8)
        svg_quality_layout.setSpacing(6)
        self.svg_simplify_enabled = QCheckBox("Konturen vereinfachen")
        self.svg_simplify_enabled.setToolTip("Douglas-Peucker-Vereinfachung auf SVG-Pfadpunkte anwenden. Originaldatei bleibt unveraendert.")
        self.svg_simplify_enabled.toggled.connect(lambda _checked: self._svg_optimization_changed())
        self.svg_tolerance = QComboBox()
        for tolerance in (0.01, 0.02, 0.05, 0.10):
            self.svg_tolerance.addItem(f"{tolerance:.2f} mm", tolerance)
        self.svg_tolerance.setCurrentIndex(1)
        self.svg_tolerance.setToolTip("Empfehlung fuer feine Falcon-10W-Motive: 0.02 mm oder 0.05 mm.")
        self.svg_tolerance.currentIndexChanged.connect(lambda _index: self._svg_optimization_changed())
        self._configure_sidebar_combo(self.svg_tolerance)
        self.svg_remove_duplicates = QCheckBox("Doppelte Linien entfernen")
        self.svg_remove_duplicates.setToolTip("Nahezu identische Liniensegmente optional nur einmal gravieren.")
        self.svg_remove_duplicates.toggled.connect(lambda _checked: self._svg_optimization_changed())
        self.svg_show_analysis = QCheckBox("Analyse anzeigen")
        self.svg_show_analysis.setChecked(True)
        self.svg_show_analysis.toggled.connect(lambda _checked: self._update_import_summary())
        self.svg_analysis_label = QLabel("Keine SVG-Analyse")
        self.svg_analysis_label.setWordWrap(True)
        self.laser_intelligence_label = QLabel("Laser Intelligence: keine Analyse")
        self.laser_intelligence_label.setWordWrap(True)
        svg_quality_layout.addWidget(self.svg_simplify_enabled)
        svg_quality_layout.addWidget(QLabel("Toleranz"))
        svg_quality_layout.addWidget(self.svg_tolerance)
        svg_quality_layout.addWidget(self.svg_remove_duplicates)
        svg_quality_layout.addWidget(self.svg_show_analysis)
        svg_quality_layout.addWidget(self.svg_analysis_label)
        svg_quality_layout.addWidget(self.laser_intelligence_label)
        diagnostics_layout.addWidget(svg_quality)

        expert_tools = QGroupBox("Expertenfunktionen")
        expert_layout = QVBoxLayout(expert_tools)
        expert_layout.setContentsMargins(8, 8, 8, 8)
        expert_layout.setSpacing(6)
        expert_layout.addWidget(self._button("Profile exportieren", self._export_profiles))
        expert_layout.addWidget(self._button("Profile importieren", self._import_profiles))
        expert_layout.addWidget(self._button("Testmatrix erzeugen", self._generate_test_matrix))
        expert_layout.addWidget(self._button("Als gut speichern", lambda: self._record_job_result("good")))
        expert_layout.addWidget(self._button("Problem speichern", lambda: self._record_job_result("problem")))
        expert_layout.addWidget(self._button("Historie exportieren", self._export_history))
        expert_layout.addWidget(self._button("Historie importieren", self._import_history))
        diagnostics_layout.addWidget(expert_tools)
        self._add_sidebar_section(sidebar_layout, "Diagnose", diagnostics_page, False)
        sidebar_layout.addStretch(1)

    def _build_content(self, layout: QVBoxLayout) -> None:
        self.workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_splitter.setChildrenCollapsible(False)
        layout.addWidget(self.workspace_splitter, 1)

        main_panel = QWidget()
        main_layout = QVBoxLayout(main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace_splitter.addWidget(main_panel)

        self.right_sidebar = QWidget()
        self.right_sidebar.setObjectName("rightSidebar")
        self.right_sidebar.setMinimumWidth(320)
        self.right_sidebar.setMaximumWidth(350)
        right_layout = QVBoxLayout(self.right_sidebar)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(8)
        self.workspace_splitter.addWidget(self.right_sidebar)
        self.workspace_splitter.setStretchFactor(0, 7)
        self.workspace_splitter.setStretchFactor(1, 2)
        self.workspace_splitter.setSizes([1120, 330])

        layout = main_layout

        workflow_group = QFrame()
        workflow_group.setObjectName("workflowStrip")
        workflow_layout = QVBoxLayout(workflow_group)
        workflow_layout.setContentsMargins(6, 4, 6, 4)
        self.workflow_status = QLabel("1 Maschine verbinden -> 2 Homing -> 3 Material -> 4 Datei -> 5 Layer -> 6 Vorschau -> 7 Frame -> 8 Preflight -> 9 Start")
        self.workflow_status.setObjectName("workflowStatus")
        self.workflow_status.setWordWrap(True)
        self.workflow_status.setMaximumHeight(58)
        workflow_layout.addWidget(self.workflow_status)
        layout.addWidget(workflow_group)

        settings = QFrame()
        settings_layout = QHBoxLayout(settings)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        self.work_width = self._double_spin(10, 2000, 300, " mm")
        self.work_height = self._double_spin(10, 2000, 200, " mm")
        self.material_shape = QComboBox()
        self.material_shape.addItems([MATERIAL_SHAPE_RECTANGLE, MATERIAL_SHAPE_CIRCLE])
        self.material_shape.currentTextChanged.connect(lambda _text: self._settings_changed())
        self.job_origin = QComboBox()
        self.job_origin.addItems([JOB_ORIGIN_LOWER_LEFT, JOB_ORIGIN_CENTER])
        self.job_origin.currentTextChanged.connect(lambda _text: self._settings_changed())
        self.profile_name = QComboBox()
        self.profile_name.addItems(self.profile_service.names())
        self.profile_name.currentTextChanged.connect(lambda _text: self._profile_selected())
        for widget in (self.work_width, self.work_height):
            widget.valueChanged.connect(self._settings_changed)
        settings_layout.addWidget(QLabel("Arbeitsbereich"))
        settings_layout.addWidget(self.work_width)
        settings_layout.addWidget(QLabel("x"))
        settings_layout.addWidget(self.work_height)
        settings_layout.addSpacing(8)
        settings_layout.addWidget(QLabel("Form"))
        settings_layout.addWidget(self.material_shape)
        settings_layout.addWidget(QLabel("Ursprung"))
        settings_layout.addWidget(self.job_origin)
        settings_layout.addSpacing(8)
        settings_layout.addSpacing(16)
        settings_layout.addWidget(QLabel("Material"))
        settings_layout.addWidget(self.profile_name, 1)
        self.add_material_button = self._button("Material hinzufuegen", self._open_add_material_dialog)
        settings_layout.addWidget(self.add_material_button)
        layout.addWidget(settings)

        material_settings = QFrame()
        material_layout = QHBoxLayout(material_settings)
        material_layout.setContentsMargins(0, 0, 0, 0)
        self.power_percent = self._spin(0, 100, DEFAULT_PROFILES[0].power_percent, suffix=" %")
        self.speed_mm_min = self._spin(50, 12000, DEFAULT_PROFILES[0].speed_mm_min, 50, " mm/min")
        self.passes = self._spin(1, 20, DEFAULT_PROFILES[0].passes, suffix=" x")
        for widget in (self.power_percent, self.speed_mm_min, self.passes):
            widget.valueChanged.connect(self._material_settings_changed)
        material_layout.addWidget(QLabel("Leistung %"))
        material_layout.addWidget(self.power_percent)
        material_layout.addWidget(QLabel("Geschwindigkeit"))
        material_layout.addWidget(self.speed_mm_min)
        material_layout.addWidget(QLabel("Durchgaenge"))
        material_layout.addWidget(self.passes)
        material_layout.addStretch(1)
        layout.addWidget(material_settings)

        self.material_summary = QLabel("Material: kein Profil gewaehlt")
        self.material_summary.setObjectName("materialSummary")
        self.material_summary.setWordWrap(True)
        self.material_summary.setMaximumHeight(48)
        layout.addWidget(self.material_summary)

        self.layer_panel = LayerPanel(on_changed=self._layer_changed)
        right_layout.addWidget(self.layer_panel)

        self.project_summary = QLabel("Projekt: Noch keine Motive vorhanden. Jetzt erstes Motiv importieren.")
        self.project_summary.setObjectName("projectSummary")
        self.project_summary.setWordWrap(True)
        self.project_summary.setMaximumHeight(48)
        layout.addWidget(self.project_summary)

        self.job_summary = QLabel("Naechster Schritt: Motiv importieren.")
        self.job_summary.setObjectName("jobSummary")
        self.job_summary.setWordWrap(True)
        self.job_summary.setMaximumHeight(48)
        layout.addWidget(self.job_summary)

        self.assistant_summary = QTextEdit()
        self.assistant_summary.setReadOnly(True)
        self.assistant_summary.setMinimumHeight(105)
        self.assistant_summary.setMaximumHeight(155)
        self.assistant_summary.setObjectName("assistantSummary")
        assistant_group = QGroupBox("Gefuehrter Check")
        assistant_layout = QVBoxLayout(assistant_group)
        assistant_layout.addWidget(self.assistant_summary)
        right_layout.addWidget(assistant_group)

        placement = QGroupBox("Motiv transformieren")
        placement.setVisible(False)
        placement_container_layout = QVBoxLayout(placement)
        placement_container_layout.setContentsMargins(6, 4, 6, 6)
        placement_body = QWidget()
        placement_layout = QGridLayout(placement_body)
        placement_container_layout.addWidget(placement_body)
        self.transform_group = placement
        self.transform_body = placement_body
        self.svg_auto = QRadioButton("Automatisch")
        self.svg_manual = QRadioButton("Manuell")
        self.svg_auto.setChecked(True)
        self.svg_auto.toggled.connect(lambda _checked: self._apply_svg_placement())
        self.svg_margin = self._double_spin(0, 50, AUTO_FIT_MARGIN_MM, " mm")
        self.svg_manual_width = self._double_spin(0.1, 2000, 50, " mm")
        self.artwork_height = self._double_spin(0.1, 2000, 50, " mm")
        self.artwork_scale_percent = self._double_spin(0.1, 1000, 100, " %")
        self.artwork_rotation = self._double_spin(-360, 360, 0, " deg")
        self.artwork_keep_aspect = QCheckBox("Seitenverhaeltnis sperren")
        self.artwork_keep_aspect.setChecked(True)
        self.svg_offset_x = self._double_spin(-2000, 2000, 0, " mm")
        self.svg_offset_y = self._double_spin(-2000, 2000, 0, " mm")
        self.svg_margin.valueChanged.connect(lambda _value: self._apply_svg_placement())
        self.svg_manual_width.valueChanged.connect(self._transform_width_changed)
        self.artwork_height.valueChanged.connect(self._transform_height_changed)
        self.artwork_scale_percent.valueChanged.connect(self._transform_scale_changed)
        self.artwork_rotation.valueChanged.connect(self._transform_rotation_changed)
        self.artwork_keep_aspect.toggled.connect(self._transform_aspect_changed)
        self.svg_offset_x.valueChanged.connect(lambda _value: self._transform_position_changed())
        self.svg_offset_y.valueChanged.connect(lambda _value: self._transform_position_changed())
        placement_layout.setContentsMargins(8, 8, 8, 8)
        placement_layout.setHorizontalSpacing(6)
        placement_layout.setVerticalSpacing(4)
        placement_layout.addWidget(self.svg_auto, 0, 0)
        placement_layout.addWidget(self.svg_manual, 0, 1)
        placement_layout.addWidget(QLabel("Rand"), 0, 2)
        placement_layout.addWidget(self.svg_margin, 0, 3)
        placement_layout.addWidget(self.artwork_keep_aspect, 0, 4, 1, 2)
        self.svg_size_label = QLabel("Motiv: keine SVG")
        self.svg_size_label.setWordWrap(False)
        self.svg_size_label.setMaximumHeight(22)

        compact_fields = (
            ("X", self.svg_offset_x),
            ("Y", self.svg_offset_y),
            ("Breite", self.svg_manual_width),
            ("Hoehe", self.artwork_height),
            ("Skalierung", self.artwork_scale_percent),
            ("Rotation", self.artwork_rotation),
        )
        for index, (label, widget) in enumerate(compact_fields):
            row = 1 + index // 3
            column = (index % 3) * 2
            placement_layout.addWidget(QLabel(label), row, column)
            placement_layout.addWidget(widget, row, column + 1)

        rotate_left = self._button("Links drehen", lambda: self._rotate_artwork(-90.0))
        rotate_right = self._button("Rechts drehen", lambda: self._rotate_artwork(90.0))
        placement_layout.addWidget(rotate_left, 3, 0)
        placement_layout.addWidget(rotate_right, 3, 1)
        placement_layout.addWidget(self._button("Zentrieren", self._center_artwork), 3, 2)
        placement_layout.addWidget(self._button("Links unten", self._place_artwork_lower_left), 3, 3)
        placement_layout.addWidget(self._button("Einpassen", self._fit_svg_to_material), 3, 4)
        placement_layout.addWidget(self._button("Originalgroesse", self._restore_artwork_original_size), 3, 5)
        placement_layout.addWidget(self.svg_size_label, 4, 0, 1, 6)
        placement_body.setVisible(False)
        self.transform_button = self._button("Motiv transformieren", self._open_transform_dialog)
        layout.addWidget(self.transform_button)

        self.preview = WorkAreaPreview()
        preview_group = QGroupBox("Vorschau")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_options = {
            "artwork": QCheckBox("Motiv"),
            "bounds": QCheckBox("Bounding Box"),
            "work_area": QCheckBox("Arbeitsbereich"),
            "head": QCheckBox("Kopfposition"),
            "gcode": QCheckBox("GCode-Pfad"),
            "overscan": QCheckBox("Overscan"),
            "snap": QCheckBox("Snap"),
        }
        option_row = QHBoxLayout()
        for key, checkbox in self.preview_options.items():
            checkbox.setChecked(key != "gcode")
            checkbox.toggled.connect(lambda _checked: self._draw_preview())
            option_row.addWidget(checkbox)
        option_row.addStretch(1)
        preview_layout.addLayout(option_row)
        self.import_summary_label = QLabel("Import: keine Datei geladen")
        self.import_summary_label.setObjectName("importSummary")
        self.import_summary_label.setWordWrap(False)
        self.import_summary_label.setMaximumHeight(22)
        preview_layout.addWidget(self.import_summary_label)
        self.preview_position_label = QLabel("Motivposition: --")
        self.preview_position_label.setObjectName("previewPosition")
        self.preview_position_label.setMaximumHeight(22)
        preview_layout.addWidget(self.preview_position_label)
        self.preview.artwork_position_requested.connect(self._move_artwork_from_preview)
        self.preview.artwork_selection_changed.connect(self._preview_selection_changed)
        self.preview.artwork_item_selected.connect(self._select_artwork_item)
        preview_layout.addWidget(self.preview)
        layout.addWidget(preview_group, 1)

        self.expert_tabs = QTabWidget()
        self.gcode_group = QGroupBox("G-Code")
        gcode_layout = QVBoxLayout(self.gcode_group)
        self.gcode_text = QTextEdit()
        self.gcode_text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.gcode_text.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        self.gcode_text.textChanged.connect(self._fit_gcode_panel_to_text)
        self.gcode_text.textChanged.connect(self._update_job_summary)
        self.gcode_text.textChanged.connect(self._update_assistant_panel)
        gcode_layout.addWidget(self.gcode_text)

        self.console_log_panel = ConsoleLogPanel()
        self.log_text = self.console_log_panel.log_text
        self.expert_tabs.addTab(self.gcode_group, "G-Code")
        self.expert_tabs.addTab(self.console_log_panel, "Log")
        self.diagnostics_group = QGroupBox("Diagnose / Expertenansicht")
        self.diagnostics_group.setCheckable(True)
        self.diagnostics_group.setChecked(False)
        diagnostics_layout = QVBoxLayout(self.diagnostics_group)
        diagnostics_layout.addWidget(self.expert_tabs)
        self.expert_tabs.setVisible(False)
        self.diagnostics_group.toggled.connect(self.expert_tabs.setVisible)
        right_layout.addWidget(self.diagnostics_group)
        right_layout.addStretch(1)

    def _build_status_bar(self, layout: QVBoxLayout) -> None:
        self.status_panel = StatusPanel()
        self.job_status = self.status_panel.job_status
        self.progress = self.status_panel.progress
        self.status = self.status_panel.status
        layout.addWidget(self.status_panel)
        self._apply_theme(self.dark_mode_enabled)

    def _button(self, text: str, handler: Callable) -> QPushButton:
        button = QPushButton(text)
        button.setToolTip(text)
        button.clicked.connect(handler)
        button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return button

    def _machine_action_button(self, action_id: str, source: str) -> QPushButton:
        definition = self.machine_action_registry.get(action_id)
        button = QPushButton(definition.label)
        button.setObjectName(f"machineAction_{action_id}")
        button.setToolTip(definition.tooltip)
        if action_id in {"toggle_alignment", "toggle_work_area_trace"}:
            button.setCheckable(True)
        if action_id == "toggle_alignment":
            self.alignment_button = button
        if action_id == "toggle_work_area_trace":
            self.work_area_trace_button = button
        button.clicked.connect(lambda _checked=False, item=action_id, origin=source: self._trigger_machine_action(item, origin))
        if action_id == "emergency_stop":
            button.setMinimumHeight(42)
        elif action_id in {"start_job", "stop", "frame", "dry_run"}:
            button.setMinimumHeight(36)
        else:
            button.setMinimumHeight(32)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.action_buttons.setdefault(action_id, []).append(button)
        return button

    def _configure_sidebar_combo(self, combo: QComboBox) -> None:
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumWidth(0)
        combo.view().setMinimumWidth(320)
        if hasattr(self, "sidebar_combos"):
            self.sidebar_combos.append(combo)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._sync_sidebar_popup_widths()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._closing = True
        try:
            self.app_controller.shutdown_controller()
            for thread in list(self._worker_threads):
                thread.join(timeout=1.0)
        finally:
            super().closeEvent(event)

    def _sync_sidebar_popup_widths(self) -> None:
        if not hasattr(self, "sidebar_combos"):
            return
        width = max(320, self.left_sidebar.width() - 24)
        for combo in self.sidebar_combos:
            combo.view().setMinimumWidth(width)

    def _spin(self, minimum: int, maximum: int, value: int, step: int = 1, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _double_spin(self, minimum: float, maximum: float, value: float, suffix: str = "") -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        spin.setValue(value)
        if suffix:
            spin.setSuffix(suffix)
        return spin

    def _fit_gcode_panel_to_text(self) -> None:
        if not hasattr(self, "gcode_group"):
            return
        lines = self.gcode_text.toPlainText().splitlines() or [""]
        metrics = self.gcode_text.fontMetrics()
        longest_line_width = max(metrics.horizontalAdvance(line) for line in lines)
        scrollbar_width = self.gcode_text.verticalScrollBar().sizeHint().width()
        target_width = longest_line_width + scrollbar_width + 72
        target_width = max(360, min(620, target_width))
        self.gcode_group.setMinimumWidth(target_width)
        self.gcode_group.setMaximumWidth(target_width)

    def _settings_changed(self) -> None:
        if hasattr(self, "app_controller") and hasattr(self, "work_width") and hasattr(self, "work_height"):
            self.app_controller.set_current_workspace(self.work_width.value(), self.work_height.value())
        if self.original_imported_paths:
            self._apply_svg_placement()
        elif self.original_raster_source is not None:
            fitted_source = self._fit_raster_source(self.original_raster_source)
            self.raster_sources = [fitted_source]
            self.artwork_source = fitted_source
            self._set_svg_size_label(fitted_source.width_mm, fitted_source.height_mm, source_label=f"Raster: {fitted_source.file_name}")
            self._refresh_gcode()
            self._draw_preview()
        else:
            self._refresh_gcode()
            self._draw_preview()

    def _profile_selected(self) -> None:
        self._ensure_profile_modes(self.profile_name.currentText())
        self._apply_mode_profile_to_controls()
        self._parameter_source = "Materialprofil/Default"
        self._sync_layers_from_controls(preserve_states=True, preserve_parameters=False)
        self._settings_changed()

    def _material_settings_changed(self) -> None:
        profile = self._selected_profile()
        self._parameter_source = "manuell"
        self._upsert_profile(profile)
        self._sync_layers_from_controls(preserve_states=True, preserve_parameters=False)
        self._settings_changed()

    def _layer_changed(self) -> None:
        self._parameter_source = "manuell/Layer"
        self._refresh_gcode()
        self._draw_preview()
        self._update_job_summary()
        self._update_assistant_panel()

    def _sync_layers_from_controls(self, preserve_states: bool = True, preserve_parameters: bool = True) -> None:
        if not hasattr(self, "layer_panel"):
            return
        next_layers = build_default_layers(self._selected_profile(), self.operation_mode.currentText())
        if getattr(self, "raster_sources", []):
            raster_name = f"Raster: {self.raster_sources[0].file_name}"
            for layer in next_layers:
                if layer.layer_type == LayerType.ENGRAVE:
                    layer.name = raster_name
                    layer.enabled = True
                    layer.visible = True
                elif layer.layer_type == LayerType.CUT:
                    layer.enabled = False
        if preserve_states:
            current_by_type = {layer.layer_type: layer for layer in self.layer_panel.layers()}
            for layer in next_layers:
                current = current_by_type.get(layer.layer_type)
                if current is not None:
                    layer.visible = current.visible
                    layer.enabled = current.enabled
                    layer.order = current.order
                    layer.mode = current.mode
                    layer.fill_spacing_mm = current.fill_spacing_mm
                    layer.fill_angle_deg = current.fill_angle_deg
                    layer.overscan_enabled = current.overscan_enabled
                    layer.overscan_mode = current.overscan_mode
                    layer.overscan_mm = current.overscan_mm
                    if preserve_parameters:
                        layer.speed_mm_min = current.speed_mm_min
                        layer.power_percent = current.power_percent
                        layer.passes = current.passes
        self.layer_panel.set_layers(next_layers)

    def _current_layers(self):
        if hasattr(self, "layer_panel"):
            return self.layer_panel.layers()
        return build_default_layers(self._selected_profile(), self.operation_mode.currentText())

    def _effective_job_profile(self) -> MaterialProfile:
        profile = self._selected_profile()
        layers = active_output_layers(self._current_layers())
        if not layers:
            return profile
        primary_layer = layers[0]
        return MaterialProfile(
            profile.name,
            primary_layer.power_percent,
            primary_layer.speed_mm_min,
            primary_layer.passes,
            primary_layer.layer_type.value,
            profile.notes,
        )

    def _switch_controller(self, *_args) -> None:
        self.controller = self.app_controller.switch_controller(self.connection_mode.currentText())
        self.active_connection_mode = self.connection_mode.currentText()
        self._sync_connection_indicator()

    def _current_controller(self):
        if self.active_connection_mode != self.connection_mode.currentText():
            self._switch_controller()
        self.controller = self.app_controller.current_controller(self.connection_mode.currentText())
        return self.controller

    def _refresh_ports(self) -> None:
        ports = list_serial_ports()
        self.serial_port.clear()
        self.serial_port.addItems(ports)
        if ports:
            default_port = getattr(self.machine_profile, "default_port", "")
            index = self.serial_port.findText(default_port) if default_port else -1
            self.serial_port.setCurrentIndex(index if index >= 0 else 0)
        self.log(f"{len(ports)} COM-Port(s) gefunden." if ports else "Keine COM-Ports gefunden.")

    def _auto_detect_laser(self) -> None:
        self.log("Suche Laser an COM-Ports...")
        self._set_progress("Laser suchen", 0, 1)

        def detect() -> None:
            candidate = find_laser_port()
            if candidate is None:
                self.signals.error.emit("Kein passender Laser-Port gefunden.")
                return
            self.signals.log.emit(f"Laser-Port gefunden: {candidate.label} ({candidate.reason})")
            self.signals.port_detected.emit(candidate.label)
            self.signals.progress.emit("Bereit", 1, 1)

        self._run_worker(detect)

    def _apply_detected_port(self, port_label: str) -> None:
        self.connection_mode.setCurrentText("GRBL ueber USB")
        self._refresh_ports()
        index = self.serial_port.findText(port_label)
        if index < 0:
            self.serial_port.addItem(port_label)
            index = self.serial_port.findText(port_label)
        self.serial_port.setCurrentIndex(index)
        self.log(f"COM-Port automatisch ausgewaehlt: {port_label}")

    def _machine_profile_changed(self, profile_id: str) -> None:
        if not self._can_change_machine_profile(profile_id):
            self.machine_panel.set_machine_profiles(
                self.machine_profile_repository.profiles(),
                self.machine_profile_repository.active_profile_id(),
            )
            return
        previous = self.machine_profile
        self.machine_profile = self.machine_profile_repository.set_active_profile(profile_id)
        self._apply_machine_profile(self.machine_profile)
        self.log(f"Maschinenprofil gewechselt: {previous.name} -> {self.machine_profile.name}")
        self.workflow.record_action(
            "Maschinenprofil gewechselt",
            MachineLogStatus.INFO,
            (
                f"profil={self.machine_profile.profile_id}; "
                f"baudrate={self.machine_profile.baudrate}; "
                f"arbeitsbereich={self.machine_profile.work_area_width:.1f}x{self.machine_profile.work_area_height:.1f}; "
                f"homing_required={self.machine_profile.homing_required}"
            ),
        )

    def _edit_machine_profiles(self) -> None:
        raw_state = getattr(self.app_controller.controller, "state", None)
        if getattr(raw_state, "connected", False) or self.app_controller.machine_state.connected:
            self._block_machine_profile_change("__profile_editor__", self.app_controller.machine_state.phase.value)
            return
        dialog = MachineProfileDialog(
            self.machine_profile_repository.profiles(),
            self.machine_profile_repository.active_profile_id(),
            self._log_profile_validation_failed,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted or dialog.saved_profile is None:
            return

        profile = dialog.saved_profile
        try:
            self.machine_profile_repository.upsert_profile(profile)
            self.machine_profile = self.machine_profile_repository.set_active_profile(profile.profile_id)
        except ValueError as exc:
            message = str(exc)
            self._log_profile_validation_failed(message)
            QMessageBox.warning(self, "Profil konnte nicht gespeichert werden", message)
            return

        self.machine_panel.set_machine_profiles(
            self.machine_profile_repository.profiles(),
            self.machine_profile_repository.active_profile_id(),
        )
        self._apply_machine_profile(self.machine_profile)
        action = "Maschinenprofil erstellt" if dialog.is_new_profile else "Maschinenprofil bearbeitet"
        self.log(f"{action}: {self.machine_profile.name}")
        self.workflow.record_action(
            action,
            MachineLogStatus.OK,
            (
                f"profil={self.machine_profile.profile_id}; "
                f"baudrate={self.machine_profile.baudrate}; "
                f"homing_required={self.machine_profile.homing_required}"
            ),
        )

    def _log_profile_validation_failed(self, message: str) -> None:
        self.log(f"Maschinenprofil ungueltig: {message}")
        self.workflow.record_action("Maschinenprofil ungueltig", MachineLogStatus.ERROR, message)

    def _can_change_machine_profile(self, requested_profile_id: str) -> bool:
        current_id = self.machine_profile_repository.active_profile_id()
        if requested_profile_id == current_id:
            return True
        raw_state = getattr(self.app_controller.controller, "state", None)
        if getattr(raw_state, "connected", False):
            return self._block_machine_profile_change(requested_profile_id, self.app_controller.machine_state.phase.value)
        self.app_controller.sync_from_controller()
        state = self.app_controller.machine_state
        if state.connected:
            return self._block_machine_profile_change(requested_profile_id, state.phase.value)
        return True

    def _block_machine_profile_change(self, requested_profile_id: str, phase: str) -> bool:
        message = (
            "Maschinenprofilwechsel ist nur im getrennten Zustand erlaubt. "
            "Bitte Verbindung trennen, Profil wechseln und neu verbinden."
        )
        self.log(message)
        self.workflow.record_action(
            "Maschinenprofilwechsel blockiert",
            MachineLogStatus.WARNING,
            f"profil={requested_profile_id}; zustand={phase}; ergebnis=blockiert",
        )
        QMessageBox.warning(self, "Profilwechsel blockiert", message)
        return False

    def _apply_machine_profile(self, profile: MachineProfile) -> None:
        self.app_controller.set_machine_profile(profile)
        if hasattr(self, "connection_mode"):
            self.connection_mode.setCurrentText(profile.controller_type)
        if hasattr(self, "work_width"):
            self.work_width.setValue(profile.work_area_width)
            self.work_height.setValue(profile.work_area_height)
        if profile.default_port and hasattr(self, "serial_port"):
            index = self.serial_port.findText(profile.default_port)
            if index >= 0:
                self.serial_port.setCurrentIndex(index)
        self._refresh_gcode()
        self._draw_preview()
        self._update_material_summary()
        self._update_workflow_status()

    def _query_status(self) -> None:
        controller = self._current_controller()
        self._run_worker(lambda: self.app_controller.get_status() if hasattr(controller, "get_status") else None)

    def _query_settings(self) -> None:
        controller = self._current_controller()
        if hasattr(controller, "query_settings"):
            self._run_worker(lambda: self.workflow.run_machine_action("GRBL Settings", self.app_controller.query_settings))
        else:
            self.log("GRBL Settings nur im USB-Modus verfuegbar.")

    def _open_transform_dialog(self) -> None:
        previous_transform = self.artwork_transform
        previous_auto_mode = self.svg_auto.isChecked()
        dialog = QDialog(self)
        dialog.setWindowTitle("Motiv transformieren")
        dialog_layout = QVBoxLayout(dialog)
        self.transform_body.setParent(dialog)
        self.transform_body.setVisible(True)
        dialog_layout.addWidget(self.transform_body)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        apply_button = QPushButton("Uebernehmen")
        cancel_button = QPushButton("Abbrechen")
        apply_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        button_row.addWidget(apply_button)
        button_row.addWidget(cancel_button)
        dialog_layout.addLayout(button_row)
        self._active_transform_dialog = dialog
        try:
            result = dialog.exec()
            if result != QDialog.DialogCode.Accepted and previous_transform is not None:
                self.svg_auto.blockSignals(True)
                self.svg_manual.blockSignals(True)
                self.svg_auto.setChecked(previous_auto_mode)
                self.svg_manual.setChecked(not previous_auto_mode)
                self.svg_auto.blockSignals(False)
                self.svg_manual.blockSignals(False)
                self._commit_artwork_transform(previous_transform)
        finally:
            self.transform_body.setParent(self.transform_group)
            self.transform_group.layout().addWidget(self.transform_body)
            self.transform_body.setVisible(False)
            self._active_transform_dialog = None

    def _open_add_material_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Material hinzufuegen")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name = QLineEdit()
        material_type = QLineEdit()
        thickness = QDoubleSpinBox()
        thickness.setRange(0.0, 200.0)
        thickness.setSuffix(" mm")
        speed = self._spin(1, 200000, self.speed_mm_min.value(), 50, " mm/min")
        power = self._spin(0, 100, self.power_percent.value(), suffix=" %")
        passes = self._spin(1, 100, self.passes.value(), suffix=" x")
        mode = QComboBox()
        mode.addItems(["Gravur", "Schnitt", "Markierung"])
        notes = QLineEdit()
        form.addRow("Materialname", name)
        form.addRow("Materialtyp", material_type)
        form.addRow("Staerke", thickness)
        form.addRow("Geschwindigkeit", speed)
        form.addRow("Laserleistung", power)
        form.addRow("Durchgaenge", passes)
        form.addRow("Modus", mode)
        form.addRow("Notizen", notes)
        layout.addLayout(form)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        save_button = QPushButton("Speichern")
        cancel_button = QPushButton("Abbrechen")
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)
        cancel_button.clicked.connect(dialog.reject)

        def save() -> None:
            try:
                self._save_new_material_profile(
                    name.text(),
                    material_type.text(),
                    thickness.value(),
                    speed.value(),
                    power.value(),
                    passes.value(),
                    mode.currentText(),
                    notes.text(),
                )
            except ValueError as exc:
                QMessageBox.warning(dialog, "Material hinzufuegen", str(exc))
                return
            dialog.accept()

        save_button.clicked.connect(save)
        dialog.exec()

    def _save_new_material_profile(
        self,
        name: str,
        material_type: str,
        thickness_mm: float,
        speed_mm_min: int,
        power_percent: int,
        passes: int,
        mode_label: str,
        notes: str = "",
    ) -> MaterialProfile:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Materialname darf nicht leer sein.")
        if thickness_mm < 0:
            raise ValueError("Materialstaerke darf nicht negativ sein.")
        if speed_mm_min <= 0:
            raise ValueError("Geschwindigkeit muss groesser als 0 sein.")
        if power_percent < 0 or power_percent > 100:
            raise ValueError("Laserleistung muss zwischen 0 und 100 Prozent liegen.")
        if passes < 1:
            raise ValueError("Durchgaenge muessen mindestens 1 sein.")
        valid_modes = {"Gravur", "Schnitt", "Markierung"}
        layer_type = mode_label.strip() or "Gravur"
        if layer_type not in valid_modes:
            raise ValueError("Modus muss Gravur, Schnitt oder Markierung sein.")
        details = []
        if material_type.strip():
            details.append(f"Typ: {material_type.strip()}")
        if thickness_mm > 0:
            details.append(f"Staerke: {thickness_mm:.2f} mm")
        if notes.strip():
            details.append(notes.strip())
        operation_mode = CUT_MODE if layer_type == "Schnitt" else ENGRAVE_MODE
        existing = clean_name in self.profile_service.names()
        profile = MaterialProfile(
            clean_name,
            int(power_percent),
            int(speed_mm_min),
            int(passes),
            layer_type,
            " | ".join(details),
            material_type.strip(),
            float(thickness_mm) if thickness_mm > 0 else None,
        )
        try:
            self.profile_service.upsert_mode_profile(profile, operation_mode)
        except OSError as exc:
            self.log(f"Materialspeicherung fehlgeschlagen: {exc}")
            raise ValueError(f"Material konnte nicht gespeichert werden: {exc}") from exc
        self.log(f"Materialprofil JSON aktualisiert: {self.profile_service.storage_path}")
        self.profile_name.blockSignals(True)
        self.profile_name.clear()
        self.profile_name.addItems(self.profile_service.names())
        self.profile_name.setCurrentText(profile.name)
        self.profile_name.blockSignals(False)
        self.log(f"Materialliste nach Speichern neu geladen: {len(self.profile_service.names())} Profile.")
        self.log(f"Neues Material ausgewaehlt: {profile.name}")
        self._apply_mode_profile_to_controls()
        self._sync_layers_from_controls(preserve_states=False)
        self._settings_changed()
        action = "aktualisiert" if existing else "angelegt"
        self.log(f"Materialprofil {action}: {profile.name} ({layer_type}).")
        return profile

    def _frame_job(self) -> None:
        bounds = self.get_transformed_bounds()
        width = bounds.width_mm
        height = bounds.height_mm
        source_name = getattr(self.artwork_source, "file_name", "") if self.artwork_source else "Arbeitsbereich"
        frame_lines = [
            (bounds.min_x, bounds.min_y),
            (bounds.max_x, bounds.min_y),
            (bounds.max_x, bounds.max_y),
            (bounds.min_x, bounds.max_y),
            (bounds.min_x, bounds.min_y),
        ]
        self.log(
            "Frame-Datenquelle: "
            f"Motiv={source_name}; "
            f"transformed_bounds=({bounds.min_x:.2f}, {bounds.min_y:.2f}, {bounds.max_x:.2f}, {bounds.max_y:.2f}); "
            f"Arbeitsbereich={self.work_width.value():.2f} x {self.work_height.value():.2f} mm; "
            "Frame-Koordinaten="
            + " -> ".join(f"X{x:.2f} Y{y:.2f}" for x, y in frame_lines)
        )
        self._run_worker(
            lambda: self.workflow.run_machine_action(
                "Frame gestartet",
                lambda: self.app_controller.frame_job(width, height, bounds.min_x, bounds.min_y),
                "Frame abgeschlossen",
            )
        )

    def _job_context(self, controller, gcode: str) -> JobContext:
        transform = self.artwork_transform
        bounds_ok = None
        transformed_bounds = self.get_transformed_bounds()
        if self.imported_paths or self.raster_sources or transform is not None:
            bounds_ok = transformed_bounds.within(self.work_width.value(), self.work_height.value())
        if self.laser_project.items:
            bounds_ok = transformed_bounds.within(self.work_width.value(), self.work_height.value())
        active_items = [item for item in self.laser_project.items if item.active]
        source_name = getattr(self.artwork_source, "file_name", "") if self.artwork_source else ""
        source_type = getattr(self.artwork_source, "source_type", "").value if self.artwork_source else ""
        if self.laser_project.items:
            source_name = ", ".join(item.name for item in active_items) or "Keine aktiven Motive"
            source_type = "multi"
        machine_state = self.app_controller.machine_state
        svg_warnings = self._svg_preflight_warnings()
        return JobContext(
            controller=controller,
            connection_mode=self.connection_mode.currentText(),
            selected_port=self.serial_port.currentText(),
            machine_label=controller.__class__.__name__,
            work_width_mm=self.work_width.value(),
            work_height_mm=self.work_height.value(),
            material_profile=self._effective_job_profile(),
            operation_mode=self.operation_mode.currentText(),
            origin_label=self.job_origin.currentText() if hasattr(self, "job_origin") else JOB_ORIGIN_LOWER_LEFT,
            gcode=gcode,
            layers=self._current_layers(),
            parameter_source=self._parameter_source,
            alignment_mode_active=self.app_controller.is_alignment_mode_active(),
            extra_warnings=self._material_shape_warnings()
            + svg_warnings
            + ([f"Aktive Motive: {len(active_items)} von {len(self.laser_project.items)}"] if self.laser_project.items else []),
            machine_phase=self.app_controller.machine_state.phase.value,
            machine_profile_name=self.machine_profile.machine_name,
            homing_required=self.machine_profile.homing_required,
            allow_unhomed_start=not self.machine_profile.homing_required,
            homing_warning=self.machine_profile.allow_start_without_homing_warning,
            max_speed=self.machine_profile.max_speed,
            max_power=self.machine_profile.max_power,
            source_name=source_name,
            source_type=source_type,
            raster_gcode_available=not any(item.active and item.is_raster for item in self.laser_project.items) and not bool(self.raster_sources),
            autofit_applied=bool(self.autofit_result and self.autofit_result.applied),
            source_original_width_mm=self.autofit_result.original_width_mm if self.autofit_result else None,
            source_original_height_mm=self.autofit_result.original_height_mm if self.autofit_result else None,
            source_current_width_mm=transformed_bounds.width_mm if self.laser_project.items else (transform.current_width_mm if transform else (self.autofit_result.current_width_mm if self.autofit_result else None)),
            source_current_height_mm=transformed_bounds.height_mm if self.laser_project.items else (transform.current_height_mm if transform else (self.autofit_result.current_height_mm if self.autofit_result else None)),
            source_x_mm=transformed_bounds.min_x if (transform or self.laser_project.items) else None,
            source_y_mm=transformed_bounds.min_y if (transform or self.laser_project.items) else None,
            source_bounds_ok=bounds_ok,
            autofit_scale_percent=transform.scale_percent if transform else (self.autofit_result.scale_percent if self.autofit_result else None),
            autofit_position=transform.position_label if transform else (self.autofit_result.position if self.autofit_result else ""),
            head_x_mm=machine_state.x_mm if machine_state.position_source else None,
            head_y_mm=machine_state.y_mm if machine_state.position_source else None,
            head_position_source=machine_state.position_source,
            fill_toolpaths=list(self.fill_toolpaths),
            job_kind=self.job_kind.currentText() if hasattr(self, "job_kind") else "Einzelstueck",
            auto_home_after_success=bool(
                self.auto_home_after_job.isChecked() if hasattr(self, "auto_home_after_job") else False
            ),
            active_artwork_count=len(active_items) if self.laser_project.items else None,
        )

    def _start_job(self) -> None:
        controller = self._current_controller()
        try:
            self.app_controller.ensure_alignment_laser_off("Preflight/Jobstart")
        except Exception as exc:
            self.log(str(exc))
            QMessageBox.critical(self, "Ausrichtmodus", f"Laserpunkt konnte nicht sicher ausgeschaltet werden:\n{exc}")
            self._sync_connection_indicator()
            return
        width = self.work_width.value()
        height = self.work_height.value()
        profile = self._effective_job_profile()
        gcode = self.gcode_text.toPlainText().strip()
        preflight = self.workflow.prepare_preflight(self._job_context(controller, gcode))
        if preflight.prepared is None:
            message = "\n".join(preflight.blockers) or "Der Job konnte nicht vorbereitet werden."
            if self.connection_mode.currentText() == "GRBL ueber USB":
                PreflightDialog(preflight, self).exec()
                return
            QMessageBox.critical(self, "Preflight fehlgeschlagen", message)
            return
        prepared = preflight.prepared

        controller_name = controller.__class__.__name__
        mode_label = self._operation_mode_label()
        mode_laser = self.workflow.laser_mode_label(self.operation_mode.currentText())
        self._show_job_analysis(prepared)
        self.last_prepared_job = prepared
        self._update_assistant_panel(prepared)

        if self.connection_mode.currentText() != "GRBL ueber USB":
            confirmed = QMessageBox.question(
                self,
                "Simulator-Modus",
                "Die App ist im Simulator-Modus.\n\n"
                "Der Job wird nicht an den Laser gesendet.\n"
                f"Auswahl: {mode_label}\n"
                f"Laser-Modus: {mode_laser}\n"
                f"Leistung: {profile.power_percent}%\n"
                f"Geschwindigkeit: {profile.speed_mm_min} mm/min\n"
                f"Durchgaenge: {profile.passes}\n"
                f"G-Code-Zeilen: {len(prepared.commands)}\n"
                f"Geschaetzte Laufzeit: {prepared.analysis.estimated_runtime_label}\n"
                "Soll die Simulation gestartet werden?",
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                self.log("Simulation abgebrochen.")
                return
        else:
            dialog = PreflightDialog(preflight, self)
            if not preflight.can_start:
                dialog.exec()
                return
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.log("Jobstart abgebrochen.")
                self.workflow.record_action("Jobstart abgebrochen", MachineLogStatus.WARNING)
                return
            self.workflow.record_action("Preflight bestaetigt", MachineLogStatus.OK, "Hardwarestart freigegeben.")
            if preflight.requires_unhomed_confirmation:
                self.workflow.record_action(
                    "Start ohne Homing bestaetigt",
                    MachineLogStatus.WARNING,
                    f"Profil={self.machine_profile.machine_name}; homing_required={self.machine_profile.homing_required}",
                )

        self.log(f"Start-Controller: {controller_name} ({mode_label})")
        self._log_job_diagnostics(prepared, controller_name, mode_label, mode_laser)

        self._run_worker(
            lambda: self.workflow.run_machine_action(
                "Job gestartet",
                lambda: self.app_controller.start_job(
                    gcode,
                    width,
                    height,
                    preflight_confirmed=self.connection_mode.currentText() == "GRBL ueber USB",
                    auto_home_after_success=self.auto_home_after_job.isChecked(),
                    job_kind=self.job_kind.currentText(),
                ),
                "Job abgeschlossen",
            )
        )

    def _dry_run_job(self) -> None:
        controller = self._current_controller()
        try:
            self.app_controller.ensure_alignment_laser_off("Preflight/Dry Run")
        except Exception as exc:
            self.log(str(exc))
            QMessageBox.critical(self, "Ausrichtmodus", f"Laserpunkt konnte nicht sicher ausgeschaltet werden:\n{exc}")
            self._sync_connection_indicator()
            return
        width = self.work_width.value()
        height = self.work_height.value()
        gcode = self.gcode_text.toPlainText().strip()
        try:
            dry_run_gcode = "\n".join(self.job_service.prepare_dry_run(gcode, width, height).commands)
        except ValueError as exc:
            self.log(str(exc))
            QMessageBox.critical(self, "Dry Run nicht moeglich", str(exc))
            return

        if self.connection_mode.currentText() == "GRBL ueber USB":
            preflight = self.workflow.prepare_preflight(self._job_context(controller, dry_run_gcode))
            dialog = PreflightDialog(preflight, self)
            if not preflight.can_start:
                dialog.exec()
                return
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.log("Dry Run abgebrochen.")
                self.workflow.record_action("Dry Run abgebrochen", MachineLogStatus.WARNING)
                return
            self.workflow.record_action("Preflight bestaetigt", MachineLogStatus.OK, "Hardware-Dry-Run freigegeben.")
            if preflight.requires_unhomed_confirmation:
                self.workflow.record_action(
                    "Start ohne Homing bestaetigt",
                    MachineLogStatus.WARNING,
                    f"Profil={self.machine_profile.machine_name}; homing_required={self.machine_profile.homing_required}",
                )

        self.log(f"Dry Run Start-Controller: {controller.__class__.__name__} ({self._operation_mode_label()})")
        self.workflow.record_action("Dry Run vorbereitet", MachineLogStatus.INFO, "Laser aus")
        dry_run_prepared = self.job_service.prepare_dry_run(gcode, width, height)
        dry_run_prepared.warnings.extend(self._material_shape_warnings())
        self._log_job_diagnostics(
            dry_run_prepared,
            controller.__class__.__name__,
            f"Dry Run {self._operation_mode_label()}",
            "Laser aus",
        )

        self._run_worker(
            lambda: self.workflow.run_machine_action(
                "Dry Run gestartet",
                lambda: self.app_controller.start_job(
                    dry_run_gcode,
                    width,
                    height,
                    "Dry Run",
                    preflight_confirmed=self.connection_mode.currentText() == "GRBL ueber USB",
                    auto_home_after_success=self.auto_home_after_job.isChecked(),
                    job_kind=self.job_kind.currentText(),
                ),
                "Dry Run abgeschlossen",
            )
        )

    def _hardware_preflight_ok(self, controller) -> bool:
        warnings = self.job_service.hardware_preflight_warnings(controller, self.serial_port.currentText())
        if warnings:
            message = "\n".join(f"- {item}" for item in warnings)
            self.log(message)
            QMessageBox.critical(self, "Preflight fehlgeschlagen", message)
            return False
        return True

    def _confirm_warnings(self, warnings: list[str]) -> bool:
        warning_text = "\n".join(f"- {item}" for item in warnings)
        result = QMessageBox.question(
            self,
            "Preflight-Warnungen",
            "Bitte pruefe diese Punkte vor dem Start:\n\n"
            f"{warning_text}\n\n"
            "Nur fortsetzen, wenn Material, Fokus, Air Assist, Absaugung und Schutzbrille vorbereitet sind.",
        )
        return result == QMessageBox.StandardButton.Yes

    def _show_job_analysis(self, prepared: JobPreparation) -> None:
        analysis = prepared.analysis
        bounds = "keine Pfadgrenzen"
        if analysis.has_bounds:
            bounds = (
                f"X {analysis.min_x:.1f}..{analysis.max_x:.1f} mm, "
                f"Y {analysis.min_y:.1f}..{analysis.max_y:.1f} mm"
            )
        self.log(
            "Jobanalyse: "
            f"{len(prepared.commands)} Zeilen, "
            f"{analysis.movement_count} Bewegungen, "
            f"{analysis.laser_command_count} Laserbefehle, "
            f"{bounds}, "
            f"ca. {analysis.estimated_runtime_label}."
        )

    def _material_shape_warnings(self) -> list[str]:
        if not hasattr(self, "material_shape") or self.material_shape.currentText() != MATERIAL_SHAPE_CIRCLE:
            return []
        width = self.work_width.value()
        height = self.work_height.value()
        if abs(width - height) <= 0.1:
            return []
        diameter = min(width, height)
        return [f"Kreis-Material nutzt den kleineren Durchmesser {diameter:.1f} mm aus {width:.1f} x {height:.1f} mm."]

    def _log_job_diagnostics(
        self,
        prepared: JobPreparation,
        controller_name: str,
        mode_label: str,
        mode_laser: str,
    ) -> None:
        profile = self._selected_profile()
        analysis = prepared.analysis
        self.diagnostic_log.job("=== JOB VORBEREITET ===")
        self.diagnostic_log.job(f"Controller: {controller_name}")
        self.diagnostic_log.job(f"Verbindungsmodus: {self.connection_mode.currentText()}")
        self.diagnostic_log.job(f"Port: {self.serial_port.currentText()}")
        self.diagnostic_log.job(f"Operation: {mode_label}, Laser-Modus: {mode_laser}")
        self.diagnostic_log.job(
            f"Material: {profile.name}, Arbeitsbereich: {self.work_width.value():.1f} x {self.work_height.value():.1f} mm"
        )
        self.diagnostic_log.job(
            f"Profil: {profile.power_percent}% Leistung, {profile.speed_mm_min} mm/min, {profile.passes} Durchgaenge"
        )
        active_layers = active_output_layers(self._current_layers())
        for layer in active_layers:
            source = "manuell/Layer" if (
                self._parameter_source.startswith("manuell")
                or
                layer.power_percent != profile.power_percent
                or layer.speed_mm_min != profile.speed_mm_min
                or layer.passes != profile.passes
            ) else "Materialprofil/Default"
            self.diagnostic_log.job(
                "Aktiver Layer: "
                f"{layer.name} ({layer.layer_type.value}) "
                f"Power {layer.power_percent}% Speed {layer.speed_mm_min} mm/min "
                f"Passes {layer.passes} Quelle {source}"
            )
        if analysis.max_feed_mm_min is not None or analysis.laser_power_values:
            self.diagnostic_log.job(
                "G-Code-Parameter: "
                f"max F {analysis.max_feed_mm_min or 0:.0f} mm/min, "
                f"max S {max(analysis.laser_power_values) if analysis.laser_power_values else 0:.0f}"
            )
        self.diagnostic_log.job(
            f"SVG-Platzierung: {self._svg_placement_data() if hasattr(self, 'svg_auto') else {}}"
        )
        if hasattr(self, "svg_size_label"):
            self.diagnostic_log.job(self.svg_size_label.text())
        if analysis.has_bounds:
            self.diagnostic_log.job(
                f"G-Code-Pfad: X {analysis.min_x:.3f}..{analysis.max_x:.3f} mm, "
                f"Y {analysis.min_y:.3f}..{analysis.max_y:.3f} mm, "
                f"Groesse {analysis.width_mm:.3f} x {analysis.height_mm:.3f} mm"
            )
        self.diagnostic_log.job(
            f"G-Code-Zeilen: {len(prepared.commands)}, Bewegungen: {analysis.movement_count}, "
            f"Laserbefehle: {analysis.laser_command_count}, Laufzeit ca. {analysis.estimated_runtime_label}"
        )
        for warning in prepared.warnings:
            self.diagnostic_log.job(f"Warnung: {warning}")

    def _has_loaded_motif(self) -> bool:
        return bool(
            self.imported_paths
            or self.original_imported_paths
            or self.raster_sources
            or self.laser_project.items
            or self.artwork_source is not None
        )

    def _sync_contextual_controls(self) -> None:
        has_motif = self._has_loaded_motif()
        if hasattr(self, "transform_group"):
            self.transform_group.setEnabled(has_motif)
            self.transform_group.setToolTip("" if has_motif else "Motiv importieren, bevor Transformationen verfuegbar sind.")
        if hasattr(self, "layer_panel"):
            self.layer_panel.setEnabled(has_motif)
            self.layer_panel.setToolTip("" if has_motif else "Layer werden nach dem Motivimport bearbeitbar.")

    def _update_job_summary(self) -> None:
        if not hasattr(self, "job_summary"):
            return
        self._update_material_summary()
        self._sync_contextual_controls()
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._selected_profile(),
                self.operation_mode.currentText(),
            )
        except ValueError as exc:
            active_raster_items = [item for item in self.laser_project.items if item.active and item.is_raster]
            if self.raster_sources or active_raster_items:
                self.job_summary.setText("Rasterbild importiert | Rastergravur-GCode noch nicht verfuegbar | Hardwarestart blockiert")
            else:
                self.job_summary.setText(f"G-Code: {exc}")
            if hasattr(self, "project_summary"):
                job_text = "Rasterquelle importiert" if self.raster_sources or active_raster_items else "keine gueltigen Jobdaten"
                if self.raster_sources:
                    source = self.raster_sources[0]
                    job_text = f"Raster: {source.width_mm:.1f} x {source.height_mm:.1f} mm | Preflight: blockiert"
                elif active_raster_items:
                    source_item = active_raster_items[0]
                    job_text = f"Raster: {source_item.transform.current_width_mm:.1f} x {source_item.transform.current_height_mm:.1f} mm | Preflight: blockiert"
                elif not self._has_loaded_motif():
                    job_text = "Noch keine Motive vorhanden. Jetzt erstes Motiv importieren."
                self.project_summary.setText(
                    f"Projekt: {self.machine_profile.name} | {self.profile_name.currentText()} | {job_text}"
                )
            self.job_summary.setText(f"{self.job_summary.text()} | Naechster Schritt: {self._next_workflow_step(None)}")
            self._update_workflow_status()
            return
        prepared.warnings.extend(self._material_shape_warnings())
        layer_count = len([layer for layer in self._current_layers() if layer.is_output_layer])
        analysis = prepared.analysis
        warning_count = len(prepared.warnings)
        warning_text = f" | Warnungen: {warning_count}" if warning_count else ""
        bounds = ""
        if analysis.has_bounds:
            bounds = f" | Pfad: {analysis.width_mm:.1f} x {analysis.height_mm:.1f} mm"
        if not self._has_loaded_motif():
            self.job_summary.setText("Noch kein Motiv geladen. Naechster Schritt: Motiv importieren.")
        else:
            self.job_summary.setText(
                f"G-Code: {len(prepared.commands)} Zeilen | Bewegungen: {analysis.movement_count} "
                f"| Aktive Layer: {layer_count} | Laufzeit ca. {analysis.estimated_runtime_label}{bounds}{warning_text}"
            )
        if hasattr(self, "project_summary"):
            job_size = "Jobgroesse: nicht verfuegbar"
            if analysis.has_bounds:
                job_size = f"Jobgroesse: {analysis.width_mm:.1f} x {analysis.height_mm:.1f} mm"
            active_raster_items = [item for item in self.laser_project.items if item.active and item.is_raster]
            if self.laser_project.items:
                active_items = [item for item in self.laser_project.items if item.active]
                bounds = self.get_transformed_bounds()
                job_size = f"{len(active_items)} aktive Motive | Gesamt: {bounds.width_mm:.1f} x {bounds.height_mm:.1f} mm"
            if self.raster_sources:
                source = self.raster_sources[0]
                job_size = f"Raster: {source.width_mm:.1f} x {source.height_mm:.1f} mm"
            elif not self.imported_paths and not self.laser_project.items:
                job_size = "Noch keine Motive vorhanden. Jetzt erstes Motiv importieren."
            if self.raster_sources or active_raster_items or (not self.imported_paths and not self.laser_project.items) or not prepared.commands or not layer_count:
                preflight_state = "blockiert"
            elif warning_count:
                preflight_state = "mit Warnungen"
            else:
                preflight_state = "bereit zur Pruefung"
            self.project_summary.setText(
                f"Projekt: {self.machine_profile.name} | Material: {self.profile_name.currentText()} | "
                f"{job_size} | Layer aktiv: {layer_count} | Preflight: {preflight_state}"
            )
        self.last_prepared_job = prepared
        self._update_workflow_status(prepared)
        self._sync_machine_action_buttons()

    def _update_material_summary(self) -> None:
        if not hasattr(self, "material_summary"):
            return
        profile = self._selected_profile()
        notes = f" | Hinweis: {profile.notes}" if getattr(profile, "notes", "") else ""
        self.material_summary.setText(
            f"Material: {profile.name} | Speed {profile.speed_mm_min} mm/min | "
            f"Power {profile.power_percent}% | Passes {profile.passes}{notes}"
        )

    def _update_workflow_status(self, prepared: JobPreparation | None = None) -> None:
        if not hasattr(self, "workflow_status"):
            return
        state = self.app_controller.machine_state
        controller_state = getattr(self.app_controller.controller, "state", None)
        active_layers = [layer for layer in self._current_layers() if layer.is_output_layer]
        if prepared is None and hasattr(self, "gcode_text"):
            try:
                prepared = self.job_service.prepare_job(
                    self.gcode_text.toPlainText(),
                    self.work_width.value(),
                    self.work_height.value(),
                    self._effective_job_profile(),
                    self.operation_mode.currentText(),
                )
            except ValueError:
                prepared = None
        active_raster_items = [item for item in self.laser_project.items if item.active and item.is_raster]
        has_job = bool(self.imported_paths or self.raster_sources or self.laser_project.active_items)
        has_bounds = bool((self.imported_paths and prepared and prepared.analysis.has_bounds) or self.raster_sources or self.laser_project.active_items)
        homed = bool(getattr(controller_state, "homed", False))
        homing_ok = homed or not self.machine_profile.homing_required
        preflight_ready = bool(
            state.phase.value == "idle"
            and prepared is not None
            and prepared.commands
            and has_job
            and active_layers
            and has_bounds
            and not self.raster_sources
            and not active_raster_items
        )
        steps = [
            ("Maschine", state.connected),
            ("Homing", homing_ok),
            ("Material", bool(self.profile_name.currentText())),
            ("Datei/Job", has_job),
            ("Layer", bool(active_layers)),
            ("Vorschau", has_bounds),
            ("Frame", False),
            ("Preflight", preflight_ready),
            ("Start", preflight_ready),
        ]
        self.workflow_status.setText(
            "  |  ".join(f"{'[x]' if done else '[ ]'} {name}" for name, done in steps)
            + f"\nNaechster Schritt: {self._next_workflow_step(prepared)}"
        )

    def _update_assistant_panel(self, prepared: JobPreparation | None = None) -> None:
        if not hasattr(self, "assistant_summary"):
            return
        state = self.app_controller.machine_state
        active_layers = [layer for layer in self._current_layers() if layer.is_output_layer]
        checklist = [
            f"Maschine: {'verbunden' if state.connected else 'nicht verbunden'} ({state.phase.value})",
            f"Homing: {'erledigt' if getattr(getattr(self.app_controller, 'controller', None).state, 'homed', False) else ('optional laut Profil' if not self.machine_profile.homing_required else 'erforderlich')}",
            f"Profil: {self.machine_profile.name}",
            f"Material: {self.profile_name.currentText() if hasattr(self, 'profile_name') else '-'}",
            f"Aktive Layer: {len(active_layers)}",
        ]
        if not self.imported_paths and not self.raster_sources and not self.laser_project.items:
            checklist.append("Motiv: noch keine Datei geladen")
        if self.raster_sources or any(item.active and item.is_raster for item in self.laser_project.items):
            checklist.append("Quelle: Rasterbild (Raster-GCode noch nicht verfuegbar)")
        if prepared is None:
            try:
                prepared = self.job_service.prepare_job(
                    self.gcode_text.toPlainText(),
                    self.work_width.value(),
                    self.work_height.value(),
                    self._selected_profile(),
                    self.operation_mode.currentText(),
                )
            except ValueError as exc:
                checklist.append(f"Preflight: blockiert ({exc})")
                checklist.append(f"Naechster Schritt: {self._next_workflow_step(None)}")
                self._set_assistant_lines(checklist)
                return
        profile = self._selected_profile()
        advice = self.assistant_service.advise(
            profile.name,
            self.operation_mode.currentText(),
            profile,
            prepared.analysis,
            prepared.warnings,
            self.job_history,
        )
        has_artwork = bool(self.imported_paths or self.raster_sources or self.laser_project.active_items)
        has_active_raster = bool(self.raster_sources or any(item.active and item.is_raster for item in self.laser_project.items))
        preflight_hint = "Preflight: bereit" if has_artwork and active_layers and prepared.commands and not has_active_raster else "Preflight: pruefen"
        work_area_hint = "Arbeitsbereich: pruefen"
        if prepared.analysis.has_bounds:
            within_x = prepared.analysis.min_x >= 0 and prepared.analysis.max_x <= self.work_width.value()
            within_y = prepared.analysis.min_y >= 0 and prepared.analysis.max_y <= self.work_height.value()
            work_area_hint = "Arbeitsbereich: gueltig" if within_x and within_y else "Arbeitsbereich: ueberschritten"
        lines = checklist + [
            work_area_hint,
            preflight_hint,
            "Frame-Test: vor Hardwarestart empfohlen",
            f"Naechster Schritt: {self._next_workflow_step(prepared)}",
            "",
            f"Risiko: {advice.risk_label} ({advice.risk_score}/100)",
        ]
        lines.extend(f"- {item}" for item in advice.recommendations)
        if advice.matching_successes:
            lines.append(f"Gespeicherte gute Treffer: {len(advice.matching_successes)}")
        self._set_assistant_lines(lines)

    def _set_assistant_lines(self, lines: list[str]) -> None:
        rendered: list[str] = []
        for line in lines:
            escaped = (
                line.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            lowered = line.lower()
            if not line:
                rendered.append("<div style='height:4px'></div>")
                continue
            if any(word in lowered for word in ("blockiert", "ueberschritten", "erforderlich", "nicht verbunden")):
                icon, color = "&#9888;", "#c45a28"
            elif any(word in lowered for word in ("bereit", "gueltig", "verbunden", "erledigt", "optional")):
                icon, color = "&#10003;", "#2f7d4a"
            elif line.startswith("- "):
                icon, color = "&#8226;", "#777777"
            else:
                icon, color = "&#9675;", "#777777"
            rendered.append(
                f"<div style='margin:2px 0; color:{color};'><b>{icon}</b>&nbsp; {escaped}</div>"
            )
        self.assistant_summary.setHtml("".join(rendered))

    def _next_workflow_step(self, prepared: JobPreparation | None = None) -> str:
        state = self.app_controller.machine_state
        controller_state = getattr(self.app_controller.controller, "state", None)
        active_layers = [layer for layer in self._current_layers() if layer.is_output_layer]
        if not state.connected:
            return "Maschine verbinden."
        if self.machine_profile.homing_required and not getattr(controller_state, "homed", False):
            return "Homing / Referenzfahrt ausfuehren."
        if not self.profile_name.currentText():
            return "Materialprofil waehlen."
        if not self._has_loaded_motif():
            return "SVG, PNG oder JPG laden."
        if self.raster_sources or any(item.active and item.is_raster for item in self.laser_project.items):
            return "Rasterbild pruefen; echter Start ist blockiert, bis Raster-GCode verfuegbar ist."
        if not active_layers:
            return "Mindestens einen Ausgabelayer aktivieren."
        if prepared is None:
            try:
                prepared = self.job_service.prepare_job(
                    self.gcode_text.toPlainText(),
                    self.work_width.value(),
                    self.work_height.value(),
                    self._effective_job_profile(),
                    self.operation_mode.currentText(),
                )
            except ValueError:
                return "Jobdaten pruefen."
        if not prepared.analysis.has_bounds:
            return "Vorschau und Jobgrenzen pruefen."
        return "Frame-Test ausfuehren, danach Preflight bestaetigen."

    def _generate_test_matrix(self) -> None:
        profile = self._selected_profile()
        gcode = self.assistant_service.build_test_matrix_gcode(
            profile.name,
            self.operation_mode.currentText(),
            profile,
        )
        self.gcode_text.setPlainText(gcode)
        self.imported_paths = []
        self.original_imported_paths = []
        self.raster_sources = []
        self.artwork_source = None
        self.original_raster_source = None
        self.autofit_result = None
        self._draw_preview()
        self.log("Testmatrix erzeugt. Bitte zuerst Dry Run und dann auf Restmaterial testen.")

    def _record_job_result(self, result: str) -> None:
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._selected_profile(),
                self.operation_mode.currentText(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Job-Historie", str(exc))
            return
        note, ok = QInputDialog.getText(self, "Job-Historie", "Notiz zum Ergebnis:")
        if not ok:
            return
        profile = self._selected_profile()
        entry = JobHistoryEntry(
            timestamp=now_timestamp(),
            material_name=profile.name,
            operation_mode=self.operation_mode.currentText(),
            power_percent=profile.power_percent,
            speed_mm_min=profile.speed_mm_min,
            passes=profile.passes,
            work_width_mm=self.work_width.value(),
            work_height_mm=self.work_height.value(),
            command_count=len(prepared.commands),
            movement_count=prepared.analysis.movement_count,
            estimated_runtime_seconds=prepared.analysis.estimated_runtime_seconds,
            warning_count=len(prepared.warnings),
            result=result,
            notes=note,
        )
        self.job_history = append_job_history(entry)
        self._update_assistant_panel(prepared)
        self.log(f"Job-Ergebnis gespeichert: {result}")

    def _refresh_gcode(self) -> None:
        if not hasattr(self, "gcode_text"):
            return
        self.laser_project.material_width_mm = self.work_width.value()
        self.laser_project.material_height_mm = self.work_height.value()
        self.laser_project.material_name = self.profile_name.currentText() if hasattr(self, "profile_name") else ""
        profile = self._effective_job_profile()
        operation_mode = self.operation_mode.currentText()
        active_rasters = [
            item for item in self.laser_project.items
            if item.active and item.is_raster
        ]
        active_vectors = self._active_vector_item_paths()
        if not self.laser_project.items and self._current_vector_paths():
            active_vectors = [("Motiv", self._current_vector_paths())]
        if active_rasters and not active_vectors:
            self.layer_panel.set_fill_available(
                False,
                "Rasterquelle: Flaechenfuellung ist nur fuer SVG-/Vektorkonturen verfuegbar.",
            )
            self.fill_toolpaths = []
            source = self._raster_source_for_item(active_rasters[0])
            code = "\n".join(
                [
                    "; Rastergravur-Quelle importiert",
                    f"; Datei: {source.file_name if source else active_rasters[0].name}",
                    f"; Bild: {source.pixel_width if source else 0} x {source.pixel_height if source else 0} px",
                    f"; Groesse: {active_rasters[0].transform.current_width_mm:.2f} x {active_rasters[0].transform.current_height_mm:.2f} mm",
                    "; Rastergravur-GCode noch nicht verfuegbar.",
                ]
            )
        elif active_vectors:
            self.layer_panel.set_fill_available(True)
            layers = self._current_layers()
            self._fill_toolpaths_by_item = {}
            if self.laser_project.items:
                for item in self.laser_project.items:
                    if not item.active:
                        continue
                    base_paths = self._effective_item_vector_paths(item)
                    if not base_paths:
                        continue
                    transformed_paths = transform_paths(base_paths, item.transform)
                    self._fill_toolpaths_by_item[item.item_id] = build_layer_fill_toolpaths(
                        transformed_paths,
                        layers,
                        self.work_width.value(),
                        self.work_height.value(),
                    )
            else:
                self._fill_toolpaths_by_item["legacy"] = build_layer_fill_toolpaths(
                    active_vectors[0][1],
                    layers,
                    self.work_width.value(),
                    self.work_height.value(),
                )
            self.fill_toolpaths = [
                toolpath
                for toolpaths in self._fill_toolpaths_by_item.values()
                for toolpath in toolpaths
            ]
            fill_warnings = [
                warning
                for toolpath in self.fill_toolpaths
                for warning in toolpath.warnings
            ]
            self.layer_panel.set_fill_warning(fill_warnings[0] if fill_warnings else "")
            try:
                if len(active_vectors) == 1 and len(self.laser_project.items) <= 1:
                    code = build_layered_polyline_gcode(active_vectors[0][1], layers, operation_mode, self.fill_toolpaths)
                else:
                    fills_by_name = {
                        item.name: self._fill_toolpaths_by_item.get(item.item_id, [])
                        for item in self.laser_project.items
                    }
                    code = build_multi_item_layered_polyline_gcode(active_vectors, layers, operation_mode, fills_by_name)
            except ValueError as exc:
                code = "\n".join(
                    [
                        "; G-Code nicht erzeugt",
                        f"; {exc}",
                        "; Konturmodus bleibt moeglich; Fuellung fuer diese SVG-Geometrie ist blockiert.",
                    ]
                )
        elif self.laser_project.items:
            self.layer_panel.set_fill_available(False, "Kein aktives Vektormotiv vorhanden.")
            self.fill_toolpaths = []
            self._fill_toolpaths_by_item = {}
            code = "; G-Code nicht erzeugt\n; Kein aktives Motiv vorhanden."
        else:
            self.layer_panel.set_fill_available(
                False,
                "Noch keine Vektordatei geladen. Fuelloptionen bleiben deaktiviert.",
            )
            self.fill_toolpaths = []
            code = build_rectangle_frame_gcode(self.work_width.value(), self.work_height.value(), profile, operation_mode)
        if self.gcode_text.toPlainText() != code:
            self.gcode_text.setPlainText(code)
        self._update_job_summary()

    def _current_vector_paths(self) -> list:
        self._sync_selected_item_from_legacy_state()
        source_paths = self._effective_legacy_source_paths()
        if source_paths and self.artwork_transform is not None:
            self.imported_paths = transform_paths(source_paths, self.artwork_transform)
        return self.imported_paths

    def _effective_legacy_source_paths(self) -> list:
        if not self.original_imported_paths:
            return []
        self._refresh_svg_optimization_for_legacy()
        if self._svg_optimization_active() and self.svg_optimized_paths:
            return self.svg_optimized_paths
        return self.original_imported_paths

    def _effective_item_vector_paths(self, item: ArtworkItem) -> list:
        base_paths = self._item_vector_paths.get(item.item_id, [])
        if not base_paths:
            return []
        self._refresh_svg_optimization_for_item(item.item_id)
        if self._svg_optimization_active():
            return self._item_optimized_vector_paths.get(item.item_id, base_paths)
        return base_paths

    def _svg_optimization_active(self) -> bool:
        return bool(
            getattr(self, "svg_simplify_enabled", None)
            and (self.svg_simplify_enabled.isChecked() or self.svg_remove_duplicates.isChecked())
        )

    def _svg_tolerance_mm(self) -> float:
        if not hasattr(self, "svg_tolerance"):
            return 0.02
        data = self.svg_tolerance.currentData()
        return float(data if data is not None else 0.02)

    def _refresh_svg_optimization_for_legacy(self) -> None:
        if not self.original_imported_paths:
            self.svg_analysis = None
            self.svg_optimization_result = None
            self.svg_optimized_paths = []
            return
        result = optimize_svg_paths(
            self.original_imported_paths,
            simplify_enabled=bool(getattr(self, "svg_simplify_enabled", None) and self.svg_simplify_enabled.isChecked()),
            tolerance_mm=self._svg_tolerance_mm(),
            remove_duplicates=bool(getattr(self, "svg_remove_duplicates", None) and self.svg_remove_duplicates.isChecked()),
        )
        self.svg_analysis = result.original_analysis
        self.svg_optimization_result = result
        self.svg_optimized_paths = result.paths

    def _refresh_svg_optimization_for_item(self, item_id: str) -> None:
        paths = self._item_vector_paths.get(item_id, [])
        if not paths:
            return
        result = optimize_svg_paths(
            paths,
            simplify_enabled=bool(getattr(self, "svg_simplify_enabled", None) and self.svg_simplify_enabled.isChecked()),
            tolerance_mm=self._svg_tolerance_mm(),
            remove_duplicates=bool(getattr(self, "svg_remove_duplicates", None) and self.svg_remove_duplicates.isChecked()),
        )
        self._item_svg_analyses[item_id] = result.original_analysis
        self._item_svg_optimization_results[item_id] = result
        self._item_optimized_vector_paths[item_id] = result.paths

    def _svg_optimization_changed(self) -> None:
        self.svg_optimized_paths = []
        self._item_optimized_vector_paths = {}
        self._item_svg_optimization_results = {}
        self._item_intelligence_results = {}
        if self.original_imported_paths:
            self._refresh_svg_optimization_for_legacy()
        for item_id in list(self._item_vector_paths):
            self._refresh_svg_optimization_for_item(item_id)
            self._refresh_laser_intelligence_for_item(item_id)
        self._refresh_gcode()
        self._draw_preview()
        self._update_import_summary()

    def _intelligence_optimization_options(self) -> GeometryOptimizationOptions:
        simplify = bool(getattr(self, "svg_simplify_enabled", None) and self.svg_simplify_enabled.isChecked())
        remove_duplicates = bool(getattr(self, "svg_remove_duplicates", None) and self.svg_remove_duplicates.isChecked())
        return GeometryOptimizationOptions(
            simplify_contours=simplify,
            simplify_tolerance_mm=self._svg_tolerance_mm(),
            merge_short_segments=False,
            remove_duplicate_lines=remove_duplicates,
            duplicate_tolerance_mm=0.02,
            reduce_intermediate_points=simplify,
        )

    def _refresh_laser_intelligence_for_item(self, item_id: str) -> None:
        source = self._item_sources.get(item_id)
        if source is None:
            return
        try:
            result = self.laser_intelligence_engine.analyze_source(
                source,
                self._intelligence_optimization_options(),
                self._effective_job_profile().speed_mm_min if hasattr(self, "profile_name") else 3000,
                material_name=self._effective_job_profile().name if hasattr(self, "profile_name") else "",
            )
        except Exception as exc:  # noqa: BLE001 - non-blocking advisory engine
            self.log(f"Laser Intelligence konnte Quelle nicht analysieren: {exc}")
            return
        self._item_intelligence_results[item_id] = result
        if item_id == self.selected_artwork_item_id:
            self.laser_intelligence_result = result

    def _refresh_laser_intelligence_for_source(self, source: object) -> None:
        try:
            result = self.laser_intelligence_engine.analyze_source(
                source,
                self._intelligence_optimization_options(),
                self._effective_job_profile().speed_mm_min if hasattr(self, "profile_name") else 3000,
                material_name=self._effective_job_profile().name if hasattr(self, "profile_name") else "",
            )
        except Exception as exc:  # noqa: BLE001 - advisory engine must not break import
            self.log(f"Laser Intelligence konnte Quelle nicht analysieren: {exc}")
            return
        self.laser_intelligence_result = result

    def _selected_artwork_item(self) -> ArtworkItem | None:
        return next((item for item in self.laser_project.items if item.item_id == self.selected_artwork_item_id), None)

    def _active_vector_item_paths(self) -> list[tuple[str, list]]:
        result: list[tuple[str, list]] = []
        for item in self.laser_project.items:
            if not item.active:
                continue
            paths = self._effective_item_vector_paths(item)
            if paths:
                result.append((item.name, transform_paths(paths, item.transform)))
        return result

    def _visible_preview_items(self) -> list[PreviewArtworkItem]:
        items: list[PreviewArtworkItem] = []
        for item in self.laser_project.items:
            raster_source = None
            if item.is_raster:
                raster_source = self._raster_source_for_item(item)
            items.append(
                PreviewArtworkItem(
                    item_id=item.item_id,
                    name=item.name,
                    source_type=item.source_type,
                    paths=self._effective_item_vector_paths(item),
                    raster_source=raster_source,
                    transform=item.transform,
                    visible=item.visible,
                    active=item.active,
                    selected=item.item_id == self.selected_artwork_item_id,
                )
            )
        return items

    def _raster_source_for_item(self, item: ArtworkItem) -> RasterImageSource | None:
        source = self._item_original_rasters.get(item.item_id)
        if source is None:
            raw_source = self._item_sources.get(item.item_id)
            source = raw_source if isinstance(raw_source, RasterImageSource) else None
        if source is None:
            return None
        bounds = item.transform.bounds
        return replace(
            source,
            transform=item.transform,
            width_mm=item.transform.current_width_mm,
            height_mm=item.transform.current_height_mm,
            bounding_box=(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y),
            raster_resolution_mm=item.transform.current_width_mm / source.pixel_width if source.pixel_width else None,
        )

    def _sync_selected_item_from_legacy_state(self) -> None:
        item = self._selected_artwork_item()
        if item is None or self.artwork_transform is None:
            return
        if item.transform != self.artwork_transform:
            item.transform = self.artwork_transform

    def _select_artwork_item(self, item_id: str | None) -> None:
        if item_id is None:
            self.selected_artwork_item_id = None
            self.artwork_source = None
            self.artwork_transform = None
            self.original_imported_paths = []
            self.imported_paths = []
            self.raster_sources = []
            self.original_raster_source = None
            self._refresh_object_table()
            self._sync_transform_controls()
            self._draw_preview()
            return
        item = next((candidate for candidate in self.laser_project.items if candidate.item_id == item_id), None)
        if item is None:
            return
        self.selected_artwork_item_id = item.item_id
        self.artwork_transform = item.transform
        self.artwork_source = self._item_sources.get(item.item_id)
        self.imported_file = item.source_path
        self.original_imported_paths = list(self._item_vector_paths.get(item.item_id, []))
        self._refresh_svg_optimization_for_item(item.item_id)
        self.svg_analysis = self._item_svg_analyses.get(item.item_id)
        self.svg_optimization_result = self._item_svg_optimization_results.get(item.item_id)
        self.svg_optimized_paths = self._item_optimized_vector_paths.get(item.item_id, [])
        self.laser_intelligence_result = self._item_intelligence_results.get(item.item_id)
        self.imported_paths = transform_paths(self.original_imported_paths, item.transform) if self.original_imported_paths else []
        raster = self._raster_source_for_item(item)
        self.original_raster_source = self._item_original_rasters.get(item.item_id)
        self.raster_sources = [raster] if raster is not None else []
        self._refresh_object_table()
        self._sync_transform_controls()
        self._set_svg_size_label(item.transform.current_width_mm, item.transform.current_height_mm)
        self._update_import_summary()
        self._draw_preview()

    def _add_artwork_source_to_project(self, source: object, transform: ArtworkTransform) -> ArtworkItem:
        source_type = getattr(source, "source_type", "")
        raw_type = getattr(source_type, "value", source_type)
        source_path = getattr(source, "file_path", None)
        name = getattr(source, "file_name", "Motiv")
        item = ArtworkItem(
            item_id=new_item_id(),
            name=name,
            source_type="svg" if raw_type == ArtworkSourceType.VECTOR.value else str(raw_type),
            source_path=source_path,
            transform=transform,
            layer_assignments={},
            visible=True,
            active=True,
            source_data=self._source_to_item_data(source, transform),
        )
        self.laser_project.items.append(item)
        self._item_sources[item.item_id] = source
        self._refresh_laser_intelligence_for_item(item.item_id)
        if isinstance(source, VectorArtworkSource):
            self._item_vector_paths[item.item_id] = normalize_paths(source.paths)
            self._refresh_svg_optimization_for_item(item.item_id)
        elif isinstance(source, RasterImageSource):
            self._item_original_rasters[item.item_id] = source
        self._select_artwork_item(item.item_id)
        return item

    def _source_to_item_data(self, source: object, transform: ArtworkTransform | None = None) -> dict:
        return {
            "source_id": str(getattr(source, "source_id", "")),
            "file_name": str(getattr(source, "file_name", "")),
            "source_type": str(getattr(getattr(source, "source_type", ""), "value", getattr(source, "source_type", ""))),
            "width_mm": float(getattr(source, "width_mm", 0.0)),
            "height_mm": float(getattr(source, "height_mm", 0.0)),
            "bounding_box": list(getattr(source, "bounding_box", (0.0, 0.0, 0.0, 0.0))),
            "transform": transform_to_dict(transform or getattr(source, "transform", None) or self.artwork_transform or ArtworkTransform(0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0)),
        }

    def _refresh_object_table(self) -> None:
        if not hasattr(self, "object_table"):
            return
        self._object_list_updating = True
        try:
            if hasattr(self, "project_empty_state"):
                self.project_empty_state.setVisible(not self.laser_project.items)
            self.object_table.setRowCount(len(self.laser_project.items))
            for row, item in enumerate(self.laser_project.items):
                values = [
                    ("x" if item.visible else "", item.visible),
                    ("x" if item.active else "", item.active),
                    (item.name, None),
                    (item.source_type, None),
                ]
                for column, (text, checked) in enumerate(values):
                    table_item = self.object_table.item(row, column) or QTableWidgetItem()
                    table_item.setText(text)
                    table_item.setData(Qt.ItemDataRole.UserRole, item.item_id)
                    if checked is not None:
                        table_item.setFlags(table_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                        table_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                    elif column == 2:
                        table_item.setFlags(table_item.flags() | Qt.ItemFlag.ItemIsEditable)
                    else:
                        table_item.setFlags(table_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.object_table.setItem(row, column, table_item)
                if item.item_id == self.selected_artwork_item_id:
                    self.object_table.selectRow(row)
        finally:
            self._object_list_updating = False

    def _object_table_item_changed(self, table_item: QTableWidgetItem) -> None:
        if self._object_list_updating:
            return
        item_id = table_item.data(Qt.ItemDataRole.UserRole)
        item = next((candidate for candidate in self.laser_project.items if candidate.item_id == item_id), None)
        if item is None:
            return
        if table_item.column() == 0:
            item.visible = table_item.checkState() == Qt.CheckState.Checked
        elif table_item.column() == 1:
            item.active = table_item.checkState() == Qt.CheckState.Checked
        elif table_item.column() == 2:
            item.name = table_item.text().strip() or item.name
        self._refresh_gcode()
        self._draw_preview()

    def _object_table_selection_changed(self) -> None:
        if self._object_list_updating:
            return
        rows = self.object_table.selectionModel().selectedRows() if hasattr(self, "object_table") else []
        if not rows:
            return
        item = self.object_table.item(rows[0].row(), 0)
        if item is not None:
            self._select_artwork_item(str(item.data(Qt.ItemDataRole.UserRole)))

    def _operation_mode_label(self) -> str:
        return "Cutten (M3 konstant)" if self.operation_mode.currentText() == CUT_MODE else "Gravieren (M4 dynamisch)"

    def _on_operation_mode_changed(self) -> None:
        self._apply_mode_profile_to_controls()
        self._sync_layers_from_controls(preserve_states=False)
        self._settings_changed()

    def _ensure_profile_modes(self, profile_name: str) -> None:
        self.profile_service.ensure_profile_modes(profile_name)

    def _apply_mode_profile_to_controls(self) -> None:
        selected_name = self.profile_name.currentText()
        if not selected_name:
            return
        self._ensure_profile_modes(selected_name)
        mode_profile = self.profile_service.profile_for(selected_name, self.operation_mode.currentText())
        self.power_percent.blockSignals(True)
        self.speed_mm_min.blockSignals(True)
        self.passes.blockSignals(True)
        self.power_percent.setValue(mode_profile.power_percent)
        self.speed_mm_min.setValue(mode_profile.speed_mm_min)
        self.passes.setValue(mode_profile.passes)
        self.power_percent.blockSignals(False)
        self.speed_mm_min.blockSignals(False)
        self.passes.blockSignals(False)

    def _import_svg(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Datei importieren", "", supported_file_filter())
        if not path:
            return
        try:
            source = self.import_service.import_file(path)
        except Exception as exc:  # noqa: BLE001 - show file import errors to user
            QMessageBox.critical(self, "Datei importieren", str(exc))
            return
        self._refresh_laser_intelligence_for_source(source)
        transform = self._default_transform_for_source(source)
        item = self._add_artwork_source_to_project(source, transform)
        self.artwork_source = replace(source, transform=transform) if isinstance(source, (VectorArtworkSource, RasterImageSource)) else source
        self._item_sources[item.item_id] = self.artwork_source
        self._refresh_laser_intelligence_for_item(item.item_id)
        self.imported_file = path
        if isinstance(source, VectorArtworkSource):
            self.raster_sources = []
            self.original_raster_source = None
            self.original_imported_paths = normalize_paths(source.paths)
            self._refresh_svg_optimization_for_legacy()
            self.imported_paths = transform_paths(self.original_imported_paths, transform)
            self.artwork_transform = transform
            self._sync_transform_controls()
            self._refresh_gcode()
            self._draw_preview()
            if self.autofit_result:
                self.log(self.autofit_result.summary)
            self.log(f"Vektordatei importiert: {path} ({len(self.laser_project.items)} Motive im Projekt)")
        elif isinstance(source, RasterImageSource):
            self.original_imported_paths = []
            self.imported_paths = []
            self.original_raster_source = source
            fitted_source = self._raster_source_for_item(item) or self._fit_raster_source(source)
            self.raster_sources = [fitted_source]
            self.artwork_source = fitted_source
            self._item_sources[item.item_id] = fitted_source
            self._item_original_rasters[item.item_id] = source
            self._sync_transform_controls()
            self._set_svg_size_label(fitted_source.width_mm, fitted_source.height_mm, source_label=f"Raster: {source.file_name}")
            self._sync_layers_from_controls(preserve_states=False)
            self._refresh_gcode()
            self._draw_preview()
            self._update_assistant_panel()
            if self.autofit_result:
                self.log(self.autofit_result.summary)
            for warning in source.import_warnings:
                self.log(f"Importwarnung: {warning}")
            self.log(f"Rasterbild importiert: {path} ({len(self.laser_project.items)} Motive im Projekt)")

    def _default_transform_for_source(self, source: object) -> ArtworkTransform:
        width = float(getattr(source, "width_mm", 1.0))
        height = float(getattr(source, "height_mm", 1.0))
        result = self.autofit_service.fit(
            width,
            height,
            self.work_width.value(),
            self.work_height.value(),
            0.0,
        )
        offset = min(5.0, max(0.0, len(self.laser_project.items) * 2.0))
        max_x = max(0.0, self.work_width.value() - result.current_width_mm)
        max_y = max(0.0, self.work_height.value() - result.current_height_mm)
        self.autofit_result = replace(
            result,
            offset_x_mm=min(max_x, result.offset_x_mm + offset),
            offset_y_mm=min(max_y, result.offset_y_mm + offset),
        )
        return autofit_to_transform(self.autofit_result)

    def _fit_raster_source(self, source: RasterImageSource) -> RasterImageSource:
        result = self.autofit_service.fit(
            source.width_mm,
            source.height_mm,
            self.work_width.value(),
            self.work_height.value(),
            0.0,
        )
        self.autofit_result = result
        self.artwork_transform = autofit_to_transform(result)
        return replace(
            source,
            width_mm=result.current_width_mm,
            height_mm=result.current_height_mm,
            bounding_box=(
                result.offset_x_mm,
                result.offset_y_mm,
                result.offset_x_mm + result.current_width_mm,
                result.offset_y_mm + result.current_height_mm,
            ),
            transform=self.artwork_transform,
            raster_resolution_mm=result.current_width_mm / source.pixel_width if source.pixel_width else None,
        )

    def _save_project(self) -> None:
        path = self.current_project_path
        if path is None:
            path, _filter = QFileDialog.getSaveFileName(self, "Projekt speichern", "", "Laser Projekt (*.laser.json)")
        if not path:
            return
        if not path.endswith(".laser.json"):
            path += ".laser.json"
        self.laser_project.material_width_mm = self.work_width.value()
        self.laser_project.material_height_mm = self.work_height.value()
        self.laser_project.material_name = self.profile_name.currentText()
        data = project_to_dict(
            self.work_width.value(),
            self.work_height.value(),
            self._selected_profile(),
            self.gcode_text.toPlainText(),
            self.original_imported_paths if self.original_imported_paths else self.imported_paths,
            self.imported_file,
            self.material_measurement,
            self._svg_placement_data(),
            self.operation_mode.currentText(),
            [layer_to_dict(layer) for layer in self._current_layers()],
            self._artwork_source_to_project(),
            self.laser_project,
        )
        save_project(path, data)
        self.current_project_path = path
        self.log(f"Projekt gespeichert: {path}")

    def _load_project(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Projekt laden", "", "Laser Projekt (*.laser.json);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            data = load_project(path)
        except Exception as exc:  # noqa: BLE001 - show project load errors to user
            QMessageBox.critical(self, "Projekt laden", str(exc))
            return
        self.work_width.setValue(float(data["work_area"]["width_mm"]))
        self.work_height.setValue(float(data["work_area"]["height_mm"]))
        profile_data = data["material_profile"]
        profile = MaterialProfile(
            profile_data["name"],
            int(profile_data["power_percent"]),
            int(profile_data["speed_mm_min"]),
            int(profile_data["passes"]),
        )
        self._upsert_profile(profile)
        self.profile_name.setCurrentText(profile.name)
        self.power_percent.setValue(profile.power_percent)
        self.speed_mm_min.setValue(profile.speed_mm_min)
        self.passes.setValue(profile.passes)
        self.current_project_path = path
        self.imported_paths = data.get("imported_paths", [])
        self.original_imported_paths = self.imported_paths
        self.imported_file = data.get("imported_file")
        self.raster_sources = []
        self.artwork_source = None
        self.original_raster_source = None
        self.autofit_result = None
        self.artwork_transform = None
        self.laser_project = laser_project_from_dict(data.get("laser_project") or {})
        self._item_sources = {}
        self._item_vector_paths = {}
        self._item_original_rasters = {}
        self._fill_toolpaths_by_item = {}
        for item in self.laser_project.items:
            if not item.source_path:
                continue
            try:
                source = self.import_service.import_file(item.source_path)
            except Exception as exc:  # noqa: BLE001 - keep project load usable
                self.log(f"Motivquelle konnte nicht erneut geladen werden ({item.name}): {exc}")
                continue
            self._item_sources[item.item_id] = replace(source, transform=item.transform) if isinstance(source, (VectorArtworkSource, RasterImageSource)) else source
            if isinstance(source, VectorArtworkSource):
                self._item_vector_paths[item.item_id] = normalize_paths(source.paths)
                self._refresh_svg_optimization_for_item(item.item_id)
            elif isinstance(source, RasterImageSource):
                self._item_original_rasters[item.item_id] = source
        if self.laser_project.items:
            self._select_artwork_item(self.laser_project.items[0].item_id)
        artwork_data = data.get("artwork_source") or {}
        transform_data = artwork_data.get("transform") or {}
        if not self.laser_project.items and artwork_data.get("source_type") == ArtworkSourceType.RASTER.value and self.imported_file:
            try:
                source = self.import_service.import_file(self.imported_file)
            except Exception as exc:  # noqa: BLE001 - keep project load usable
                self.log(f"Rasterquelle konnte nicht erneut geladen werden: {exc}")
            else:
                if isinstance(source, RasterImageSource):
                    self.original_raster_source = source
                    if transform_data:
                        self.artwork_transform = self._transform_from_project(transform_data)
                        bounds = self.artwork_transform.bounds
                        source = replace(
                            source,
                            width_mm=self.artwork_transform.current_width_mm,
                            height_mm=self.artwork_transform.current_height_mm,
                            bounding_box=(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y),
                            transform=self.artwork_transform,
                            raster_resolution_mm=self.artwork_transform.current_width_mm / source.pixel_width if source.pixel_width else None,
                        )
                    else:
                        source = self._fit_raster_source(source)
                    self.artwork_source = source
                    self.raster_sources = [source]
                    self.imported_paths = []
                    self.original_imported_paths = []
        elif not self.laser_project.items and artwork_data.get("source_type") == ArtworkSourceType.VECTOR.value and self.imported_file:
            self.artwork_source = VectorArtworkSource(
                source_id=str(artwork_data.get("source_id", "")),
                file_path=self.imported_file,
                file_name=str(artwork_data.get("file_name", self.imported_file)),
                source_type=ArtworkSourceType.VECTOR,
                width_mm=float(artwork_data.get("width_mm", self.work_width.value())),
                height_mm=float(artwork_data.get("height_mm", self.work_height.value())),
                bounding_box=tuple(artwork_data.get("bounding_box", [0.0, 0.0, self.work_width.value(), self.work_height.value()])), # type: ignore[arg-type]
                paths=self.imported_paths,
            )
            autofit_data = artwork_data.get("autofit") or {}
            if autofit_data:
                self.autofit_result = AutoFitResult(
                    original_width_mm=float(autofit_data.get("original_width_mm", self.work_width.value())),
                    original_height_mm=float(autofit_data.get("original_height_mm", self.work_height.value())),
                    current_width_mm=float(autofit_data.get("current_width_mm", self.work_width.value())),
                    current_height_mm=float(autofit_data.get("current_height_mm", self.work_height.value())),
                    scale_factor=float(autofit_data.get("scale_factor", 1.0)),
                    offset_x_mm=float(autofit_data.get("offset_x_mm", 0.0)),
                    offset_y_mm=float(autofit_data.get("offset_y_mm", 0.0)),
                    work_width_mm=self.work_width.value(),
                    work_height_mm=self.work_height.value(),
                    applied=bool(autofit_data.get("applied", False)),
                    position=str(autofit_data.get("position", "zentriert")),
                )
            if transform_data:
                self.artwork_transform = self._transform_from_project(transform_data)
                self.original_imported_paths = normalize_paths(self.imported_paths)
                self.imported_paths = transform_paths(self.original_imported_paths, self.artwork_transform)
                bounds = self.artwork_transform.bounds
                self.artwork_source = replace(
                    self.artwork_source,
                    transform=self.artwork_transform,
                    width_mm=self.artwork_transform.current_width_mm,
                    height_mm=self.artwork_transform.current_height_mm,
                    bounding_box=(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y),
                    paths=self.original_imported_paths,
                )
        self.material_measurement = data.get("material_measurement")
        self.material_points = {1: None, 2: None, 3: None, 4: None}
        if self.material_measurement:
            raw_points = self.material_measurement.get("points") or {}
            for key, value in raw_points.items():
                index = int(key)
                if index in self.material_points and value:
                    self.material_points[index] = tuple(value) # type: ignore
            if not raw_points:
                self.material_points[1] = tuple(self.material_measurement["point_a"]) if self.material_measurement.get("point_a") else None # type: ignore
                self.material_points[2] = tuple(self.material_measurement["point_b"]) if self.material_measurement.get("point_b") else None # type: ignore
            self.material_point_a = self.material_points[1]
            self.material_point_b = self.material_points[2]
        placement = data.get("svg_placement") or {}
        if data.get("operation_mode"):
            self.operation_mode.setCurrentText(data["operation_mode"])
        self.svg_auto.setChecked(placement.get("mode", "Automatisch") == "Automatisch")
        self.svg_manual_width.setValue(float(placement.get("manual_width", self.svg_manual_width.value())))
        self.artwork_height.setValue(float(placement.get("manual_height", self.artwork_height.value())))
        self.artwork_scale_percent.setValue(float(placement.get("scale_percent", self.artwork_scale_percent.value())))
        self.artwork_rotation.setValue(float(placement.get("rotation_deg", self.artwork_rotation.value())))
        self.artwork_keep_aspect.setChecked(bool(placement.get("keep_aspect_ratio", True)))
        self.svg_offset_x.setValue(float(placement.get("offset_x", 0)))
        self.svg_offset_y.setValue(float(placement.get("offset_y", 0)))
        self.svg_margin.setValue(float(placement.get("margin", AUTO_FIT_MARGIN_MM)))
        self.material_shape.setCurrentText(placement.get("material_shape", MATERIAL_SHAPE_RECTANGLE))
        self.job_origin.setCurrentText(placement.get("job_origin", JOB_ORIGIN_LOWER_LEFT))
        if data.get("layers"):
            try:
                self.layer_panel.set_layers([layer_from_dict(item) for item in data.get("layers", [])])
            except Exception as exc:  # noqa: BLE001 - load project should remain usable
                self.log(f"Layerdaten konnten nicht geladen werden: {exc}")
                self._sync_layers_from_controls(preserve_states=False)
        else:
            self._sync_layers_from_controls(preserve_states=False)
        self.gcode_text.setPlainText(data.get("gcode", ""))
        self._update_material_measurement_label()
        self._draw_preview()
        self.log(f"Projekt geladen: {path}")

    def _draw_preview(self) -> None:
        if hasattr(self, "preview"):
            self.preview.set_preview_model(
                self._build_preview_model(),
                self.material_shape.currentText() if hasattr(self, "material_shape") else MATERIAL_SHAPE_RECTANGLE,
                self.svg_margin.value() if hasattr(self, "svg_margin") else AUTO_FIT_MARGIN_MM,
                self.job_origin.currentText() if hasattr(self, "job_origin") else JOB_ORIGIN_LOWER_LEFT,
            )
            selected_item = self._selected_artwork_item()
            self.preview.set_artwork_interaction(
                selected_item.transform.bounds if selected_item is not None else (self.artwork_transform.bounds if self.artwork_transform is not None else None),
                bool(
                    self.preview_options.get("snap") is None
                    or self.preview_options["snap"].isChecked()
                ),
            )
        self._update_import_summary()

    def _build_preview_model(self) -> JobPreviewModel:
        estimated_runtime = None
        warnings: list[str] = []
        if hasattr(self, "gcode_text"):
            try:
                prepared = self.job_service.prepare_job(
                    self.gcode_text.toPlainText(),
                    self.work_width.value(),
                    self.work_height.value(),
                    self._effective_job_profile(),
                    self.operation_mode.currentText(),
                )
                estimated_runtime = prepared.analysis.estimated_runtime_seconds
                warnings.extend(prepared.warnings)
                gcode_segments = prepared.analysis.segments
            except ValueError as exc:
                warnings.append(str(exc))
                gcode_segments = []
        else:
            gcode_segments = []
        if self.autofit_result is not None:
            warnings.append(self.autofit_result.summary)
        if self.laser_project.items:
            return build_multi_item_preview_model(
                self._visible_preview_items(),
                self._current_layers(),
                self.work_width.value(),
                self.work_height.value(),
                estimated_runtime,
                warnings,
                gcode_segments,
                self._preview_head_position(),
                self._preview_options(),
                self._fill_toolpaths_by_item,
            )
        preview_paths = self._effective_legacy_source_paths() if self.original_imported_paths and self.artwork_transform is not None else self.imported_paths
        return build_preview_model(
            preview_paths,
            self._current_layers(),
            self.work_width.value(),
            self.work_height.value(),
            estimated_runtime,
            warnings,
            self.raster_sources,
            self.artwork_transform if self.original_imported_paths else None,
            gcode_segments,
            self._preview_head_position(),
            self._preview_options(),
            self.fill_toolpaths,
        )

    def _preview_options(self) -> PreviewOptions:
        options = getattr(self, "preview_options", {})
        return PreviewOptions(
            show_artwork=bool(options.get("artwork") is None or options["artwork"].isChecked()),
            show_bounds=bool(options.get("bounds") is None or options["bounds"].isChecked()),
            show_work_area=bool(options.get("work_area") is None or options["work_area"].isChecked()),
            show_head_position=bool(options.get("head") is None or options["head"].isChecked()),
            show_gcode_path=bool(options.get("gcode") is not None and options["gcode"].isChecked()),
            show_overscan=bool(options.get("overscan") is None or options["overscan"].isChecked()),
        )

    def _move_artwork_from_preview(self, x_mm: float, y_mm: float) -> None:
        if self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(
            self.artwork_transform.with_position(round(x_mm, 1), round(y_mm, 1))
        )

    def _preview_selection_changed(self, selected: bool) -> None:
        if not hasattr(self, "preview_position_label"):
            return
        transform = self.artwork_transform
        if not selected or transform is None:
            self.preview_position_label.setText("Motivposition: --")
            return
        self.preview_position_label.setText(
            f"Motiv ausgewaehlt | X: {transform.x_mm:.1f} mm | Y: {transform.y_mm:.1f} mm"
        )

    def _preview_head_position(self) -> PreviewHeadPosition | None:
        state = getattr(self, "app_controller", None).machine_state if hasattr(self, "app_controller") else None
        if state is None or not state.position_source or state.x_mm is None or state.y_mm is None:
            return None
        if not state.position_source.startswith("WPos"):
            return None
        return PreviewHeadPosition(state.x_mm, state.y_mm, state.position_source)

    def _svg_preflight_warnings(self) -> list[str]:
        analyses: list[SvgVectorAnalysis] = []
        results: list[SvgOptimizationResult] = []
        if self.laser_project.items:
            for item in self.laser_project.items:
                if not item.active or not item.is_vector:
                    continue
                self._refresh_svg_optimization_for_item(item.item_id)
                analysis = self._item_svg_analyses.get(item.item_id)
                result = self._item_svg_optimization_results.get(item.item_id)
                if analysis:
                    analyses.append(analysis)
                if result:
                    results.append(result)
        else:
            self._refresh_svg_optimization_for_legacy()
            if self.svg_analysis:
                analyses.append(self.svg_analysis)
            if self.svg_optimization_result:
                results.append(self.svg_optimization_result)
        warnings: list[str] = []
        for analysis in analyses:
            warnings.append(
                f"SVG-Komplexitaet: {analysis.complexity} - {analysis.segment_count} Segmente, "
                f"{analysis.short_segment_count} sehr kurze Segmente."
            )
            warnings.extend(analysis.warnings)
        for result in results:
            if result.simplify_enabled or result.duplicate_removal_enabled:
                warnings.append(
                    "SVG-Optimierung aktiv: "
                    f"{result.original_analysis.segment_count} -> {result.optimized_analysis.segment_count} Segmente "
                    f"mit {result.tolerance_mm:.2f} mm Toleranz."
                )
        intelligence_results = (
            [self._item_intelligence_results[item.item_id] for item in self.laser_project.items if item.active and item.item_id in self._item_intelligence_results]
            if self.laser_project.items
            else ([self.laser_intelligence_result] if self.laser_intelligence_result is not None else [])
        )
        for intelligence in intelligence_results:
            warnings.append(
                "Laser Intelligence: "
                f"{intelligence.quality.score}% Qualitaet, "
                f"Klasse {intelligence.classification.motif_class.value}, "
                f"Strategie {intelligence.classification.recommended_strategy}."
            )
            if intelligence.analysis.bezier and intelligence.analysis.bezier.curve_count:
                warnings.append(
                    "Bezieranalyse: "
                    f"{intelligence.analysis.bezier.curve_count} Kurven, "
                    f"empf. Flattening {intelligence.analysis.bezier.recommended_flattening_tolerance_mm:.2f} mm."
                )
            if intelligence.analysis.raster:
                warnings.append(
                    "Rasteranalyse: "
                    f"Kontrast {intelligence.analysis.raster.contrast_score}%, "
                    f"Modus {intelligence.analysis.raster.recommended_mode}, "
                    f"Linienabstand {intelligence.analysis.raster.recommended_line_interval_mm:.2f} mm."
                )
            if intelligence.material_recommendation:
                warnings.append(
                    "Materialempfehlung Falcon 10W: "
                    f"{intelligence.material_recommendation.material_name} - "
                    f"{intelligence.material_recommendation.engraving_label}."
                )
            if intelligence.comparison_report:
                warnings.append("Original vs. Arbeitskopie: " + intelligence.comparison_report.short_summary)
        profile = self._effective_job_profile()
        warnings.extend(
            material_deviation_warnings(
                profile.name,
                int(profile.speed_mm_min),
                int(profile.power_percent),
                int(profile.passes),
            )
        )
        return warnings

    def _update_import_summary(self) -> None:
        if not hasattr(self, "import_summary_label"):
            return
        self.import_summary_label.setText(self._import_summary_text())
        if hasattr(self, "svg_analysis_label"):
            self.svg_analysis_label.setText(self._svg_analysis_text(compact=False))
        if hasattr(self, "laser_intelligence_label"):
            self.laser_intelligence_label.setText(self._laser_intelligence_text())

    def _import_summary_text(self) -> str:
        source = getattr(self, "artwork_source", None)
        if source is None:
            return "Import: keine Datei geladen"
        transform = self.artwork_transform or getattr(source, "transform", None)
        source_type = getattr(source, "source_type", "")
        type_label = "Raster" if getattr(source_type, "value", source_type) == "raster" else "Vektor"
        if transform is None:
            return f"Import: {source.file_name} | {type_label} | Transform: --"
        bounds_ok = transform.bounds.within(self.work_width.value(), self.work_height.value())
        warnings = list(getattr(source, "import_warnings", []))
        if not bounds_ok:
            warnings.append("Motiv ausserhalb des Arbeitsbereichs")
        warning_text = " | Warnungen: " + "; ".join(warnings) if warnings else ""
        analysis_text = ""
        if bool(getattr(self, "svg_show_analysis", None) and self.svg_show_analysis.isChecked()):
            compact = self._svg_analysis_text(compact=True)
            analysis_text = f" | {compact}" if compact else ""
        return (
            f"Import: {source.file_name} | {type_label} | "
            f"Original {transform.original_width_mm:.1f} x {transform.original_height_mm:.1f} mm | "
            f"Aktuell {transform.current_width_mm:.1f} x {transform.current_height_mm:.1f} mm | "
            f"X {transform.x_mm:.1f} Y {transform.y_mm:.1f} | "
            f"{transform.scale_percent:.1f}% | Rotation {transform.rotation_deg:.1f} deg | "
            f"AutoFit {'ja' if transform.autofit_applied else 'nein'} | "
            f"Arbeitsbereich {'OK' if bounds_ok else 'ueberschritten'}"
            f"{analysis_text}"
            f"{warning_text}"
        )

    def _svg_analysis_text(self, compact: bool) -> str:
        analysis = self.svg_analysis
        result = self.svg_optimization_result
        if analysis is None and self.selected_artwork_item_id:
            analysis = self._item_svg_analyses.get(self.selected_artwork_item_id)
            result = self._item_svg_optimization_results.get(self.selected_artwork_item_id)
        if analysis is None:
            return "Keine SVG-Analyse"
        if compact:
            optimized = ""
            if result and (result.simplify_enabled or result.duplicate_removal_enabled):
                optimized = f", optimiert {result.optimized_analysis.segment_count}"
            return f"SVG {analysis.complexity}: {analysis.segment_count} Segmente{optimized}"
        lines = [
            f"Pfade: {analysis.path_count}, offen: {analysis.open_path_count}, geschlossen: {analysis.closed_path_count}",
            f"Segmente: {analysis.segment_count}, sehr kurz: {analysis.short_segment_count}, Komplexitaet: {analysis.complexity}",
            f"Duplikate: {analysis.duplicate_segment_count}, GCode geschaetzt: {analysis.estimated_gcode_lines}",
        ]
        if result and (result.simplify_enabled or result.duplicate_removal_enabled):
            lines.append(
                f"Optimiert: {result.optimized_analysis.segment_count} Segmente, reduziert: {result.reduced_segments}, Toleranz: {result.tolerance_mm:.2f} mm"
            )
        if analysis.warnings:
            lines.append("Hinweis: " + " ".join(analysis.warnings[:2]))
        return "\n".join(lines)

    def _laser_intelligence_text(self) -> str:
        result = self.laser_intelligence_result
        if result is None and self.selected_artwork_item_id:
            result = self._item_intelligence_results.get(self.selected_artwork_item_id)
        if result is None:
            return "Laser Intelligence: keine Analyse"
        recommendations = ", ".join(result.quality.recommended_optimizations[:3]) or "keine automatische Optimierung noetig"
        machine = result.machine_recommendation
        analysis_bits: list[str] = []
        if result.analysis.bezier and result.analysis.bezier.curve_count:
            analysis_bits.append(
                f"Bezier: {result.analysis.bezier.curve_count} Kurven, Flattening {result.analysis.bezier.recommended_flattening_tolerance_mm:.2f} mm"
            )
        if result.analysis.raster:
            analysis_bits.append(
                f"Raster: Kontrast {result.analysis.raster.contrast_score}%, {result.analysis.raster.recommended_mode}, {result.analysis.raster.recommended_line_interval_mm:.2f} mm"
            )
        if result.comparison_report:
            analysis_bits.append(
                f"Original vs. Arbeitskopie: {result.comparison_report.segment_reduction_percent}% weniger Segmente, Risiko {result.comparison_report.detail_loss_risk}"
            )
        if result.material_recommendation:
            analysis_bits.append(
                f"Material: {result.material_recommendation.material_name} Startwert {result.material_recommendation.engraving_label}"
            )
        analysis_text = "\n".join(analysis_bits[:4])
        analysis_text = f"\n{analysis_text}" if analysis_text else ""
        return (
            f"Laser Intelligence {result.quality.bar} {result.quality.score}%\n"
            f"Klasse: {result.classification.motif_class.value} ({result.classification.confidence}%)\n"
            f"Strategie: {result.classification.recommended_strategy}\n"
            f"Falcon 10W: {machine.speed_mm_min} mm/min, {machine.power_percent}%, "
            f"{machine.passes}x, Overscan {machine.overscan_mm:.1f} mm\n"
            f"Vorschlag: {recommendations}"
            f"{analysis_text}"
        )

    def get_transformed_bounds(self) -> ArtworkBounds:
        active_bounds = [item.transform.bounds for item in self.laser_project.items if item.active]
        if active_bounds:
            return ArtworkBounds(
                min(bounds.min_x for bounds in active_bounds),
                min(bounds.min_y for bounds in active_bounds),
                max(bounds.max_x for bounds in active_bounds),
                max(bounds.max_y for bounds in active_bounds),
            )
        if self.artwork_transform is not None:
            return self.artwork_transform.bounds
        if self.raster_sources:
            source = self.raster_sources[0]
            if source.transform is not None:
                return source.transform.bounds
            min_x, min_y, max_x, max_y = source.bounding_box
            return ArtworkBounds(min_x, min_y, max_x, max_y)
        paths = self._current_vector_paths()
        if paths:
            min_x, min_y, max_x, max_y = path_bounds(paths)
            return ArtworkBounds(min_x, min_y, max_x, max_y)
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._effective_job_profile(),
                self.operation_mode.currentText(),
            )
            if prepared.analysis.has_bounds:
                return ArtworkBounds(
                    prepared.analysis.min_x or 0.0,
                    prepared.analysis.min_y or 0.0,
                    prepared.analysis.max_x or 0.0,
                    prepared.analysis.max_y or 0.0,
                )
        except ValueError:
            pass
        return ArtworkBounds(0.0, 0.0, self.work_width.value(), self.work_height.value())

    def _frame_dimensions(self) -> tuple[float, float]:
        bounds = self.get_transformed_bounds()
        if bounds.width_mm > 0 and bounds.height_mm > 0:
            return bounds.width_mm, bounds.height_mm
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._effective_job_profile(),
                self.operation_mode.currentText(),
            )
            if prepared.analysis.has_bounds and prepared.analysis.width_mm > 0 and prepared.analysis.height_mm > 0:
                return prepared.analysis.width_mm, prepared.analysis.height_mm
        except ValueError:
            pass
        return self.work_width.value(), self.work_height.value()

    def _selected_profile(self) -> MaterialProfile:
        return MaterialProfile(
            self.profile_name.currentText() or DEFAULT_PROFILES[0].name,
            self.power_percent.value() if hasattr(self, "power_percent") else DEFAULT_PROFILES[0].power_percent,
            self.speed_mm_min.value() if hasattr(self, "speed_mm_min") else DEFAULT_PROFILES[0].speed_mm_min,
            self.passes.value() if hasattr(self, "passes") else DEFAULT_PROFILES[0].passes,
        )

    def _upsert_profile(self, profile: MaterialProfile) -> None:
        self.profile_service.upsert_mode_profile(profile, self.operation_mode.currentText())
        self.profile_name.blockSignals(True)
        current = self.profile_name.currentText()
        self.profile_name.clear()
        self.profile_name.addItems(self.profile_service.names())
        self.profile_name.setCurrentText(current or profile.name)
        self.profile_name.blockSignals(False)

    def _capture_material_point(self, point_index: int) -> None:
        try:
            x, y = self.app_controller.current_position()
        except Exception as exc:  # noqa: BLE001 - user-facing hardware state
            self.log(str(exc))
            QMessageBox.critical(self, "Material einmessen", str(exc))
            return
        self.material_points[point_index] = (x, y) # type: ignore
        self.material_point_a = self.material_points[1]
        self.material_point_b = self.material_points[2]
        self._update_material_measurement_label()

    def _apply_material_measurement(self) -> None:
        points = [point for point in self.material_points.values() if point is not None]
        if len(points) < 2:
            QMessageBox.warning(self, "Material einmessen", "Bitte mindestens zwei Ecken setzen.")
            return
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if width <= 0 or height <= 0:
            QMessageBox.warning(self, "Material einmessen", "Die gesetzten Ecken ergeben keine gueltige Flaeche.")
            return
        self.work_width.setValue(width)
        self.work_height.setValue(height)
        self.material_db_width.setValue(width)
        self.material_db_height.setValue(height)
        self.material_measurement = {
            "points": {str(index): point for index, point in self.material_points.items() if point is not None},
            "point_a": self.material_points[1],
            "point_b": self.material_points[2],
        }
        self._update_material_measurement_label()
        self._settings_changed()

    def _update_material_measurement_label(self) -> None:
        if not any(self.material_points.values()):
            self.material_measurement_label.setText("Nicht eingemessen")
            return
        lines = []
        for index in range(1, 5):
            point = self.material_points[index]
            if point is None:
                lines.append(f"Ecke {index}: -")
            else:
                lines.append(f"Ecke {index}: X{point[0]:.1f} Y{point[1]:.1f}")
        self.material_measurement_label.setText("\n".join(lines))

    def _save_measured_material(self) -> None:
        name = self.material_db_name.currentText().strip()
        if not name:
            QMessageBox.warning(self, "Material speichern", "Bitte einen Materialnamen eingeben.")
            return
        record = {
            "name": name,
            "width_mm": self.material_db_width.value() or self.work_width.value(),
            "height_mm": self.material_db_height.value() or self.work_height.value(),
            "points": {str(index): point for index, point in self.material_points.items() if point is not None},
            "point_a": self.material_point_a,
            "point_b": self.material_point_b,
            "material_shape": self.material_shape.currentText(),
            "job_origin": self.job_origin.currentText(),
        }
        self.material_db_records = upsert_material(record)
        self._refresh_material_db_combo()
        self.log(f"Material gespeichert: {name}")

    def _select_material_record(self) -> None:
        record = find_material(self.material_db_selection.currentText())
        if record:
            self.material_db_name.setCurrentText(record.get("name", ""))
            self.material_db_width.setValue(float(record.get("width_mm", 0)))
            self.material_db_height.setValue(float(record.get("height_mm", 0)))
            self.material_shape.setCurrentText(record.get("material_shape", MATERIAL_SHAPE_RECTANGLE))
            self.job_origin.setCurrentText(record.get("job_origin", JOB_ORIGIN_LOWER_LEFT))

    def _load_measured_material(self) -> None:
        record = find_material(self.material_db_selection.currentText())
        if not record:
            return
        self.work_width.setValue(float(record.get("width_mm", self.work_width.value())))
        self.work_height.setValue(float(record.get("height_mm", self.work_height.value())))
        self.material_shape.setCurrentText(record.get("material_shape", MATERIAL_SHAPE_RECTANGLE))
        self.job_origin.setCurrentText(record.get("job_origin", JOB_ORIGIN_LOWER_LEFT))
        raw_points = record.get("points") or {}
        self.material_points = {1: None, 2: None, 3: None, 4: None}
        for key, value in raw_points.items():
            index = int(key)
            if index in self.material_points and value:
                self.material_points[index] = tuple(value) # type: ignore
        if not raw_points:
            self.material_points[1] = tuple(record["point_a"]) if record.get("point_a") else None # type: ignore
            self.material_points[2] = tuple(record["point_b"]) if record.get("point_b") else None # type: ignore
        self.material_point_a = self.material_points[1]
        self.material_point_b = self.material_points[2]
        self.material_measurement = {
            "points": {str(index): point for index, point in self.material_points.items() if point is not None},
            "point_a": self.material_point_a,
            "point_b": self.material_point_b,
        }
        self._update_material_measurement_label()
        self._settings_changed()
        self.log(f"Material geladen: {record.get('name', '')}")

    def _refresh_material_db_combo(self) -> None:
        names = [item.get("name", "") for item in self.material_db_records]
        self.material_db_selection.blockSignals(True)
        self.material_db_selection.clear()
        self.material_db_selection.addItems(names)
        self.material_db_selection.blockSignals(False)
        self.material_db_name.clear()
        self.material_db_name.addItems(names)

    def _delete_measured_material(self) -> None:
        name = self.material_db_selection.currentText()
        if not name:
            return
        self.material_db_records = delete_material(name)
        self._refresh_material_db_combo()
        self.log(f"Material geloescht: {name}")

    def _apply_svg_placement(self) -> None:
        if self._transform_ui_updating:
            return
        if not self.original_imported_paths and self.original_raster_source is None:
            if hasattr(self, "svg_size_label"):
                self.svg_size_label.setText("Motiv: keine Datei")
            return
        try:
            source_width, source_height = self._original_artwork_size()
            rotation = self.artwork_transform.rotation_deg if self.artwork_transform is not None else self.artwork_rotation.value()
            if self.svg_auto.isChecked():
                margin = self.svg_margin.value()
                unit_transform = ArtworkTransform(
                    x_mm=0.0,
                    y_mm=0.0,
                    scale=1.0,
                    original_width_mm=source_width,
                    original_height_mm=source_height,
                    current_width_mm=source_width,
                    current_height_mm=source_height,
                    rotation_deg=rotation,
                )
                if self.material_shape.currentText() == MATERIAL_SHAPE_CIRCLE:
                    box_x, box_y, box_width, box_height = self._material_fit_box()
                    autofit = self.autofit_service.fit(
                        unit_transform.current_width_mm,
                        unit_transform.current_height_mm,
                        box_width,
                        box_height,
                        margin,
                    )
                    self.autofit_result = replace(
                        autofit,
                        offset_x_mm=autofit.offset_x_mm + box_x,
                        offset_y_mm=autofit.offset_y_mm + box_y,
                    )
                else:
                    self.autofit_result = self.autofit_service.fit(
                        unit_transform.current_width_mm,
                        unit_transform.current_height_mm,
                        self.work_width.value(),
                        self.work_height.value(),
                        margin,
                    )
                transform = ArtworkTransform(
                    x_mm=self.autofit_result.offset_x_mm,
                    y_mm=self.autofit_result.offset_y_mm,
                    scale=self.autofit_result.scale_factor,
                    original_width_mm=source_width,
                    original_height_mm=source_height,
                    current_width_mm=self.autofit_result.current_width_mm,
                    current_height_mm=self.autofit_result.current_height_mm,
                    rotation_deg=rotation,
                    autofit_applied=self.autofit_result.applied,
                )
            else:
                current = self.artwork_transform or ArtworkTransform(
                    x_mm=0.0,
                    y_mm=0.0,
                    scale=1.0,
                    original_width_mm=source_width,
                    original_height_mm=source_height,
                    current_width_mm=source_width,
                    current_height_mm=source_height,
                )
                transform = ArtworkTransform(
                    x_mm=self.svg_offset_x.value(),
                    y_mm=self.svg_offset_y.value(),
                    scale=self.artwork_scale_percent.value() / 100.0,
                    original_width_mm=source_width,
                    original_height_mm=source_height,
                    current_width_mm=self.svg_manual_width.value(),
                    current_height_mm=self.artwork_height.value(),
                    rotation_deg=self.artwork_rotation.value(),
                    autofit_applied=False,
                    aspect_locked=self.artwork_keep_aspect.isChecked(),
                    scale_x=current.scale_x,
                    scale_y=current.scale_y,
                    uniform_scale=self.artwork_scale_percent.value() / 100.0 if self.artwork_keep_aspect.isChecked() else None,
                    keep_aspect_ratio=self.artwork_keep_aspect.isChecked(),
                )
            self._commit_artwork_transform(transform)
        except ValueError as exc:
            self.log(str(exc))
    
    def _commit_artwork_transform(self, transform: ArtworkTransform) -> None:
        transform.validate()
        self.artwork_transform = transform
        selected_item = self._selected_artwork_item()
        if selected_item is not None:
            selected_item.transform = transform
            selected_item.source_data["transform"] = transform_to_dict(transform)
        bounds = transform.bounds
        if self.original_imported_paths:
            self.imported_paths = transform_paths(self.original_imported_paths, transform)
            if isinstance(self.artwork_source, VectorArtworkSource):
                self.artwork_source = replace(
                    self.artwork_source,
                    transform=transform,
                    width_mm=transform.current_width_mm,
                    height_mm=transform.current_height_mm,
                    bounding_box=(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y),
                    paths=self.original_imported_paths,
                )
        elif self.original_raster_source is not None:
            source = replace(
                self.original_raster_source,
                transform=transform,
                width_mm=transform.current_width_mm,
                height_mm=transform.current_height_mm,
                bounding_box=(bounds.min_x, bounds.min_y, bounds.max_x, bounds.max_y),
                raster_resolution_mm=transform.current_width_mm / self.original_raster_source.pixel_width
                if self.original_raster_source.pixel_width
                else None,
            )
            self.raster_sources = [source]
            self.artwork_source = source
        self._sync_transform_controls()
        if hasattr(self, "preview_position_label") and self.preview.artwork_selected:
            self.preview_position_label.setText(
                f"Motiv ausgewaehlt | X: {transform.x_mm:.1f} mm | Y: {transform.y_mm:.1f} mm"
            )
        self._set_svg_size_label(transform.current_width_mm, transform.current_height_mm)
        self._refresh_gcode()
        self._draw_preview()

    def _sync_transform_controls(self) -> None:
        transform = self.artwork_transform
        if transform is None:
            return
        self._transform_ui_updating = True
        try:
            controls = (
                (self.svg_offset_x, transform.x_mm),
                (self.svg_offset_y, transform.y_mm),
                (self.svg_manual_width, transform.current_width_mm),
                (self.artwork_height, transform.current_height_mm),
                (self.artwork_scale_percent, transform.scale_percent),
                (self.artwork_rotation, transform.rotation_deg),
            )
            for control, value in controls:
                control.blockSignals(True)
                control.setValue(value)
                control.blockSignals(False)
            self.artwork_keep_aspect.blockSignals(True)
            self.artwork_keep_aspect.setChecked(transform.keep_aspect_ratio)
            self.artwork_keep_aspect.blockSignals(False)
        finally:
            self._transform_ui_updating = False

    def _transform_width_changed(self, width_mm: float) -> None:
        if self._transform_ui_updating or self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.with_width(width_mm, self.artwork_keep_aspect.isChecked()))

    def _transform_height_changed(self, height_mm: float) -> None:
        if self._transform_ui_updating or self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.with_height(height_mm, self.artwork_keep_aspect.isChecked()))

    def _transform_scale_changed(self, percent: float) -> None:
        if self._transform_ui_updating or self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.with_scale_percent(percent))

    def _transform_rotation_changed(self, rotation_deg: float) -> None:
        if self._transform_ui_updating or self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.with_rotation(rotation_deg))

    def _transform_position_changed(self) -> None:
        if self._transform_ui_updating or self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(
            self.artwork_transform.with_position(self.svg_offset_x.value(), self.svg_offset_y.value())
        )

    def _transform_aspect_changed(self, locked: bool) -> None:
        if self._transform_ui_updating or self.artwork_transform is None:
            return
        if locked:
            self._commit_artwork_transform(self.artwork_transform.with_scale_percent(self.artwork_transform.scale_percent))

    def _rotate_artwork(self, delta_deg: float) -> None:
        if self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.with_rotation(self.artwork_transform.rotation_deg + delta_deg))

    def _center_artwork(self) -> None:
        if self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(
            self.artwork_transform.centered_in(self.work_width.value(), self.work_height.value())
        )

    def _place_artwork_lower_left(self) -> None:
        if self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.with_position(0.0, 0.0))

    def _restore_artwork_original_size(self) -> None:
        if self.artwork_transform is None:
            return
        self.svg_manual.setChecked(True)
        self._commit_artwork_transform(self.artwork_transform.original_size())

    def _original_artwork_size(self) -> tuple[float, float]:
        if self.original_imported_paths:
            return self._source_dimensions_from_paths()
        if self.original_raster_source is not None:
            return self.original_raster_source.width_mm, self.original_raster_source.height_mm
        raise ValueError("Keine Motivquelle geladen.")

    def _source_dimensions_from_paths(self) -> tuple[float, float]:
        min_x, min_y, max_x, max_y = path_bounds(self.original_imported_paths)
        width = max_x - min_x
        height = max_y - min_y
        if width <= 0 or height <= 0:
            raise ValueError("Motiv-Bounding-Box ist ungueltig.")
        return width, height

    def _fit_svg_to_material(self) -> None:
        self.svg_auto.setChecked(True)
        self._apply_svg_placement()

    def _material_fit_box(self) -> tuple[float, float, float, float]:
        width = self.work_width.value()
        height = self.work_height.value()
        if self.material_shape.currentText() == MATERIAL_SHAPE_CIRCLE:
            diameter = min(width, height)
            return (width - diameter) / 2, (height - diameter) / 2, diameter, diameter
        return 0.0, 0.0, width, height

    def _set_svg_size_label(self, width_mm: float, height_mm: float, source_label: str = "Motiv") -> None:
        if not hasattr(self, "svg_size_label"):
            return
        self.svg_size_label.setText(
            f"{source_label}: {width_mm:.1f} x {height_mm:.1f} mm | Material: "
            f"{self.work_width.value():.1f} x {self.work_height.value():.1f} mm | "
            f"Form: {self.material_shape.currentText()} | Ursprung: {self.job_origin.currentText()}"
        )

    def _svg_placement_data(self) -> dict:
        return {
            "mode": "Automatisch" if self.svg_auto.isChecked() else "Manuell",
            "margin": self.svg_margin.value(),
            "manual_width": self.svg_manual_width.value(),
            "manual_height": self.artwork_height.value(),
            "scale_percent": self.artwork_scale_percent.value(),
            "rotation_deg": self.artwork_rotation.value(),
            "keep_aspect_ratio": self.artwork_keep_aspect.isChecked(),
            "offset_x": self.svg_offset_x.value(),
            "offset_y": self.svg_offset_y.value(),
            "material_shape": self.material_shape.currentText(),
            "job_origin": self.job_origin.currentText(),
        }

    def _artwork_source_to_project(self) -> dict | None:
        source = getattr(self, "artwork_source", None)
        if source is None:
            return None
        data = {
            "source_id": source.source_id,
            "file_path": source.file_path,
            "file_name": source.file_name,
            "source_type": source.source_type.value,
            "width_mm": source.width_mm,
            "height_mm": source.height_mm,
            "bounding_box": list(source.bounding_box),
            "import_warnings": list(source.import_warnings),
        }
        if self.autofit_result is not None:
            data["autofit"] = {
                "original_width_mm": self.autofit_result.original_width_mm,
                "original_height_mm": self.autofit_result.original_height_mm,
                "current_width_mm": self.autofit_result.current_width_mm,
                "current_height_mm": self.autofit_result.current_height_mm,
                "scale_factor": self.autofit_result.scale_factor,
                "scale_percent": self.autofit_result.scale_percent,
                "offset_x_mm": self.autofit_result.offset_x_mm,
                "offset_y_mm": self.autofit_result.offset_y_mm,
                "position": self.autofit_result.position,
                "applied": self.autofit_result.applied,
            }
        transform = getattr(source, "transform", None) or self.artwork_transform
        if transform is not None:
            data["transform"] = {
                "x_mm": transform.x_mm,
                "y_mm": transform.y_mm,
                "scale": transform.scale,
                "scale_x": transform.scale_x,
                "scale_y": transform.scale_y,
                "uniform_scale": transform.uniform_scale,
                "rotation_deg": transform.rotation_deg,
                "original_width_mm": transform.original_width_mm,
                "original_height_mm": transform.original_height_mm,
                "current_width_mm": transform.current_width_mm,
                "current_height_mm": transform.current_height_mm,
                "autofit_applied": transform.autofit_applied,
                "aspect_locked": transform.aspect_locked,
                "keep_aspect_ratio": transform.keep_aspect_ratio,
                "origin_mode": transform.origin_mode,
            }
        if isinstance(source, RasterImageSource):
            data.update(
                {
                    "pixel_width": source.pixel_width,
                    "pixel_height": source.pixel_height,
                    "dpi": list(source.dpi) if source.dpi else None,
                    "raster_resolution_mm": source.raster_resolution_mm,
                }
            )
        return data

    def _transform_from_project(self, data: dict) -> ArtworkTransform:
        transform = ArtworkTransform(
            x_mm=float(data.get("x_mm", 0.0)),
            y_mm=float(data.get("y_mm", 0.0)),
            scale=float(data.get("scale", 1.0)),
            rotation_deg=float(data.get("rotation_deg", 0.0)),
            original_width_mm=float(data.get("original_width_mm", 1.0)),
            original_height_mm=float(data.get("original_height_mm", 1.0)),
            current_width_mm=float(data.get("current_width_mm", 1.0)),
            current_height_mm=float(data.get("current_height_mm", 1.0)),
            autofit_applied=bool(data.get("autofit_applied", False)),
            aspect_locked=bool(data.get("aspect_locked", True)),
            scale_x=float(data["scale_x"]) if data.get("scale_x") is not None else None,
            scale_y=float(data["scale_y"]) if data.get("scale_y") is not None else None,
            uniform_scale=float(data["uniform_scale"]) if data.get("uniform_scale") is not None else None,
            keep_aspect_ratio=bool(data.get("keep_aspect_ratio", data.get("aspect_locked", True))),
            origin_mode=str(data.get("origin_mode", "lower_left")),
        )
        transform.validate()
        return transform

    def _trigger_machine_action(self, action_id: str, source: str = "UI") -> None:
        definition = self.machine_action_registry.get(action_id)
        details = f"action_id={definition.action_id}; quelle={source}"
        if definition.machine_action is not None and not self.app_controller.require_action(
            definition.machine_action,
            definition.label,
        ):
            self.workflow.record_action("Maschinenaktion blockiert", MachineLogStatus.WARNING, f"{details}; ergebnis=blockiert")
            QMessageBox.warning(self, "Aktion blockiert", f"'{definition.label}' ist im aktuellen Maschinenzustand nicht erlaubt.")
            self._sync_connection_indicator()
            return
        try:
            self._dispatch_machine_action(action_id)
            self.workflow.record_action("Maschinenaktion ausgefuehrt", MachineLogStatus.INFO, f"{details}; ergebnis=ausgefuehrt")
        except Exception as exc:  # noqa: BLE001 - user-facing action dispatch
            self.workflow.record_action("Maschinenaktion fehlgeschlagen", MachineLogStatus.ERROR, f"{details}; ergebnis=fehlgeschlagen", str(exc))
            raise

    def _dispatch_machine_action(self, action_id: str) -> None:
        if action_id == "connect":
            self._run_worker(lambda: self.workflow.run_machine_action("Verbindung herstellen", self.app_controller.connect))
        elif action_id == "disconnect":
            self._run_worker(
                lambda: self.workflow.run_machine_action("Verbindung trennen", self.app_controller.disconnect),
                allow_while_busy=True,
            )
        elif action_id == "refresh_ports":
            self._refresh_ports()
        elif action_id == "detect_laser":
            self._auto_detect_laser()
        elif action_id == "home":
            self._run_worker(lambda: self.workflow.run_machine_action("Homing", self.app_controller.home))
        elif action_id == "status":
            self._query_status()
        elif action_id == "settings":
            self._query_settings()
        elif action_id == "toggle_alignment":
            target = bool(getattr(self, "alignment_button", None) and self.alignment_button.isChecked())
            self._run_worker(
                lambda: self.workflow.run_machine_action(
                    "Material ausrichten",
                    lambda: self.app_controller.toggle_alignment_mode(target),
                ),
                allow_while_busy=True,
            )
        elif action_id == "toggle_work_area_trace":
            target = bool(getattr(self, "work_area_trace_button", None) and self.work_area_trace_button.isChecked())
            self._run_worker(
                lambda: self.workflow.run_machine_action(
                    "Arbeitsflaeche abfahren",
                    lambda: self._toggle_work_area_trace_from_ui(target),
                ),
                allow_while_busy=True,
            )
        elif action_id == "jog_y_plus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen Y+", lambda: self.app_controller.jog(0, 10, "Position setzen Y+")))
        elif action_id == "jog_x_minus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen X-", lambda: self.app_controller.jog(-10, 0, "Position setzen X-")))
        elif action_id == "jog_x_plus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen X+", lambda: self.app_controller.jog(10, 0, "Position setzen X+")))
        elif action_id == "jog_y_minus":
            self._run_worker(lambda: self.workflow.run_machine_action("Position setzen Y-", lambda: self.app_controller.jog(0, -10, "Position setzen Y-")))
        elif action_id == "frame":
            self._frame_job()
        elif action_id == "dry_run":
            self._dry_run_job()
        elif action_id == "start_job":
            self._start_job()
        elif action_id == "pause":
            self._run_worker(lambda: self.workflow.run_machine_action("Job pausieren", self.app_controller.pause), allow_while_busy=True)
        elif action_id == "resume":
            self._run_worker(lambda: self.workflow.run_machine_action("Job fortsetzen", self.app_controller.resume), allow_while_busy=True)
        elif action_id == "stop":
            self._run_worker(
                lambda: self.workflow.run_machine_action("Job stoppen", self.app_controller.stop),
                allow_while_busy=True,
            )
        elif action_id == "emergency_stop":
            self._run_worker(
                lambda: self.workflow.run_machine_action("Sicherheitsstopp", self.app_controller.emergency_stop),
                allow_while_busy=True,
            )
        else:
            raise RuntimeError(f"Unbekannte Maschinenaktion: {action_id}")

    def _run_worker(self, action, allow_while_busy: bool = False) -> None:
        if self._closing:
            self.log("App wird beendet; keine neue Maschinenaktion gestartet.")
            return
        if self.worker_busy and not allow_while_busy:
            self.log("Bitte warten, bis die aktuelle Aktion abgeschlossen ist.")
            return
        counted_worker = not allow_while_busy
        if counted_worker:
            self.worker_busy = True
            self._set_progress("Laeuft", 0, 1)

        def target() -> None:
            try:
                action()
            except Exception as exc:  # noqa: BLE001 - report worker failures to UI
                self.signals.error.emit(str(exc))
            finally:
                self.signals.finished.emit(counted_worker)

        thread = threading.Thread(target=target, daemon=True)
        self._worker_threads.append(thread)
        thread.start()

    def _threadsafe_log(self, message: str) -> None:
        self.signals.log.emit(message)

    def _threadsafe_progress(self, label: str, current: int, total: int) -> None:
        self.signals.progress.emit(label, current, total)

    def _show_worker_error(self, message: str) -> None:
        self.log(message)
        QMessageBox.critical(self, "Fehler", message)

    def _worker_finished(self, counted_worker: bool) -> None:
        if counted_worker:
            self.worker_busy = False
        self._worker_threads = [thread for thread in self._worker_threads if thread.is_alive()]
        self._sync_connection_indicator()

    def _sync_connection_indicator(self) -> None:
        if hasattr(self, "app_controller"):
            self.app_controller.sync_from_controller()
            if hasattr(self, "status_panel"):
                self.status_panel.update_machine_state(
                    self.app_controller.machine_state,
                    self.machine_profile.name if hasattr(self, "machine_profile") else "",
                    self.serial_port.currentText() if hasattr(self, "serial_port") else "",
                    self.app_controller.machine_state.message if self.app_controller.machine_state.phase.value in {"alarm", "error"} else "",
                    self.app_controller.job_controller.status,
                )
            self._sync_machine_action_buttons()
            if hasattr(self, "machine_panel"):
                self.machine_panel.update_state(self.app_controller.machine_state)
                self._update_workflow_status()
                self._update_assistant_panel()
                return
        state = getattr(self.controller, "state", None)
        self._set_connection_indicator(bool(state and state.connected))

    def _sync_machine_action_buttons(self) -> None:
        if not hasattr(self, "machine_action_registry"):
            return
        state = self.app_controller.machine_state
        has_motif = self._has_loaded_motif() if hasattr(self, "laser_project") else False
        for action_id, buttons in self.action_buttons.items():
            enabled = self.machine_action_registry.is_enabled(action_id, state)
            if action_id in {"frame", "dry_run", "start_job"} and not has_motif:
                enabled = False
            definition = self.machine_action_registry.get(action_id)
            for button in buttons:
                button.setEnabled(enabled)
                if action_id in {"frame", "dry_run", "start_job"} and not has_motif:
                    button.setToolTip(f"{definition.tooltip} Motiv importieren, bevor diese Aktion verfuegbar ist.")
                else:
                    button.setToolTip(definition.tooltip)
        self._sync_alignment_indicator()
        self._sync_work_area_trace_indicator()

    def _alignment_power_changed(self, value: int) -> None:
        if not hasattr(self, "app_controller"):
            return
        if self.app_controller.is_alignment_mode_active():
            self._run_worker(lambda: self.app_controller.set_alignment_pointer_power(value), allow_while_busy=True)
        else:
            self.app_controller.set_alignment_pointer_power(value)
            self._sync_alignment_indicator()

    def _sync_alignment_indicator(self) -> None:
        if not hasattr(self, "alignment_status") or not hasattr(self, "app_controller"):
            return
        active = self.app_controller.is_alignment_mode_active()
        power = self.app_controller.alignment_controller.pointer_power_percent
        self.alignment_status.setText(
            f"Ausrichtmodus aktiv - Laserpunkt aktiv, niedrige Leistung {power}%."
            if active
            else "Ausrichtmodus aus"
        )
        self.alignment_status.setStyleSheet("color: #d93025; font-weight: 700;" if active else "color: #777777;")
        if hasattr(self, "alignment_button"):
            self.alignment_button.blockSignals(True)
            self.alignment_button.setChecked(active)
            self.alignment_button.setText("Ausrichtmodus ausschalten" if active else "Material ausrichten")
            self.alignment_button.blockSignals(False)
        if hasattr(self, "alignment_power") and self.alignment_power.value() != power:
            self.alignment_power.blockSignals(True)
            self.alignment_power.setValue(power)
            self.alignment_power.blockSignals(False)

    def _sync_work_area_trace_indicator(self) -> None:
        if not hasattr(self, "work_area_trace_status") or not hasattr(self, "app_controller"):
            return
        active = self.app_controller.is_work_area_trace_active()
        if hasattr(self, "workspace_scan_panel"):
            self.workspace_scan_panel.set_active(active)
            return
        if hasattr(self, "work_area_trace_button"):
            self.work_area_trace_button.blockSignals(True)
            self.work_area_trace_button.setChecked(active)
            self.work_area_trace_button.setText("Arbeitsflaeche stoppen" if active else "Arbeitsflaeche abfahren")
            self.work_area_trace_button.blockSignals(False)

    def _toggle_work_area_trace_from_ui(self, enabled: bool) -> None:
        self.app_controller.set_current_workspace(self.work_width.value(), self.work_height.value())
        self.app_controller.set_work_area_trace_power(5)
        self.app_controller.toggle_work_area_trace(enabled)

    def _test_alignment_pointer(self) -> None:
        if not hasattr(self, "app_controller"):
            return
        self._run_worker(
            lambda: self.workflow.run_machine_action(
                "Ausrichtlaser Testmodus",
                lambda: self.app_controller.test_alignment_pointer(self.alignment_power.value(), 2.0),
            ),
            allow_while_busy=True,
        )

    def _sync_position_indicator(self) -> None:
        controller_state = getattr(getattr(self, "app_controller", None).controller, "state", None)
        if controller_state is None or not hasattr(self, "status_panel"):
            return
        state = self.app_controller.machine_state
        if getattr(controller_state, "position_source", ""):
            state.x_mm = getattr(controller_state, "x_mm", None)
            state.y_mm = getattr(controller_state, "y_mm", None)
            state.z_mm = getattr(controller_state, "z_mm", None)
            state.position_source = getattr(controller_state, "position_source", "")
            state.feed_rate = getattr(controller_state, "feed_rate", None)
            state.spindle_value = getattr(controller_state, "spindle_value", None)
        self.status_panel.update_machine_state(
            state,
            self.machine_profile.name if hasattr(self, "machine_profile") else "",
            self.serial_port.currentText() if hasattr(self, "serial_port") else "",
            job_state=self.app_controller.job_controller.status,
        )
        if hasattr(self, "preview"):
            self.preview.preview_model = replace(
                self.preview.preview_model,
                head_position=self._preview_head_position(),
                options=self._preview_options(),
            )
            self.preview.update()

    def _set_connection_indicator(self, connected: bool) -> None:
        self.connection_label.setText("Verbunden" if connected else "Nicht verbunden")
        color = "#188038" if connected else "#d93025"
        self.connection_label.setStyleSheet(f"color: {color}; font-weight: 600;")

    def _set_progress(self, label: str, current: int, total: int) -> None:
        self.status_panel.set_progress(label, current, total)
        if hasattr(self, "app_controller") and not self._closing:
            self._sync_position_indicator()

    def log(self, message: str) -> None:
        self.status_panel.set_message(message)
        self.console_log_panel.append(message)
        self.diagnostic_log.app(message)

    def _theme_tokens(self, dark: bool) -> dict[str, str]:
        if dark:
            return {
                "window": "#1b1c1f",
                "sidebar": "#202226",
                "workspace": "#1f2125",
                "panel": "#272a2f",
                "panel_alt": "#2d3036",
                "panel_border": "#464b54",
                "panel_highlight": "#383d45",
                "text": "#f2f3f5",
                "muted": "#aab0b8",
                "disabled_text": "#7d838c",
                "input": "#202329",
                "input_border": "#515762",
                "input_focus": "#6f9be8",
                "button": "#30343b",
                "button_hover": "#383d45",
                "button_pressed": "#262a30",
                "button_border": "#5a606a",
                "button_top": "#6a707a",
                "button_bottom": "#22252a",
                "blue": "#4d8dff",
                "green": "#188038",
                "green_dark": "#126a2e",
                "orange": "#d28a1d",
                "red": "#b3261e",
                "red_text": "#ffdad6",
                "table_grid": "#424750",
                "selection": "#294f82",
                "empty_border": "#5a606a",
            }
        return {
            "window": "#f3f5f8",
            "sidebar": "#e9edf2",
            "workspace": "#f7f8fa",
            "panel": "#ffffff",
            "panel_alt": "#f3f5f8",
            "panel_border": "#c5cbd4",
            "panel_highlight": "#ffffff",
            "text": "#202124",
            "muted": "#5f6670",
            "disabled_text": "#8a9099",
            "input": "#ffffff",
            "input_border": "#c3cad4",
            "input_focus": "#2563eb",
            "button": "#f8fafc",
            "button_hover": "#eef3fb",
            "button_pressed": "#e2e8f0",
            "button_border": "#b8c0cc",
            "button_top": "#ffffff",
            "button_bottom": "#cbd3de",
            "blue": "#2563eb",
            "green": "#188038",
            "green_dark": "#126a2e",
            "orange": "#b06000",
            "red": "#d93025",
            "red_text": "#8b1a10",
            "table_grid": "#d8dde3",
            "selection": "#dbeafe",
            "empty_border": "#c8cdd3",
        }

    def _build_stylesheet(self, tokens: dict[str, str]) -> str:
        return f"""
            QMainWindow {{
                background: {tokens["window"]};
                color: {tokens["text"]};
                font-size: 10pt;
            }}
            QWidget {{
                background: {tokens["workspace"]};
                color: {tokens["text"]};
                selection-background-color: {tokens["selection"]};
            }}
            QDialog {{
                background: {tokens["panel"]};
                border: 1px solid {tokens["panel_highlight"]};
                border-radius: 8px;
            }}
            QFrame#workflowStrip {{
                background: {tokens["panel"]};
                border: 1px solid {tokens["panel_border"]};
                border-top-color: {tokens["panel_highlight"]};
                border-bottom-color: {tokens["button_bottom"]};
                border-radius: 7px;
            }}
            QGroupBox {{
                background: {tokens["panel"]};
                border: 1px solid {tokens["panel_border"]};
                border-top-color: {tokens["panel_highlight"]};
                border-bottom-color: {tokens["button_bottom"]};
                border-radius: 7px;
                margin-top: 13px;
                padding: 12px 9px 9px 9px;
                font-weight: 650;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 11px;
                padding: 0 6px;
                color: {tokens["text"]};
                background: {tokens["workspace"]};
            }}
            QGroupBox#sidebarSection {{
                background: {tokens["panel_alt"]};
                border: 1px solid {tokens["panel_border"]};
                border-left: 2px solid {tokens["panel_highlight"]};
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
            }}
            QGroupBox#sidebarSection::title {{
                font-size: 13px;
                font-weight: 800;
                left: 10px;
                padding: 0 6px;
                background: {tokens["sidebar"]};
            }}
            QPushButton {{
                background: {tokens["button"]};
                color: {tokens["text"]};
                border: 1px solid {tokens["button_border"]};
                border-top-color: {tokens["button_top"]};
                border-bottom-color: {tokens["button_bottom"]};
                border-radius: 6px;
                padding: 7px 10px;
                min-height: 22px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {tokens["button_hover"]};
                border-color: {tokens["blue"]};
            }}
            QPushButton:pressed {{
                background: {tokens["button_pressed"]};
                border-top-color: {tokens["button_bottom"]};
                border-bottom-color: {tokens["button_top"]};
                padding-top: 8px;
                padding-bottom: 6px;
            }}
            QPushButton:disabled {{
                color: {tokens["disabled_text"]};
                background: {tokens["button_pressed"]};
                border-color: {tokens["panel_border"]};
            }}
            QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QTextEdit {{
                background: {tokens["input"]};
                color: {tokens["text"]};
                border: 1px solid {tokens["input_border"]};
                border-top-color: {tokens["button_bottom"]};
                border-bottom-color: {tokens["panel_highlight"]};
                border-radius: 5px;
                padding: 6px;
                selection-background-color: {tokens["selection"]};
            }}
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover, QTextEdit:hover {{
                border-color: {tokens["button_border"]};
            }}
            QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus, QTextEdit:focus {{
                border: 1px solid {tokens["input_focus"]};
            }}
            QComboBox::drop-down {{
                border-left: 1px solid {tokens["panel_border"]};
                width: 22px;
            }}
            QCheckBox {{
                spacing: 8px;
                min-height: 26px;
                color: {tokens["text"]};
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border: 1px solid {tokens["input_border"]};
                border-radius: 3px;
                background: {tokens["input"]};
            }}
            QCheckBox::indicator:hover {{
                border-color: {tokens["blue"]};
            }}
            QCheckBox::indicator:checked {{
                background: {tokens["blue"]};
                border-color: {tokens["blue"]};
            }}
            QTableWidget {{
                background: {tokens["input"]};
                alternate-background-color: {tokens["panel_alt"]};
                gridline-color: {tokens["table_grid"]};
                border: 1px solid {tokens["panel_border"]};
                border-radius: 6px;
            }}
            QTableWidget::item {{
                padding: 4px;
            }}
            QTableWidget::item:selected {{
                background: {tokens["selection"]};
                color: {tokens["text"]};
                border-left: 2px solid {tokens["blue"]};
            }}
            QHeaderView::section {{
                background: {tokens["panel_alt"]};
                color: {tokens["muted"]};
                border: 0;
                border-bottom: 1px solid {tokens["panel_border"]};
                padding: 5px;
                font-weight: 700;
            }}
            QTabWidget::pane {{
                border: 1px solid {tokens["panel_border"]};
                border-radius: 6px;
                background: {tokens["panel"]};
            }}
            QTabBar::tab {{
                background: {tokens["panel_alt"]};
                border: 1px solid {tokens["panel_border"]};
                padding: 6px 10px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }}
            QTabBar::tab:selected {{
                background: {tokens["panel"]};
                border-bottom-color: {tokens["panel"]};
                color: {tokens["blue"]};
            }}
            QScrollArea {{
                border: 0;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {tokens["sidebar"]};
                width: 10px;
                margin: 2px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {tokens["panel_border"]};
                min-height: 28px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {tokens["button_border"]};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QProgressBar {{
                background: {tokens["input"]};
                border: 1px solid {tokens["panel_border"]};
                border-radius: 5px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {tokens["blue"]};
                border-radius: 4px;
            }}
            QLabel#machineConnectionStatus {{
                font-size: 13px;
                font-weight: 800;
            }}
            #leftSidebar, #rightSidebar {{
                background: {tokens["sidebar"]};
                border: 1px solid {tokens["panel_border"]};
                border-top-color: {tokens["panel_highlight"]};
                border-radius: 8px;
            }}
            #leftSidebar {{
                border-right: 1px solid {tokens["button_bottom"]};
            }}
            #rightSidebar {{
                border-left: 1px solid {tokens["panel_highlight"]};
            }}
            #workflowHint {{
                color: {tokens["muted"]};
                font-weight: 700;
                letter-spacing: 0px;
            }}
            #workflowStatus, #projectSummary, #materialSummary, #previewPosition {{
                background: {tokens["panel"]};
                color: {tokens["muted"]};
                padding: 7px;
                border: 1px solid {tokens["panel_border"]};
                border-radius: 6px;
            }}
            #jobSummary {{
                background: {tokens["panel_alt"]};
                color: {tokens["text"]};
                font-weight: 700;
                padding: 7px;
                border: 1px solid {tokens["panel_border"]};
                border-left: 2px solid {tokens["blue"]};
                border-radius: 6px;
            }}
            #assistantSummary, #projectEmptyState, #layerEmptyState {{
                color: {tokens["muted"]};
                padding: 7px;
                border: 1px dashed {tokens["empty_border"]};
                border-radius: 6px;
                background: {tokens["panel_alt"]};
            }}
            #machineAction_frame {{
                border-color: {tokens["blue"]};
                font-weight: 700;
            }}
            #machineAction_start_job {{
                background: {tokens["green"]};
                color: #ffffff;
                border-color: {tokens["green_dark"]};
                border-top-color: #35a25b;
                border-bottom-color: #0f5524;
                font-weight: 800;
            }}
            #machineAction_start_job:hover {{
                background: #20924a;
            }}
            #machineAction_start_job:disabled {{
                background: {tokens["button_pressed"]};
                color: {tokens["disabled_text"]};
                border-color: {tokens["panel_border"]};
            }}
            #machineAction_stop {{
                border-color: {tokens["red"]};
                color: {tokens["red_text"]};
                font-weight: 800;
            }}
            #machineAction_emergency_stop {{
                background: {tokens["red"]};
                border-color: {tokens["red_text"]};
                border-bottom-color: #6f1712;
                color: #ffffff;
                font-weight: 900;
            }}
        """

    def _apply_theme(self, dark: bool) -> None:
        self.dark_mode_enabled = dark
        if hasattr(self, "theme_switch"):
            self.theme_switch.setText("Dark" if dark else "Light")
        tokens = self._theme_tokens(dark)
        self.setStyleSheet(self._build_stylesheet(tokens))
        if hasattr(self, "preview"):
            if dark:
                self.preview.background_color = QColor(tokens["window"])
                self.preview.material_surface_color = QColor("#262a30")
                self.preview.material_shadow_color = QColor("#14161a")
                self.preview.grid_color = QColor("#393e46")
                self.preview.border_color = QColor("#777e89")
                self.preview.path_color = QColor("#ff6b5f")
                self.preview.safe_area_color = QColor(tokens["blue"])
                self.preview.origin_color = QColor("#6dd47e")
                self.preview.head_color = QColor(tokens["red"])
                self.preview.head_ring_color = QColor("#f2f3f5")
            else:
                self.preview.background_color = QColor(tokens["workspace"])
                self.preview.material_surface_color = QColor("#ffffff")
                self.preview.material_shadow_color = QColor("#d4dae3")
                self.preview.grid_color = QColor("#dde2ea")
                self.preview.border_color = QColor("#9aa0a6")
                self.preview.path_color = QColor(tokens["red"])
                self.preview.safe_area_color = QColor(tokens["blue"])
                self.preview.origin_color = QColor(tokens["green"])
                self.preview.head_color = QColor(tokens["red"])
                self.preview.head_ring_color = QColor("#ffffff")
            self.preview.update()

    def _export_profiles(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Profile exportieren", "", "JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        self.profile_service.export_profiles(path)
        self.log(f"Profile exportiert: {path}")

    def _export_diagnostics(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Diagnose exportieren", "", "Logdatei (*.log);;Alle Dateien (*.*)")
        if not path:
            return
        if not path.endswith(".log"):
            path += ".log"
        exported = self.diagnostic_log.export_to(path)
        self.log(f"Diagnose exportiert: {exported}")

    def _import_profiles(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Profile importieren", "", "JSON (*.json);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            self.profile_service.import_profiles(path)
        except Exception as exc:  # noqa: BLE001 - user-facing import error
            QMessageBox.critical(self, "Profile importieren", str(exc))
            return
        self.profile_name.clear()
        self.profile_name.addItems(self.profile_service.names())
        self._apply_mode_profile_to_controls()
        self._settings_changed()
        self.log(f"Profile importiert: {path}")

    def _export_history(self) -> None:
        path, _filter = QFileDialog.getSaveFileName(self, "Historie exportieren", "", "JSON (*.json)")
        if not path:
            return
        if not path.endswith(".json"):
            path += ".json"
        export_job_history(path)
        self.log(f"Historie exportiert: {path}")

    def _import_history(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "Historie importieren", "", "JSON (*.json);;Alle Dateien (*.*)")
        if not path:
            return
        try:
            self.job_history = import_job_history(path)
        except Exception as exc:  # noqa: BLE001 - user-facing import error
            QMessageBox.critical(self, "Historie importieren", str(exc))
            return
        self._update_assistant_panel()
        self.log(f"Historie importiert: {path}")


def run_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = LaserControlWindow()
    window.show()
    return app.exec()
