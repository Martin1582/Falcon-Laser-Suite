"""Motivimport, Objektliste, SVG-Optimierung, Platzierung und Transformation."""

from dataclasses import replace
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
    QVBoxLayout,
)
from laser_control.artwork_import import (
    ArtworkSourceType,
    RasterImageSource,
    VectorArtworkSource,
    supported_file_filter,
)
from laser_control.artwork_scaling import autofit_to_transform
from laser_control.artwork_transform import ArtworkBounds, ArtworkTransform, normalize_paths, transform_paths
from laser_control.geometry_optimizer import GeometryOptimizationOptions
from laser_control.preview_model import PreviewArtworkItem
from laser_control.project import ArtworkItem, new_item_id, transform_to_dict
from laser_control.svg_import import path_bounds
from laser_control.svg_optimization import optimize_svg_paths
from laser_control.ui_common import MATERIAL_SHAPE_CIRCLE


class ArtworkMixin:
    """Motivimport, Objektliste, SVG-Optimierung, Platzierung und Transformation.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

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

    def _has_loaded_motif(self) -> bool:
        """True when there is something to run: imported artwork or a generated job (test matrix)."""
        return bool(
            self.imported_paths
            or self.original_imported_paths
            or self.raster_sources
            or self.laser_project.items
            or self.artwork_source is not None
            or getattr(self, "_generated_job_name", None)
        )

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

    def _active_vector_items(self) -> list[tuple[str, str, list]]:
        """Active vector artworks as (unique item_id, display name, transformed paths)."""
        result: list[tuple[str, str, list]] = []
        for item in self.laser_project.items:
            if not item.active:
                continue
            paths = self._effective_item_vector_paths(item)
            if paths:
                result.append((item.item_id, item.name, transform_paths(paths, item.transform)))
        return result

    def _active_vector_item_paths(self) -> list[tuple[str, list]]:
        return [(name, paths) for _item_id, name, paths in self._active_vector_items()]

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
            self._clear_selected_artwork_state()
            self._show_empty_selection_labels()
            self._refresh_object_table()
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
            if self._selected_artwork_item() is None:
                # Nach dem Schrumpfen der Tabelle darf keine alte Zeilenauswahl stehen bleiben.
                self.object_table.clearSelection()
        finally:
            self._object_list_updating = False
        self._sync_project_edit_actions()

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
        if isinstance(source, VectorArtworkSource) and source.paths:
            # Vector paths are normalized to their geometric bounds, so the transform must use the
            # geometry size - not the SVG document size, which includes surrounding whitespace.
            min_x, min_y, max_x, max_y = path_bounds(source.paths)
            width = max(max_x - min_x, 0.01)
            height = max(max_y - min_y, 0.01)
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

    def get_transformed_bounds(self) -> ArtworkBounds:
        if getattr(self, "_generated_job_name", None):
            # A generated job (test matrix) replaces the artwork output: frame what will run.
            generated_bounds = self._gcode_bounds()
            if generated_bounds is not None:
                return generated_bounds
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
        generated_bounds = self._gcode_bounds()
        if generated_bounds is not None:
            return generated_bounds
        return ArtworkBounds(0.0, 0.0, self.work_width.value(), self.work_height.value())

    def _gcode_bounds(self) -> ArtworkBounds | None:
        """Motion bounds of the G-code currently in the editor, if it can be analysed."""
        try:
            prepared = self.job_service.prepare_job(
                self.gcode_text.toPlainText(),
                self.work_width.value(),
                self.work_height.value(),
                self._effective_job_profile(),
                self.operation_mode.currentText(),
            )
        except ValueError:
            return None
        if not prepared.analysis.has_bounds:
            return None
        return ArtworkBounds(
            prepared.analysis.min_x or 0.0,
            prepared.analysis.min_y or 0.0,
            prepared.analysis.max_x or 0.0,
            prepared.analysis.max_y or 0.0,
        )

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
