from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FalconMaterialRecommendation:
    material_name: str
    engraving_speed_mm_min: int
    engraving_power_percent: int
    engraving_passes: int
    fill_spacing_mm: float
    overscan_default_mm: float
    operation_mode: str
    notes: list[str] = field(default_factory=list)
    cut_speed_mm_min: int | None = None
    cut_power_percent: int | None = None
    cut_passes: int | None = None

    @property
    def engraving_label(self) -> str:
        return f"{self.engraving_speed_mm_min} mm/min, {self.engraving_power_percent}%, {self.engraving_passes}x"


FALCON_10W_MATERIALS: tuple[FalconMaterialRecommendation, ...] = (
    FalconMaterialRecommendation("Lindenholz 2 mm", 3000, 35, 1, 0.10, 2.5, "M4", ["Startwert; Maserung und Fokus testen."], 450, 90, 2),
    FalconMaterialRecommendation("Kunstleder", 2500, 18, 1, 0.10, 2.0, "M4", ["Startwert; Geruch/Absaugung und geringe Leistung beachten."]),
    FalconMaterialRecommendation("Schiefer", 1800, 45, 1, 0.08, 2.0, "M4", ["Startwert; Kontrast haengt stark von Oberflaeche ab."]),
    FalconMaterialRecommendation("Pappe/Karton", 3500, 18, 1, 0.12, 2.0, "M4", ["Startwert; Brandgefahr, immer beaufsichtigen."], 900, 65, 1),
    FalconMaterialRecommendation("Sperrholz 3 mm", 2800, 35, 1, 0.10, 2.5, "M4", ["Startwert; Leimschichten koennen abweichen."], 320, 95, 3),
)


def falcon_10w_material_recommendation(material_name: str) -> FalconMaterialRecommendation | None:
    normalized = _normalize(material_name)
    if not normalized:
        return None
    for recommendation in FALCON_10W_MATERIALS:
        rec_name = _normalize(recommendation.material_name)
        if normalized in rec_name or rec_name in normalized:
            return recommendation
    aliases = {
        "lindenholz": "Lindenholz 2 mm",
        "kunstleder": "Kunstleder",
        "schiefer": "Schiefer",
        "karton": "Pappe/Karton",
        "pappe": "Pappe/Karton",
        "sperrholz": "Sperrholz 3 mm",
    }
    for token, target in aliases.items():
        if token in normalized:
            return next(item for item in FALCON_10W_MATERIALS if item.material_name == target)
    return None


def material_deviation_warnings(
    material_name: str,
    speed_mm_min: int,
    power_percent: int,
    passes: int,
) -> list[str]:
    recommendation = falcon_10w_material_recommendation(material_name)
    if recommendation is None:
        return []
    warnings: list[str] = [
        f"Falcon-10W-Materialstartwert {recommendation.material_name}: {recommendation.engraving_label}, Fill {recommendation.fill_spacing_mm:.2f} mm, Overscan {recommendation.overscan_default_mm:.1f} mm."
    ]
    if abs(speed_mm_min - recommendation.engraving_speed_mm_min) > recommendation.engraving_speed_mm_min * 0.35:
        warnings.append(f"Aktuelle Geschwindigkeit weicht deutlich vom Startwert ab ({speed_mm_min} statt {recommendation.engraving_speed_mm_min} mm/min).")
    if abs(power_percent - recommendation.engraving_power_percent) > 20:
        warnings.append(f"Aktuelle Leistung weicht deutlich vom Startwert ab ({power_percent}% statt {recommendation.engraving_power_percent}%).")
    if passes != recommendation.engraving_passes:
        warnings.append(f"Aktuelle Durchgaenge weichen vom Startwert ab ({passes} statt {recommendation.engraving_passes}).")
    return warnings


def _normalize(value: str) -> str:
    return value.strip().lower().replace("-", " ").replace("_", " ")
