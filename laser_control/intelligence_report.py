from __future__ import annotations

from dataclasses import dataclass, field

from laser_control.geometry_analyzer import GeometryAnalysis
from laser_control.svg_optimization import SvgOptimizationResult


@dataclass(frozen=True)
class OriginalWorkingCopyReport:
    original: GeometryAnalysis
    working_copy: GeometryAnalysis
    applied_optimizations: list[str] = field(default_factory=list)
    segment_reduction_percent: int = 0
    gcode_reduction_percent: int = 0
    runtime_saving_percent: int = 0
    detail_loss_risk: str = "niedrig"
    recommendations: list[str] = field(default_factory=list)

    @property
    def short_summary(self) -> str:
        return (
            f"Original {self.original.segment_count} Segmente -> "
            f"Arbeitskopie {self.working_copy.segment_count} Segmente; "
            f"{self.segment_reduction_percent}% weniger Segmente, "
            f"Detailverlust-Risiko {self.detail_loss_risk}."
        )


def build_original_working_copy_report(
    original: GeometryAnalysis,
    working_copy: GeometryAnalysis,
    optimization_result: SvgOptimizationResult | None = None,
) -> OriginalWorkingCopyReport:
    applied: list[str] = []
    if optimization_result is not None:
        if optimization_result.simplify_enabled:
            applied.append(f"Konturvereinfachung {optimization_result.tolerance_mm:.2f} mm")
        if optimization_result.duplicate_removal_enabled:
            applied.append("Doppelte Linien entfernt")
    segment_reduction = _reduction(original.segment_count, working_copy.segment_count)
    gcode_reduction = _reduction(original.estimated_gcode_lines, working_copy.estimated_gcode_lines)
    runtime_saving = _reduction(round(original.estimated_runtime_seconds), round(working_copy.estimated_runtime_seconds))
    risk = "niedrig"
    if optimization_result is not None and optimization_result.simplify_enabled:
        if optimization_result.tolerance_mm >= 0.05 and original.smallest_detail_mm <= 0.15:
            risk = "mittel"
        if optimization_result.tolerance_mm >= 0.08:
            risk = "hoch"
    recommendations: list[str] = []
    if segment_reduction >= 30:
        recommendations.append("Optimierte Arbeitskopie reduziert Laufzeit und GCode deutlich.")
    if risk != "niedrig":
        recommendations.append("Detailverlust am Restmaterial pruefen.")
    if not applied:
        recommendations.append("Keine aktive Optimierung; Original und Arbeitskopie sind praktisch gleich.")
    return OriginalWorkingCopyReport(
        original=original,
        working_copy=working_copy,
        applied_optimizations=applied,
        segment_reduction_percent=segment_reduction,
        gcode_reduction_percent=gcode_reduction,
        runtime_saving_percent=runtime_saving,
        detail_loss_risk=risk,
        recommendations=recommendations,
    )


def _reduction(original: int | float, optimized: int | float) -> int:
    if original <= 0:
        return 0
    return max(0, min(100, round((original - optimized) / original * 100)))
