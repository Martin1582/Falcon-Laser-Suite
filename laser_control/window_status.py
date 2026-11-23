"""Zusammenfassungen, Workflow-Schritte und Assistenzpanel."""

from laser_control.services.job_service import JobPreparation


class StatusSummaryMixin:
    """Zusammenfassungen, Workflow-Schritte und Assistenzpanel.

    Mixin fuer LaserControlWindow; nutzt dessen Widgets und Services ueber self.
    """

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
