from collections.abc import Callable
from dataclasses import dataclass, field

from laser_control.gcode import CUT_MODE
from laser_control.fill_toolpath import FillToolpath
from laser_control.layers import JobLayer, active_output_layers, layer_validation_warnings
from laser_control.machine_log import MachineActionLog, MachineLogStatus
from laser_control.machine_state import MachinePhase
from laser_control.models import MaterialProfile
from laser_control.services.job_service import JobPreparation, JobService
from laser_control.start_validation import StartConditionValidator, StartValidationResult, StartValidationContext


LogFn = Callable[[str], None]


@dataclass
class JobContext:
    controller: object
    connection_mode: str
    selected_port: str
    machine_label: str
    work_width_mm: float
    work_height_mm: float
    material_profile: MaterialProfile
    operation_mode: str
    origin_label: str
    gcode: str
    layers: list[JobLayer]
    parameter_source: str = "Materialprofil/Default"
    alignment_mode_active: bool = False
    extra_warnings: list[str] = field(default_factory=list)
    extra_blockers: list[str] = field(default_factory=list)
    machine_phase: str = ""
    machine_profile_name: str = "Standardmaschine"
    homing_required: bool = True
    allow_unhomed_start: bool = False
    homing_warning: str = "Start ohne Homing wurde bewusst erlaubt."
    max_speed: int | None = None
    max_power: int | None = None
    source_name: str = ""
    source_type: str = ""
    raster_gcode_available: bool = True
    autofit_applied: bool = False
    source_original_width_mm: float | None = None
    source_original_height_mm: float | None = None
    source_current_width_mm: float | None = None
    source_current_height_mm: float | None = None
    source_x_mm: float | None = None
    source_y_mm: float | None = None
    source_bounds_ok: bool | None = None
    autofit_scale_percent: float | None = None
    autofit_position: str = ""
    head_x_mm: float | None = None
    head_y_mm: float | None = None
    head_position_source: str = ""
    fill_toolpaths: list[FillToolpath] = field(default_factory=list)
    job_kind: str = "Einzelstueck"
    auto_home_after_success: bool = False
    active_artwork_count: int | None = None


@dataclass
class PreflightResult:
    context: JobContext
    prepared: JobPreparation | None
    warnings: list[str]
    blockers: list[str]
    start_validation: StartValidationResult | None = None

    @property
    def can_start(self) -> bool:
        return not self.blockers and self.prepared is not None

    def start_button_enabled(self, unhomed_confirmed: bool | None = None) -> bool:
        confirmed_unhomed = self._unhomed_start_confirmed(unhomed_confirmed)
        return self.can_start and confirmed_unhomed

    def start_button_disabled_reasons(self, unhomed_confirmed: bool | None = None) -> list[str]:
        reasons: list[str] = []
        if self.prepared is None:
            reasons.append("PreparedJob fehlt.")
        if self.blockers:
            reasons.extend(self.blockers)
        if self.requires_unhomed_confirmation and not self._unhomed_start_confirmed(unhomed_confirmed):
            reasons.append("Start ohne erkannte Referenzfahrt muss bewusst bestaetigt werden.")
        return _dedupe(reasons)

    def start_condition_lines(self, unhomed_confirmed: bool | None = None) -> list[str]:
        context = self.context
        state = getattr(context.controller, "state", None)
        hardware = context.connection_mode == "GRBL ueber USB"
        active_layers = active_output_layers(context.layers)
        prepared = self.prepared
        analysis = prepared.analysis if prepared is not None else None
        machine_connected = bool(getattr(state, "connected", False))
        machine_idle = context.machine_phase == MachinePhase.IDLE.value or (not context.machine_phase and machine_connected)
        homed = bool(getattr(state, "homed", False))
        homing_ok = homed or not context.homing_required
        port_ok = bool(context.selected_port.strip()) if hardware else True
        gcode_ok = bool(context.gcode.strip())
        material_name_ok = bool(context.material_profile.name.strip())
        material_power_ok = 0 < context.material_profile.power_percent <= 100
        material_speed_ok = context.material_profile.speed_mm_min > 0
        work_area_ok = context.work_width_mm > 0 and context.work_height_mm > 0
        bounds_ok = context.source_bounds_ok is not False
        if analysis is not None and analysis.has_bounds:
            bounds_ok = bounds_ok and (
                (analysis.min_x is None or analysis.min_x >= 0)
                and (analysis.min_y is None or analysis.min_y >= 0)
                and (analysis.max_x is None or analysis.max_x <= context.work_width_mm)
                and (analysis.max_y is None or analysis.max_y <= context.work_height_mm)
            )
        validation_ok = self.start_validation.passed if self.start_validation is not None else False
        blockers_ok = not self.blockers
        prepared_ok = prepared is not None
        active_layers_ok = bool(active_layers)
        requires_unhomed = self.requires_unhomed_confirmation
        confirmed_unhomed = self._unhomed_start_confirmed(unhomed_confirmed)
        button_enabled = self.start_button_enabled(unhomed_confirmed)
        disabled_reasons = self.start_button_disabled_reasons(unhomed_confirmed)

        rows = [
            ("Maschine verbunden", (machine_connected if hardware else True), "Simulator aktiv" if not hardware else ""),
            ("Maschine idle", (machine_idle if hardware else True), context.machine_phase or "unbekannt"),
            ("Kein Alarm/Fehler", not bool(getattr(state, "alarm", False)) and context.machine_phase not in {"alarm", "error"}, ""),
            ("Homing OK", homing_ok, "optional" if not context.homing_required else ("homed" if homed else "nicht homed")),
            ("Port ausgewaehlt", port_ok, context.selected_port or "-"),
            ("Materialprofil Name", material_name_ok, context.material_profile.name or "-"),
            ("Materialprofil Leistung", material_power_ok, f"{context.material_profile.power_percent}%"),
            ("Materialprofil Geschwindigkeit", material_speed_ok, f"{context.material_profile.speed_mm_min} mm/min"),
            ("PreparedJob vorhanden", prepared_ok, ""),
            ("GCode vorhanden", gcode_ok, f"{len(context.gcode.splitlines())} Zeilen"),
            ("Aktive Layer", active_layers_ok, str(len(active_layers))),
            ("Arbeitsbereich OK", work_area_ok and bounds_ok, f"{context.work_width_mm:.1f} x {context.work_height_mm:.1f} mm"),
            ("Startvalidierung bestanden", validation_ok, self.start_validation.summary if self.start_validation else "nicht ausgefuehrt"),
            ("Keine Blocker", blockers_ok, "; ".join(self.blockers)),
            ("Frame-Test verlangt", True, "nein - nur Empfehlung"),
            ("preflight_confirmed vor Dialog", True, "nein - wird erst nach Start bestaetigen gesetzt"),
            ("Preflight bestanden", self.can_start, ""),
            (
                "Unhomed-Bestaetigung erforderlich",
                not requires_unhomed or confirmed_unhomed,
                "ja - noch nicht bestaetigt" if requires_unhomed and not confirmed_unhomed else ("ja - bestaetigt" if requires_unhomed else "nein"),
            ),
            ("Startbutton aktiviert", button_enabled, "; ".join(disabled_reasons)),
        ]
        return [_format_condition(label, passed, detail) for label, passed, detail in rows]

    def _unhomed_start_confirmed(self, unhomed_confirmed: bool | None = None) -> bool:
        if not self.requires_unhomed_confirmation:
            return True
        return bool(unhomed_confirmed)

    @property
    def active_layers(self) -> list[JobLayer]:
        return active_output_layers(self.context.layers)

    @property
    def requires_unhomed_confirmation(self) -> bool:
        state = getattr(self.context.controller, "state", None)
        return (
            self.can_start
            and not self.context.homing_required
            and not getattr(state, "homed", False)
            and getattr(state, "connected", False)
        )

    def summary_lines(self) -> list[str]:
        machine_state = getattr(self.context.controller, "state", None)
        homed = getattr(machine_state, "homed", False)
        if homed:
            homing = "Homing erfolgreich durchgefuehrt"
        elif self.context.homing_required:
            homing = "Homing erforderlich, aber nicht erkannt"
        else:
            homing = "Homing laut Maschinenprofil optional"
        lines = [
            f"Maschine: {self.context.machine_label}",
            f"Maschinenprofil: {self.context.machine_profile_name}",
            f"Verbindung: {self.context.connection_mode}",
            f"Port: {self.context.selected_port or '-'}",
            f"Status: {self._connection_status_label()}",
            f"Homing: {homing}",
            f"Homing erforderlich: {'ja' if self.context.homing_required else 'nein'}",
            f"Arbeitsbereich: {self.context.work_width_mm:.1f} x {self.context.work_height_mm:.1f} mm",
            f"Nullpunkt / Startposition: {self.context.origin_label}",
            f"Materialprofil: {self.context.material_profile.name}",
            f"Ausrichtmodus aktiv: {'ja - wird vor Start deaktiviert' if self.context.alignment_mode_active else 'nein'}",
            f"Job-Art: {self.context.job_kind}",
            f"Auto-Home nach Abschluss: {'Ja' if self.context.auto_home_after_success else 'Nein'}",
            (
                "Materialparameter: "
                f"{self.context.material_profile.speed_mm_min} mm/min, "
                f"{self.context.material_profile.power_percent}% Leistung, "
                f"{self.context.material_profile.passes} Durchgaenge "
                f"(Quelle: {self.context.parameter_source})"
            ),
            f"Aktive Layer: {len(self.active_layers)}",
        ]
        if self.context.head_position_source and self.context.head_x_mm is not None and self.context.head_y_mm is not None:
            lines.append(
                f"Kopfposition: {self.context.head_position_source} "
                f"X {self.context.head_x_mm:.2f} mm, Y {self.context.head_y_mm:.2f} mm"
            )
        else:
            lines.append("Kopfposition: --")
        if self.context.source_name:
            lines.append(f"Quelle: {self.context.source_name} ({self.context.source_type or 'unbekannt'})")
            if self.context.source_original_width_mm is not None and self.context.source_current_width_mm is not None:
                if self.context.autofit_applied:
                    lines.extend(
                        [
                            "AutoFit: Motiv automatisch eingepasst",
                            (
                                "Originalgroesse: "
                                f"{self.context.source_original_width_mm:.1f} x "
                                f"{self.context.source_original_height_mm:.1f} mm"
                            ),
                            (
                                "Aktuelle Groesse: "
                                f"{self.context.source_current_width_mm:.1f} x "
                                f"{self.context.source_current_height_mm:.1f} mm"
                            ),
                            (
                                "Position: "
                                f"X {self.context.source_x_mm:.1f} mm, "
                                f"Y {self.context.source_y_mm:.1f} mm"
                            )
                            if self.context.source_x_mm is not None and self.context.source_y_mm is not None
                            else f"Position: {self.context.autofit_position or 'zentriert'}",
                            f"Skalierung: {self.context.autofit_scale_percent:.1f}%",
                            f"Arbeitsbereich: {'OK' if self.context.source_bounds_ok else 'ueberschritten'}"
                            if self.context.source_bounds_ok is not None
                            else "Arbeitsbereich: nicht geprueft",
                        ]
                    )
                else:
                    lines.append("AutoFit: Motiv passt vollstaendig in den Arbeitsbereich")
                    if self.context.source_x_mm is not None and self.context.source_y_mm is not None:
                        lines.append(
                            f"Position: X {self.context.source_x_mm:.1f} mm, Y {self.context.source_y_mm:.1f} mm"
                        )
                    if self.context.source_current_width_mm is not None and self.context.source_current_height_mm is not None:
                        lines.append(
                            f"Aktuelle Groesse: {self.context.source_current_width_mm:.1f} x {self.context.source_current_height_mm:.1f} mm"
                        )
                    if self.context.autofit_scale_percent is not None:
                        lines.append(f"Skalierung: {self.context.autofit_scale_percent:.1f}%")
                    if self.context.source_bounds_ok is not None:
                        lines.append(f"Arbeitsbereich: {'OK' if self.context.source_bounds_ok else 'ueberschritten'}")
        for layer in self.active_layers:
            lines.append(
                f"- {layer.name} ({layer.layer_type.value}): "
                f"{layer.speed_mm_min} mm/min, {layer.power_percent}%, "
                f"{layer.passes} Durchgaenge, Reihenfolge {layer.order}, Modus {layer.mode.value}"
            )
            if layer.uses_fill:
                fill = next((item for item in self.context.fill_toolpaths if item.layer_order == layer.order), None)
                lines.append(f"  Fuellabstand: {layer.fill_spacing_mm:.2f} mm")
                lines.append(f"  Fuellwinkel: {layer.fill_angle_deg} deg")
                lines.append(
                    f"  Geschlossene Flaeche: {'ja' if fill and fill.closed_shape_count else 'nein'}"
                )
                lines.append(f"  Geschaetzte Fuelllinien: {fill.line_count if fill else 0}")
                if fill and fill.overscan_enabled:
                    lines.append(f"  Overscan: aktiv ({fill.overscan_mode})")
                    lines.append(f"  Berechnet: {fill.overscan_mm:.1f} mm")
                    lines.append(f"  Geschwindigkeit: {layer.speed_mm_min} mm/min")
                    lines.append(f"  Zusaetzliche Fahrstrecke: {fill.additional_travel_mm:.1f} mm")
                    additional_seconds = fill.additional_travel_mm / max(1, layer.speed_mm_min) * 60.0
                    lines.append(f"  Zusaetzliche Laufzeit: ca. {additional_seconds:.1f} s je Durchgang")
                else:
                    lines.append("  Overscan: aus")
        if self.prepared is not None:
            lines.append(f"G-Code-Zeilen: {len(self.prepared.commands)}")
            if self.prepared.analysis.has_bounds:
                lines.append(
                    "Jobgroesse: "
                    f"{self.prepared.analysis.width_mm:.1f} x {self.prepared.analysis.height_mm:.1f} mm"
                )
            lines.append(f"Geschaetzte Laufzeit: {self.prepared.analysis.estimated_runtime_label}")
        else:
            lines.append("Geschaetzte Laufzeit: nicht verfuegbar")
        lines.append("Frame-Test: vor Hardwarestart empfohlen.")
        if self.blockers:
            lines.append("Blockierende Punkte:")
            lines.extend(f"- {item}" for item in self.blockers)
        if self.warnings:
            lines.append("Warnungen:")
            lines.extend(f"- {item}" for item in self.warnings)
        if self.requires_unhomed_confirmation:
            lines.append("Bestaetigung erforderlich:")
            lines.append(f"- {self.context.homing_warning}")
        lines.append("Sicherheit: Schutzbrille tragen, Material und Arbeitsbereich pruefen.")
        return lines

    def _connection_status_label(self) -> str:
        state = getattr(self.context.controller, "state", None)
        if not state:
            return "kein Maschinenstatus"
        if getattr(state, "alarm", False):
            return "Alarm"
        if getattr(state, "paused", False):
            return "Pausiert"
        if getattr(state, "connected", False):
            return "Verbunden"
        return "Nicht verbunden"


class WorkflowController:
    def __init__(
        self,
        job_service: JobService,
        machine_log: MachineActionLog,
        log: LogFn,
        start_validator: StartConditionValidator | None = None,
    ) -> None:
        self._job_service = job_service
        self._machine_log = machine_log
        self._log = log
        self._start_validator = start_validator or StartConditionValidator()

    def record_action(
        self,
        action: str,
        status: MachineLogStatus = MachineLogStatus.INFO,
        details: str = "",
        error: str = "",
    ) -> None:
        entry = self._machine_log.record(action, status, details, error)
        self._log(entry.format())

    def prepare_preflight(self, context: JobContext) -> PreflightResult:
        self.record_action("Job vorbereitet", MachineLogStatus.INFO, "Preflight wird erstellt.")
        blockers: list[str] = list(context.extra_blockers)
        warnings = list(context.extra_warnings)
        warnings.append("Frame-Test vor Hardwarestart empfohlen.")
        warnings.extend(layer_validation_warnings(context.layers))
        for toolpath in context.fill_toolpaths:
            warnings.extend(f"Layer '{toolpath.layer_name}': {warning}" for warning in toolpath.warnings)
        fill_by_order = {toolpath.layer_order: toolpath for toolpath in context.fill_toolpaths}
        for layer in active_output_layers(context.layers):
            if not layer.uses_fill:
                continue
            toolpath = fill_by_order.get(layer.order)
            if toolpath is None:
                blockers.append(
                    f"Layer '{layer.name}': Fuellung ist aktiv, aber es wurde kein FillToolpath erzeugt."
                )
            elif getattr(toolpath, "unsafe_fill", False):
                blockers.append(
                    f"Layer '{layer.name}': SVG-Fuellung bei verschachtelten oder offenen Konturen aktuell nicht sicher unterstuetzt."
                )
            elif toolpath.closed_shape_count == 0 or toolpath.line_count == 0:
                blockers.append(
                    f"Layer '{layer.name}': Fuellung benoetigt mindestens eine geschlossene Flaeche."
                )
        # Any active raster artwork blocks the job while raster G-code is not implemented - also in
        # multi-artwork projects, where vector items would otherwise produce valid G-code and the
        # raster item would be silently skipped.
        if not context.raster_gcode_available:
            if context.source_type == "multi":
                blockers.append("Aktives Rastermotiv: Rastergravur-GCode noch nicht verfuegbar. Motiv deaktivieren oder entfernen.")
            else:
                blockers.append("Rastergravur-GCode noch nicht verfuegbar.")
        if context.active_artwork_count == 0:
            blockers.append("Kein aktives Motiv vorhanden.")
        if context.source_bounds_ok is False:
            blockers.append("Motiv liegt ausserhalb des Arbeitsbereichs.")
        if context.connection_mode == "GRBL ueber USB" and context.source_name and not context.head_position_source:
            warnings.append("Kopfposition ist unbekannt; Statusabfrage vor Hardwarestart empfohlen.")

        prepared: JobPreparation | None = None
        try:
            prepared = self._job_service.prepare_job(
                context.gcode,
                context.work_width_mm,
                context.work_height_mm,
                context.material_profile,
                context.operation_mode,
            )
            warnings.extend(prepared.warnings)
        except ValueError as exc:
            blockers.append(str(exc))

        machine_phase = context.machine_phase
        if not machine_phase:
            machine_phase = MachinePhase.IDLE.value if getattr(getattr(context.controller, "state", None), "connected", False) else MachinePhase.DISCONNECTED.value
        validation = self._start_validator.validate(
            StartValidationContext(
                connection_mode=context.connection_mode,
                machine_phase=machine_phase,
                controller_state=getattr(context.controller, "state", None),
                selected_port=context.selected_port,
                gcode=context.gcode,
                layers=context.layers,
                material_profile=context.material_profile,
                work_width_mm=context.work_width_mm,
                work_height_mm=context.work_height_mm,
                prepared=prepared,
                homing_required=context.homing_required,
                allow_unhomed_start=context.allow_unhomed_start,
                max_speed=context.max_speed,
                max_power=context.max_power,
            )
        )
        blockers.extend(validation.blocking_errors)
        warnings.extend(validation.warnings)
        warnings.extend(validation.info)

        if not context.material_profile.name.strip():
            warnings.append("Kein Materialprofil gesetzt.")

        result = PreflightResult(
            context=context,
            prepared=prepared,
            warnings=_dedupe(warnings),
            blockers=_dedupe(blockers),
            start_validation=validation,
        )
        if result.blockers:
            self.record_action("Preflight blockiert", MachineLogStatus.ERROR, "; ".join(result.blockers))
        elif result.warnings:
            self.record_action("Preflight mit Warnungen", MachineLogStatus.WARNING, "; ".join(result.warnings))
        else:
            self.record_action("Preflight bestanden", MachineLogStatus.OK)
        self.record_action(
            "Preflight Startdiagnose",
            MachineLogStatus.INFO,
            "\n".join(result.start_condition_lines()),
        )
        return result

    def run_machine_action(self, action_name: str, action: Callable[[], None], success_name: str | None = None) -> None:
        self.record_action(action_name, MachineLogStatus.INFO)
        try:
            action()
        except Exception as exc:
            self.record_action(f"{action_name} fehlgeschlagen", MachineLogStatus.ERROR, error=str(exc))
            raise
        self.record_action(success_name or f"{action_name} abgeschlossen", MachineLogStatus.OK)

    def laser_mode_label(self, operation_mode: str) -> str:
        return "M3 konstant" if operation_mode == CUT_MODE else "M4 dynamisch"


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _format_condition(label: str, passed: bool, detail: str = "") -> str:
    prefix = "[OK]" if passed else "[BLOCK]"
    suffix = f" ({detail})" if detail else ""
    return f"{prefix} {label}{suffix}"
