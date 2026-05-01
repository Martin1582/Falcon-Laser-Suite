from dataclasses import dataclass

from laser_control.gcode import CUT_MODE, ENGRAVE_MODE
from laser_control.gcode_analysis import GCodeAnalysis
from laser_control.job_history import JobHistoryEntry
from laser_control.models import MaterialProfile


@dataclass
class AssistantAdvice:
    risk_score: int
    risk_label: str
    recommendations: list[str]
    matching_successes: list[JobHistoryEntry]


class AssistantService:
    def advise(
        self,
        material_name: str,
        operation_mode: str,
        profile: MaterialProfile,
        analysis: GCodeAnalysis,
        warnings: list[str],
        history: list[JobHistoryEntry],
    ) -> AssistantAdvice:
        score = self._risk_score(profile, analysis, warnings)
        recommendations = self._recommendations(material_name, operation_mode, profile, analysis, warnings, history)
        successes = [
            entry
            for entry in history
            if entry.material_name == material_name
            and entry.operation_mode == operation_mode
            and entry.result == "good"
        ][-3:]
        return AssistantAdvice(
            risk_score=score,
            risk_label=self._risk_label(score),
            recommendations=recommendations,
            matching_successes=successes,
        )

    def build_test_matrix_gcode(
        self,
        material_name: str,
        operation_mode: str,
        profile: MaterialProfile,
        cell_size_mm: float = 12.0,
        gap_mm: float = 4.0,
    ) -> str:
        power_offsets = [-10, 0, 10]
        speed_factors = [1.25, 1.0, 0.75]
        lines = [
            f"; Testmatrix fuer {material_name} ({operation_mode})",
            "; Spalten: weniger / normal / mehr Leistung",
            "; Zeilen: schneller / normal / langsamer",
            "G21",
            "G90",
            "M5",
            "M3 ; constant laser power" if operation_mode == CUT_MODE else "M4 ; dynamic laser power",
        ]
        for row, speed_factor in enumerate(speed_factors):
            speed = max(50, int(profile.speed_mm_min * speed_factor))
            for column, power_offset in enumerate(power_offsets):
                power = min(100, max(1, profile.power_percent + power_offset))
                s_value = round(power / 100 * 1000)
                x = column * (cell_size_mm + gap_mm)
                y = row * (cell_size_mm + gap_mm)
                lines.extend(
                    [
                        f"; Feld R{row + 1} C{column + 1}: {power}% / {speed} mm/min",
                        "M5",
                        f"G0 X{x:.2f} Y{y:.2f} F2400",
                        f"G1 X{x + cell_size_mm:.2f} Y{y:.2f} S{s_value} F{speed}",
                        f"G1 X{x + cell_size_mm:.2f} Y{y + cell_size_mm:.2f} S{s_value} F{speed}",
                        f"G1 X{x:.2f} Y{y + cell_size_mm:.2f} S{s_value} F{speed}",
                        f"G1 X{x:.2f} Y{y:.2f} S{s_value} F{speed}",
                    ]
                )
        lines.append("M5")
        return "\n".join(lines)

    def _risk_score(self, profile: MaterialProfile, analysis: GCodeAnalysis, warnings: list[str]) -> int:
        score = min(60, len(warnings) * 15)
        if profile.power_percent >= 90:
            score += 20
        if profile.speed_mm_min <= 300:
            score += 15
        if profile.passes >= 3:
            score += 10
        if analysis.estimated_runtime_seconds >= 15 * 60:
            score += 10
        if analysis.uses_relative_positioning:
            score += 20
        return min(100, score)

    def _risk_label(self, score: int) -> str:
        if score >= 70:
            return "hoch"
        if score >= 35:
            return "mittel"
        return "niedrig"

    def _recommendations(
        self,
        material_name: str,
        operation_mode: str,
        profile: MaterialProfile,
        analysis: GCodeAnalysis,
        warnings: list[str],
        history: list[JobHistoryEntry],
    ) -> list[str]:
        recommendations: list[str] = []
        matching = [
            entry
            for entry in history
            if entry.material_name == material_name and entry.operation_mode == operation_mode
        ]
        successful = [entry for entry in matching if entry.result == "good"]
        if successful:
            last = successful[-1]
            recommendations.append(
                f"Letzter guter Job: {last.power_percent}% / {last.speed_mm_min} mm/min / {last.passes} Durchgaenge."
            )
        else:
            recommendations.append("Noch kein guter Erfahrungswert gespeichert; zuerst Testmatrix auf Restmaterial fahren.")
        if warnings:
            recommendations.append("Preflight-Warnungen zuerst klaeren, bevor echte Hardware gestartet wird.")
        if operation_mode == CUT_MODE and profile.power_percent >= 90:
            recommendations.append("Bei Cut mit hoher Leistung Air Assist und Absaugung aktiv nutzen.")
        if operation_mode == ENGRAVE_MODE and profile.power_percent >= 80:
            recommendations.append("Fuer Gravur koennte weniger Leistung mit hoeherer Geschwindigkeit sauberer sein.")
        if analysis.width_mm > 0 and analysis.height_mm > 0:
            recommendations.append(f"Pfadgroesse: {analysis.width_mm:.1f} x {analysis.height_mm:.1f} mm.")
        return recommendations
