import math
import re
from dataclasses import dataclass, field

from laser_control.gcode import FALCON_MAX_HEIGHT_MM, FALCON_MAX_WIDTH_MM, prepare_job_gcode


WORD_RE = re.compile(r"([A-Z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))", re.IGNORECASE)
MOTION_PREFIXES = ("G0", "G00", "G1", "G01", "G2", "G02", "G3", "G03")


@dataclass
class GCodeAnalysis:
    commands: list[str]
    movement_count: int = 0
    laser_command_count: int = 0
    laser_power_values: list[float] = field(default_factory=list)
    min_x: float | None = None
    min_y: float | None = None
    max_x: float | None = None
    max_y: float | None = None
    max_feed_mm_min: float | None = None
    estimated_runtime_seconds: float = 0.0
    uses_relative_positioning: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def has_bounds(self) -> bool:
        return None not in (self.min_x, self.min_y, self.max_x, self.max_y)

    @property
    def width_mm(self) -> float:
        if not self.has_bounds:
            return 0.0
        return max(0.0, self.max_x - self.min_x)

    @property
    def height_mm(self) -> float:
        if not self.has_bounds:
            return 0.0
        return max(0.0, self.max_y - self.min_y)

    @property
    def max_laser_power_percent(self) -> float:
        if not self.laser_power_values:
            return 0.0
        return max(self.laser_power_values) / 10

    @property
    def estimated_runtime_label(self) -> str:
        seconds = int(round(self.estimated_runtime_seconds))
        minutes, remaining_seconds = divmod(seconds, 60)
        if minutes:
            return f"{minutes} min {remaining_seconds:02d} s"
        return f"{remaining_seconds} s"


def analyze_gcode(gcode: str, work_width_mm: float, work_height_mm: float) -> GCodeAnalysis:
    commands = prepare_job_gcode(gcode, work_width_mm, work_height_mm)
    analysis = GCodeAnalysis(commands=commands)
    x = 0.0
    y = 0.0
    feed = 1000.0
    absolute_positioning = True

    for command in commands:
        upper = command.upper()
        first_word = upper.split(None, 1)[0]
        words = {letter.upper(): float(value) for letter, value in WORD_RE.findall(command)}

        if upper.startswith("G90"):
            absolute_positioning = True
        elif upper.startswith("G91"):
            absolute_positioning = False
            analysis.uses_relative_positioning = True

        if "F" in words and words["F"] > 0:
            feed = words["F"]
            analysis.max_feed_mm_min = max(analysis.max_feed_mm_min or 0.0, feed)
        if "S" in words:
            analysis.laser_power_values.append(words["S"])
        if upper.startswith(("M3", "M4")) or "S" in words:
            analysis.laser_command_count += 1

        if first_word in MOTION_PREFIXES:
            next_x = words.get("X", x)
            next_y = words.get("Y", y)
            if not absolute_positioning:
                next_x = x + words.get("X", 0.0)
                next_y = y + words.get("Y", 0.0)
            _include_point(analysis, next_x, next_y)
            analysis.movement_count += 1
            distance = math.hypot(next_x - x, next_y - y)
            if feed > 0:
                analysis.estimated_runtime_seconds += distance / feed * 60
            x, y = next_x, next_y

    _add_safety_warnings(analysis, work_width_mm, work_height_mm)
    return analysis


def _include_point(analysis: GCodeAnalysis, x: float, y: float) -> None:
    analysis.min_x = x if analysis.min_x is None else min(analysis.min_x, x)
    analysis.min_y = y if analysis.min_y is None else min(analysis.min_y, y)
    analysis.max_x = x if analysis.max_x is None else max(analysis.max_x, x)
    analysis.max_y = y if analysis.max_y is None else max(analysis.max_y, y)


def _add_safety_warnings(analysis: GCodeAnalysis, work_width_mm: float, work_height_mm: float) -> None:
    if analysis.uses_relative_positioning:
        analysis.warnings.append("Relative Positionierung (G91) erkannt; Pfadgrenzen bitte besonders pruefen.")
    if analysis.has_bounds:
        if analysis.min_x < 0 or analysis.min_y < 0:
            analysis.warnings.append("G-Code enthaelt negative Koordinaten.")
        if analysis.max_x > work_width_mm or analysis.max_y > work_height_mm:
            analysis.warnings.append("G-Code liegt ausserhalb des eingestellten Arbeitsbereichs.")
        if analysis.max_x > FALCON_MAX_WIDTH_MM or analysis.max_y > FALCON_MAX_HEIGHT_MM:
            analysis.warnings.append("G-Code ueberschreitet den Falcon-Arbeitsbereich.")
    if analysis.max_laser_power_percent >= 90:
        analysis.warnings.append("Sehr hohe Laserleistung im G-Code erkannt.")
    if not analysis.laser_command_count:
        analysis.warnings.append("Keine Laser-Aktivbefehle erkannt; Job bewegt vermutlich nur.")
