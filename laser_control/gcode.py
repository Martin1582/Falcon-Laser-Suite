import re

from laser_control.models import MaterialProfile
from laser_control.svg_import import Polyline


FALCON_MAX_WIDTH_MM = 400.0
FALCON_MAX_HEIGHT_MM = 415.0
MOTION_COMMAND_RE = re.compile(r"^G0*[123](?:\D|$)")
LASER_POWER_WORD_RE = re.compile(r"\sS[-+]?(?:\d+(?:\.\d+)?|\.\d+)\b", re.IGNORECASE)
ENGRAVE_MODE = "gravieren"
CUT_MODE = "cutten"


def laser_mode_command(operation_mode: str) -> str:
    return "M3 ; constant laser power" if operation_mode == CUT_MODE else "M4 ; dynamic laser power"


def build_rectangle_frame_gcode(
    width_mm: float,
    height_mm: float,
    profile: MaterialProfile,
    operation_mode: str = ENGRAVE_MODE,
) -> str:
    safe_width = max(1.0, width_mm)
    safe_height = max(1.0, height_mm)
    laser_power = round(profile.power_percent / 100 * 1000)

    lines = [
        "; Laser Control preview job",
        "G21 ; millimeters",
        "G90 ; absolute positioning",
        "M5 ; laser off",
        laser_mode_command(operation_mode),
        f"G0 X0 Y0 F{profile.speed_mm_min}",
        f"G1 X{safe_width:.2f} Y0 S{laser_power} F{profile.speed_mm_min}",
        f"G1 X{safe_width:.2f} Y{safe_height:.2f}",
        f"G1 X0 Y{safe_height:.2f}",
        "G1 X0 Y0",
        "M5 ; laser off",
    ]

    return "\n".join(lines)


def prepare_job_gcode(gcode: str, width_mm: float, height_mm: float) -> list[str]:
    validate_falcon_work_area(width_mm, height_mm)
    commands = []
    for raw_line in gcode.splitlines():
        command = raw_line.split(";", 1)[0].strip()
        if command:
            commands.append(command)

    if not commands:
        raise ValueError("Kein G-Code zum Senden vorhanden.")

    if not any(MOTION_COMMAND_RE.match(command.upper()) for command in commands):
        raise ValueError("Der G-Code enthaelt keine Bewegungsbefehle.")

    if not any(command.upper().startswith("M5") for command in commands[-2:]):
        commands.append("M5")

    return commands


def build_dry_run_gcode(gcode: str, width_mm: float, height_mm: float) -> str:
    commands = prepare_job_gcode(gcode, width_mm, height_mm)
    sanitized = ["M5"]
    for command in commands:
        upper = command.upper()
        if upper.startswith(("M3", "M4")) or upper.startswith("S"):
            continue
        if upper.startswith("M5"):
            continue
        sanitized_command = LASER_POWER_WORD_RE.sub("", command).strip()
        if sanitized_command:
            sanitized.append(sanitized_command)
    sanitized.append("M5")
    return "\n".join(sanitized)


def validate_falcon_work_area(width_mm: float, height_mm: float) -> None:
    if width_mm <= 0 or height_mm <= 0:
        raise ValueError("Arbeitsbereich muss groesser als 0 mm sein.")
    if width_mm > FALCON_MAX_WIDTH_MM or height_mm > FALCON_MAX_HEIGHT_MM:
        raise ValueError(
            f"Arbeitsbereich ueberschreitet Falcon-Limit {FALCON_MAX_WIDTH_MM:.0f} x {FALCON_MAX_HEIGHT_MM:.0f} mm."
        )


def build_safe_frame_gcode(width_mm: float, height_mm: float, feed_mm_min: int = 2400) -> list[str]:
    validate_falcon_work_area(width_mm, height_mm)
    safe_width = max(1.0, width_mm)
    safe_height = max(1.0, height_mm)

    return [
        "G21",
        "G90",
        "M5",
        f"G0 X0 Y0 F{feed_mm_min}",
        f"G0 X{safe_width:.2f} Y0 F{feed_mm_min}",
        f"G0 X{safe_width:.2f} Y{safe_height:.2f} F{feed_mm_min}",
        f"G0 X0 Y{safe_height:.2f} F{feed_mm_min}",
        f"G0 X0 Y0 F{feed_mm_min}",
        "M5",
    ]


def build_polyline_gcode(
    paths: list[Polyline],
    profile: MaterialProfile,
    operation_mode: str = ENGRAVE_MODE,
) -> str:
    if not paths:
        raise ValueError("Keine Pfade fuer G-Code vorhanden.")

    laser_power = round(profile.power_percent / 100 * 1000)
    lines = [
        "; Laser Control imported SVG job",
        "G21 ; millimeters",
        "G90 ; absolute positioning",
        "M5 ; laser off",
        laser_mode_command(operation_mode),
    ]

    for pass_index in range(max(1, profile.passes)):
        lines.append(f"; pass {pass_index + 1}")
        for path in paths:
            if len(path) < 2:
                continue
            start_x, start_y = path[0]
            lines.append("M5")
            lines.append(f"G0 X{start_x:.2f} Y{start_y:.2f} F{profile.speed_mm_min}")
            lines.append(laser_mode_command(operation_mode))
            for x, y in path[1:]:
                lines.append(f"G1 X{x:.2f} Y{y:.2f} S{laser_power} F{profile.speed_mm_min}")
    lines.append("M5 ; laser off")
    return "\n".join(lines)
