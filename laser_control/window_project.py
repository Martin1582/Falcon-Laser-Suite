"""Projekt speichern/laden sowie Import/Export von Profilen, Historie und Diagnose."""

from dataclasses import replace
from PySide6.QtWidgets import QFileDialog, QMessageBox
from laser_control.artwork_import import ArtworkSourceType, RasterImageSource, VectorArtworkSource
from laser_control.artwork_scaling import AutoFitResult
from laser_control.artwork_transform import normalize_paths, transform_paths
from laser_control.layer_compat import repair_legacy_raster_layers
from laser_control.layers import layer_from_dict, layer_to_dict
from laser_control.job_history import export_job_history, import_job_history
from laser_control.models import MaterialProfile
from laser_control.project import laser_project_from_dict, load_project, project_to_dict, save_project
from laser_control.ui_common import AUTO_FIT_MARGIN_MM, JOB_ORIGIN_LOWER_LEFT, MATERIAL_SHAPE_RECTANGLE

LEGACY_LAYER_REPAIR_MESSAGE = (
    "Dieses Projekt wurde mit einer aelteren Version gespeichert, in der ein Rasterbild die Layer "
    "veraendert hat. Die Layer wurden beim Laden korrigiert:\n\n{notes}\n\n"
    "Die Projektdatei bleibt unveraendert, bis Sie das Projekt speichern."
)


class ProjectMixin:
    """Projekt speichern/laden sowie Import/Export von Profilen, Historie und Diagnose.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

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
        self._clear_selected_artwork_state()
        self.imported_paths = data.get("imported_paths", [])
        self.original_imported_paths = self.imported_paths
        self.imported_file = data.get("imported_file")
        # Neues Projekt setzen und alle Motiv-Caches der alten IDs verwerfen.
        self.project_workspace.replace_project(laser_project_from_dict(data.get("laser_project") or {}))
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
        self._restore_svg_placement(placement)
        if self.artwork_transform is not None:
            # Show the persisted transform of the selected item (or of the legacy source).
            self._sync_transform_controls()
        elif not self.laser_project.items and self.original_imported_paths:
            # Legacy vector project without stored transform: place it once from the restored settings.
            self._apply_svg_placement()
        repair_notes = self._restore_layers(data)
        self.gcode_text.setPlainText(data.get("gcode", ""))
        self._update_material_measurement_label()
        self._draw_preview()
        self.log(f"Projekt geladen: {path}")
        if repair_notes:
            self._report_legacy_layer_repair(repair_notes)

    def _restore_layers(self, data: dict) -> list[str]:
        """Setzt die gespeicherten Layer; liefert Hinweise, falls ein Altprojekt korrigiert wurde.

        Die Korrektur wirkt nur im Speicher. Die Datei aendert sich erst beim naechsten Speichern.
        """
        if not data.get("layers"):
            self._sync_layers_from_controls(preserve_states=False)
            return []
        try:
            layers = [layer_from_dict(item) for item in data.get("layers", [])]
            repair = repair_legacy_raster_layers(layers, self.operation_mode.currentText())
            self.layer_panel.set_layers(repair.layers)
        except Exception as exc:  # noqa: BLE001 - load project should remain usable
            self.log(f"Layerdaten konnten nicht geladen werden: {exc}")
            self._sync_layers_from_controls(preserve_states=False)
            return []
        return repair.notes

    def _report_legacy_layer_repair(self, notes: list[str]) -> None:
        for note in notes:
            self.log(note)
        if self.laser_project.items:
            # Der gespeicherte G-Code beruht auf den alten Layern; Preflight und Start sollen den
            # korrigierten nutzen. Ohne Motive (z. B. gespeicherte Testmatrix) bleibt er erhalten.
            self._refresh_gcode()
        QMessageBox.information(self, "Projekt laden", LEGACY_LAYER_REPAIR_MESSAGE.format(notes="\n\n".join(notes)))

    def _restore_svg_placement(self, placement: dict) -> None:
        """Setzt die Platzierungs-Controls aus gespeicherten Daten (fehlende Schluessel: Defaults)."""
        # Restoring the controls must not feed back into the artwork: the transform handlers would
        # otherwise write the saved values (possibly of another selected item) into the item that
        # was selected on load. The persisted transforms are the source of truth.
        self._transform_ui_updating = True
        try:
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
        finally:
            self._transform_ui_updating = False

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
