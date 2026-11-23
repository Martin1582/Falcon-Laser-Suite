from __future__ import annotations

from dataclasses import dataclass

from laser_control.fill_toolpath import calculate_automatic_overscan_mm
from laser_control.geometry_analyzer import GeometryAnalysis
from laser_control.motif_classifier import MotifClass, MotifClassification
from laser_control.svg_import import Polyline


@dataclass(frozen=True)
class ToolpathPlan:
    ordered_paths: list[Polyline]
    strategy: str
    estimated_travel_reduction_percent: int
    warnings: list[str]


@dataclass(frozen=True)
class FalconMachineRecommendation:
    power_percent: int
    speed_mm_min: int
    passes: int
    overscan_mm: float
    line_spacing_mm: float
    fill_strategy: str
    notes: list[str]


class ToolpathOptimizer:
    def sort_paths_nearest_neighbor(self, paths: list[Polyline]) -> list[Polyline]:
        remaining = [path for path in paths if path]
        if not remaining:
            return []
        ordered = [remaining.pop(0)]
        while remaining:
            last = ordered[-1][-1]
            index = min(range(len(remaining)), key=lambda i: _distance_sq(last, remaining[i][0]))
            ordered.append(remaining.pop(index))
        return ordered

    def plan(self, paths: list[Polyline], classification: MotifClassification) -> ToolpathPlan:
        ordered = self.sort_paths_nearest_neighbor(paths)
        strategy = "Innenkonturen vor Aussenkonturen, danach Gravur/Schnitt"
        if classification.motif_class in {MotifClass.TEXT, MotifClass.TECHNICAL_DRAWING}:
            strategy = "Reine Kontur, Reihenfolge nach Naehe"
        warnings = []
        if len(paths) > 2_000:
            warnings.append("Viele Einzelpfade; Reihenfolgeoptimierung kann Leerfahrten reduzieren.")
        return ToolpathPlan(
            ordered_paths=ordered,
            strategy=strategy,
            estimated_travel_reduction_percent=15 if len(paths) > 10 else 0,
            warnings=warnings,
        )


def falcon_10w_recommendation(analysis: GeometryAnalysis, classification: MotifClassification) -> FalconMachineRecommendation:
    speed = 3000
    power = 35
    passes = 1
    spacing = 0.08
    fill_strategy = classification.recommended_strategy
    notes = ["Empfehlung fuer Creality CR Laser Falcon 10W; Materialtest bleibt erforderlich."]
    if classification.motif_class in {MotifClass.TEXT, MotifClass.TECHNICAL_DRAWING}:
        speed = 3500
        power = 25
        spacing = 0.10
    elif classification.motif_class in {MotifClass.LOGO, MotifClass.POLYGON_ART, MotifClass.MANDALA}:
        speed = 2800
        power = 30
        spacing = 0.08
    elif classification.motif_class in {MotifClass.RASTER, MotifClass.PHOTO}:
        speed = 2500
        power = 20
        spacing = 0.10
    if analysis.complexity in {"Hoch", "Extrem"}:
        speed = min(speed, 2500)
        notes.append("Hohe Komplexitaet: moderatere Geschwindigkeit und Konturvereinfachung pruefen.")
    overscan = calculate_automatic_overscan_mm(speed)
    return FalconMachineRecommendation(power, speed, passes, overscan, spacing, fill_strategy, notes)


def _distance_sq(a: tuple[float, float], b: tuple[float, float]) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
