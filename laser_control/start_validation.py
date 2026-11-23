from __future__ import annotations

from dataclasses import dataclass, field

from laser_control.layers import JobLayer, active_output_layers
from laser_control.models import MaterialProfile
from laser_control.services.job_service import JobPreparation


HARDWARE_MODE = "GRBL ueber USB"


@dataclass(frozen=True)
class StartValidationContext:
    connection_mode: str
    machine_phase: str
    controller_state: object | None
    selected_port: str
    gcode: str
    layers: list[JobLayer]
    material_profile: MaterialProfile
    work_width_mm: float
    work_height_mm: float
    prepared: JobPreparation | None = None
    homing_required: bool = True
    allow_unhomed_start: bool = False
    max_speed: int | None = None
    max_power: int | None = None


@dataclass
class StartValidationResult:
    passed: bool
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        sections: list[str] = []
        if self.blocking_errors:
            sections.append("Blocker: " + "; ".join(self.blocking_errors))
        if self.warnings:
            sections.append("Warnungen: " + "; ".join(self.warnings))
        if self.info:
            sections.append("Info: " + "; ".join(self.info))
        return " | ".join(sections) if sections else "Startbedingungen erfuellt."


class StartConditionValidator:
    def validate(self, context: StartValidationContext) -> StartValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        info: list[str] = []
        state = context.controller_state
        hardware = context.connection_mode == HARDWARE_MODE
        phase = context.machine_phase or ""

        if hardware:
            if not getattr(state, "connected", False):
                errors.append("Maschine ist nicht verbunden.")
            if phase != "idle":
                errors.append(f"Maschinenzustand ist nicht idle: {phase or 'unbekannt'}.")
            if getattr(state, "paused", False):
                errors.append("Maschine ist pausiert.")
            if getattr(state, "alarm", False) or phase == "alarm":
                errors.append("Maschine meldet Alarm.")
            if phase in {"running", "stopping", "error", "connecting", "disconnected"}:
                errors.append(f"Jobstart aus Zustand {phase} ist nicht erlaubt.")
            if not getattr(state, "homed", False):
                if context.homing_required:
                    errors.append("Keine Referenzfahrt erkannt.")
                elif context.allow_unhomed_start:
                    warnings.append("Start ohne erkannte Referenzfahrt wurde durch Maschinenprofil erlaubt.")
                else:
                    warnings.append("Maschine wurde nicht referenziert; Homing ist laut Maschinenprofil optional.")
            if not context.selected_port.strip():
                errors.append("Kein COM-Port ausgewaehlt.")

        if not context.gcode.strip():
            errors.append("Keine Jobdaten vorhanden.")

        output_layers = active_output_layers(context.layers)
        if not output_layers:
            errors.append("Keine aktiven Layer fuer die Ausgabe.")

        for layer in output_layers:
            if layer.power_percent <= 0 or layer.power_percent > 100:
                errors.append(f"Ungueltige Laserleistung in Layer '{layer.name}'.")
            if context.max_power is not None and layer.power_percent > context.max_power:
                errors.append(f"Laserleistung in Layer '{layer.name}' ueberschreitet das Maschinenprofil.")
            if layer.speed_mm_min <= 0:
                errors.append(f"Ungueltige Geschwindigkeit in Layer '{layer.name}'.")
            if context.max_speed is not None and layer.speed_mm_min > context.max_speed:
                errors.append(f"Geschwindigkeit in Layer '{layer.name}' ueberschreitet das Maschinenprofil.")
            if layer.passes <= 0:
                errors.append(f"Ungueltige Durchgangszahl in Layer '{layer.name}'.")

        if context.material_profile.power_percent <= 0 or context.material_profile.power_percent > 100:
            errors.append("Ungueltige Laserleistung im Materialprofil.")
        if context.max_power is not None and context.material_profile.power_percent > context.max_power:
            errors.append("Laserleistung im Materialprofil ueberschreitet das Maschinenprofil.")
        if context.material_profile.speed_mm_min <= 0:
            errors.append("Ungueltige Geschwindigkeit im Materialprofil.")
        if context.max_speed is not None and context.material_profile.speed_mm_min > context.max_speed:
            errors.append("Geschwindigkeit im Materialprofil ueberschreitet das Maschinenprofil.")

        if context.prepared is not None:
            analysis = context.prepared.analysis
            if analysis.has_bounds:
                if analysis.min_x is not None and analysis.min_x < 0:
                    errors.append("Job unterschreitet den Arbeitsbereich.")
                if analysis.min_y is not None and analysis.min_y < 0:
                    errors.append("Job unterschreitet den Arbeitsbereich.")
                if analysis.max_x is not None and analysis.max_x > context.work_width_mm:
                    errors.append("Job ueberschreitet den Arbeitsbereich in X.")
                if analysis.max_y is not None and analysis.max_y > context.work_height_mm:
                    errors.append("Job ueberschreitet den Arbeitsbereich in Y.")
            if analysis.max_laser_power_percent > 100:
                errors.append("G-Code enthaelt Laserleistung ueber 100%.")
            elif analysis.max_laser_power_percent >= 90:
                warnings.append("G-Code enthaelt sehr hohe Laserleistung.")
            # The G-code can be edited by hand, so check the commands themselves - not only the
            # material/layer settings - against the machine profile limits.
            if context.max_power is not None and analysis.max_laser_power_percent > context.max_power:
                errors.append(
                    f"G-Code-Laserleistung {analysis.max_laser_power_percent:.0f}% ueberschreitet "
                    f"das Maschinenprofil ({context.max_power}%)."
                )
            if (
                context.max_speed is not None
                and analysis.max_feed_mm_min is not None
                and analysis.max_feed_mm_min > context.max_speed
            ):
                errors.append(
                    f"G-Code-Vorschub F{analysis.max_feed_mm_min:.0f} ueberschreitet "
                    f"das Maschinenprofil ({context.max_speed} mm/min)."
                )

        if hardware and not errors:
            info.append("Hardwarestart ist nur nach bestaetigtem Preflight erlaubt.")

        return StartValidationResult(
            passed=not errors,
            blocking_errors=_dedupe(errors),
            warnings=_dedupe(warnings),
            info=_dedupe(info),
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
