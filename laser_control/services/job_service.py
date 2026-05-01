from dataclasses import dataclass, field

from laser_control.gcode import CUT_MODE, build_dry_run_gcode, prepare_job_gcode
from laser_control.gcode_analysis import GCodeAnalysis, analyze_gcode
from laser_control.models import MaterialProfile
from laser_control.serial_grbl import serial_support_available
from laser_control.workflow import build_cut_mode_warnings


@dataclass
class JobPreparation:
    commands: list[str]
    analysis: GCodeAnalysis
    warnings: list[str] = field(default_factory=list)


class JobService:
    def prepare_job(
        self,
        gcode: str,
        width_mm: float,
        height_mm: float,
        profile: MaterialProfile,
        operation_mode: str,
    ) -> JobPreparation:
        analysis = analyze_gcode(gcode, width_mm, height_mm)
        warnings = list(analysis.warnings)
        if operation_mode == CUT_MODE:
            warnings.extend(build_cut_mode_warnings(profile.power_percent, profile.speed_mm_min, profile.passes))
        return JobPreparation(commands=analysis.commands, analysis=analysis, warnings=warnings)

    def prepare_dry_run(self, gcode: str, width_mm: float, height_mm: float) -> JobPreparation:
        dry_run_gcode = build_dry_run_gcode(gcode, width_mm, height_mm)
        analysis = analyze_gcode(dry_run_gcode, width_mm, height_mm)
        return JobPreparation(commands=prepare_job_gcode(dry_run_gcode, width_mm, height_mm), analysis=analysis)

    def hardware_preflight_warnings(self, controller, selected_port: str) -> list[str]:
        warnings: list[str] = []
        if not serial_support_available():
            warnings.append("pyserial ist nicht installiert. Bitte requirements installieren.")
        if not selected_port.strip():
            warnings.append("Kein COM-Port ausgewaehlt. Bitte zuerst einen Port waehlen.")
        state = getattr(controller, "state", None)
        if not state or not getattr(state, "connected", False):
            warnings.append("Controller ist nicht verbunden. Bitte zuerst auf 'Verbinden' klicken.")
        if not getattr(state, "homed", False):
            warnings.append("Keine Referenzfahrt erkannt. Bitte zuerst 'Referenzfahrt' ausfuehren.")
        return warnings
