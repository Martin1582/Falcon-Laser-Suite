"""Arbeitsflaechen-Vorschau-Widget (Zeichnen, Auswahl, Drag & Drop)."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import QSizePolicy, QWidget
from laser_control.artwork_import import RasterImageSource
from laser_control.artwork_interaction import ArtworkSnapService
from laser_control.preview_model import JobPreviewModel, build_preview_model
from laser_control.workspace_coordinates import WorkspaceCoordinateMapper
from laser_control.ui_common import AUTO_FIT_MARGIN_MM, JOB_ORIGIN_CENTER, JOB_ORIGIN_LOWER_LEFT, MATERIAL_SHAPE_CIRCLE, MATERIAL_SHAPE_RECTANGLE


def raster_source_image(source: RasterImageSource) -> QImage | None:
    """Build a preview QImage from the tightly packed 8-bit grayscale pixels of a raster source.

    Pillow's ``tobytes()`` has no row padding, while QImage without an explicit bytes-per-line
    assumes rows aligned to 4 bytes. For widths not divisible by 4 (e.g. 1546 px) Qt would then
    read past the end of the buffer and crash the app, so the row length is passed explicitly and
    the buffer size is checked first. ``copy()`` detaches the image from the Python buffer.
    """
    width, height = source.pixel_width, source.pixel_height
    data = source.grayscale_data
    if not data or width <= 0 or height <= 0 or len(data) != width * height:
        return None
    return QImage(data, width, height, width, QImage.Format.Format_Grayscale8).copy()


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
        image = raster_source_image(source)
        if image is None:
            return
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
