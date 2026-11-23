"""Materialprofile, Betriebsmodus, Ebenen und Materialvermessung."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.layers import LayerType, active_output_layers, build_default_layers
from laser_control.material_db import delete_material, find_material, upsert_material
from laser_control.models import MaterialProfile
from laser_control.profiles import DEFAULT_PROFILES
from laser_control.ui_common import JOB_ORIGIN_LOWER_LEFT, MATERIAL_SHAPE_RECTANGLE


class MaterialMixin:
    """Materialprofile, Betriebsmodus, Ebenen und Materialvermessung.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

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
