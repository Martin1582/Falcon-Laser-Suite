"""Jobvorbereitung, G-Code-Erzeugung, Preflight, Rahmen/Dry Run/Start und Job-Historie."""

from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox
from laser_control.artwork_transform import transform_paths
from laser_control.gcode import (
    build_layered_polyline_gcode,
    build_multi_item_layered_polyline_gcode,
    build_rectangle_frame_gcode,
)
from laser_control.fill_toolpath import build_layer_fill_toolpaths
from laser_control.layers import active_output_layers
from laser_control.job_history import JobHistoryEntry, append_job_history, now_timestamp
from laser_control.machine_log import MachineLogStatus
from laser_control.material_recommendations import material_deviation_warnings
from laser_control.qt_panels import PreflightDialog
from laser_control.services.job_service import JobPreparation
from laser_control.svg_optimization import SvgOptimizationResult, SvgVectorAnalysis
from laser_control.workflow_controller import JobContext
from laser_control.ui_common import JOB_ORIGIN_LOWER_LEFT, MATERIAL_SHAPE_CIRCLE


class JobMixin:
    """Jobvorbereitung, G-Code-Erzeugung, Preflight, Rahmen/Dry Run/Start und Job-Historie.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

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
            extra_blockers=self._missing_source_blockers(),
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

    def _missing_source_blockers(self) -> list[str]:
        """Active artworks whose source could not be loaded would be silently left out of the job."""
        missing = [
            item.name
            for item in self.laser_project.items
            if item.active and item.item_id not in self._item_sources
        ]
        if not missing:
            return []
        return [
            "Motivquelle nicht geladen (Datei verschoben oder geloescht?): "
            + ", ".join(missing)
            + ". Motiv neu importieren, deaktivieren oder entfernen."
        ]

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
        active_vector_items = self._active_vector_items()
        active_vectors = [(name, paths) for _item_id, name, paths in active_vector_items]
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
                    # Key fills by the unique item ID: names repeat when an SVG is placed twice.
                    code = build_multi_item_layered_polyline_gcode(
                        active_vectors,
                        layers,
                        operation_mode,
                        self._fill_toolpaths_by_item,
                        item_keys=[item_id for item_id, _name, _paths in active_vector_items],
                    )
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
