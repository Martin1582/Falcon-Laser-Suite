import re
from typing import TYPE_CHECKING

from laser_control.models import MaterialProfile
from laser_control.svg_import import Polyline

if TYPE_CHECKING:
    from laser_control.fill_toolpath import FillToolpath


FALCON_MAX_WIDTH_MM = 400.0
FALCON_MAX_HEIGHT_MM = 415.0
MOTION_COMMAND_RE = re.compile(r"^G0*[0123](?:\D|$)")
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


def build_safe_frame_gcode(
    width_mm: float,
    height_mm: float,
    feed_mm_min: int = 2400,
    x_mm: float = 0.0,
    y_mm: float = 0.0,
) -> list[str]:
    if x_mm < 0 or y_mm < 0:
        raise ValueError("Frame-Koordinaten duerfen nicht negativ sein.")
    validate_falcon_work_area(x_mm + width_mm, y_mm + height_mm)
    safe_width = max(1.0, width_mm)
    safe_height = max(1.0, height_mm)
    safe_x = max(0.0, x_mm)
    safe_y = max(0.0, y_mm)
    max_x = safe_x + safe_width
    max_y = safe_y + safe_height

    return [
        "G21",
        "G90",
        "M5",
        "S0",
        f"G0 X{safe_x:.2f} Y{safe_y:.2f} F{feed_mm_min}",
        f"G0 X{max_x:.2f} Y{safe_y:.2f} F{feed_mm_min}",
        f"G0 X{max_x:.2f} Y{max_y:.2f} F{feed_mm_min}",
        f"G0 X{safe_x:.2f} Y{max_y:.2f} F{feed_mm_min}",
        f"G0 X{safe_x:.2f} Y{safe_y:.2f} F{feed_mm_min}",
        "S0",
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


def build_layered_polyline_gcode(
    paths: list[Polyline],
    layers: list[object],
    operation_mode: str = ENGRAVE_MODE,
    fill_toolpaths: list["FillToolpath"] | None = None,
) -> str:
    if not paths:
        raise ValueError("Keine Pfade fuer G-Code vorhanden.")

    output_layers = sorted(
        (layer for layer in layers if bool(getattr(layer, "is_output_layer", False))),
        key=lambda layer: int(getattr(layer, "order", 99)),
    )
    if not output_layers:
        raise ValueError("Keine aktiven Ausgabelayer fuer G-Code vorhanden.")

    lines = [
        "; Laser Control imported SVG job",
        "G21 ; millimeters",
        "G90 ; absolute positioning",
        "M5 ; laser off",
    ]
    fill_by_order = {toolpath.layer_order: toolpath for toolpath in (fill_toolpaths or [])}
    for layer in output_layers:
        power_percent = int(getattr(layer, "power_percent", 0))
        speed_mm_min = int(getattr(layer, "speed_mm_min", 1000))
        passes = max(1, int(getattr(layer, "passes", 1)))
        laser_power = round(power_percent / 100 * 1000)
        lines.append(
            f"; layer {getattr(layer, 'order', 0)}: {getattr(layer, 'name', 'Layer')} "
            f"{speed_mm_min} mm/min {power_percent}% {passes}x"
        )
        uses_outline = bool(getattr(layer, "uses_outline", True))
        uses_fill = bool(getattr(layer, "uses_fill", False))
        fill_toolpath = fill_by_order.get(int(getattr(layer, "order", 99)))
        if uses_fill and fill_toolpath is not None and bool(getattr(fill_toolpath, "unsafe_fill", False)):
            raise ValueError("SVG-Fuellung bei verschachtelten oder offenen Konturen aktuell nicht sicher unterstuetzt.")
        if uses_fill and fill_toolpath is not None:
            lines.append(
                f"; fill spacing {fill_toolpath.spacing_mm:.2f} mm "
                f"angle {fill_toolpath.angle_deg} deg lines {fill_toolpath.line_count}"
            )
            if fill_toolpath.overscan_enabled:
                lines.append(
                    f"; overscan {fill_toolpath.overscan_mode} {fill_toolpath.overscan_mm:.2f} mm "
                    f"additional {fill_toolpath.additional_travel_mm:.2f} mm"
                )
        for pass_index in range(passes):
            lines.append(f"; pass {pass_index + 1}")
            if uses_fill and fill_toolpath is not None:
                lines.append("; toolpath fill")
                _append_fill_paths(lines, fill_toolpath, speed_mm_min, laser_power, operation_mode)
            if uses_outline:
                lines.append("; toolpath outline")
                _append_paths(lines, paths, speed_mm_min, laser_power, operation_mode)
    lines.append("M5 ; laser off")
    return "\n".join(lines)


def build_multi_item_layered_polyline_gcode(
    item_paths: list[tuple[str, list[Polyline]]],
    layers: list[object],
    operation_mode: str = ENGRAVE_MODE,
    fill_toolpaths_by_item: dict[str, list["FillToolpath"]] | None = None,
) -> str:
    active_items = [(name, paths) for name, paths in item_paths if paths]
    if not active_items:
        raise ValueError("Keine aktiven Vektormotive fuer G-Code vorhanden.")

    output_layers = sorted(
        (layer for layer in layers if bool(getattr(layer, "is_output_layer", False))),
        key=lambda layer: int(getattr(layer, "order", 99)),
    )
    if not output_layers:
        raise ValueError("Keine aktiven Ausgabelayer fuer G-Code vorhanden.")

    lines = [
        "; Laser Control multi artwork job",
        "G21 ; millimeters",
        "G90 ; absolute positioning",
        "M5 ; laser off",
    ]
    fills_by_item = fill_toolpaths_by_item or {}
    for item_index, (item_name, paths) in enumerate(active_items, start=1):
        lines.append(f"; artwork {item_index}: {item_name}")
        item_fills = fills_by_item.get(item_name, [])
        item_code = build_layered_polyline_gcode(paths, output_layers, operation_mode, item_fills).splitlines()
        lines.extend(line for line in item_code if line not in {"G21 ; millimeters", "G90 ; absolute positioning"})
    if not any(line.upper().startswith("M5") for line in lines[-2:]):
        lines.append("M5 ; laser off")
    return "\n".join(lines)


def _append_paths(
    lines: list[str],
    paths: list[Polyline],
    speed_mm_min: int,
    laser_power: int,
    operation_mode: str,
) -> None:
    for path in paths:
        if len(path) < 2:
            continue
        start_x, start_y = path[0]
        lines.append("M5")
        lines.append(f"G0 X{start_x:.2f} Y{start_y:.2f} F{speed_mm_min}")
        lines.append(laser_mode_command(operation_mode))
        for x, y in path[1:]:
            lines.append(f"G1 X{x:.2f} Y{y:.2f} S{laser_power} F{speed_mm_min}")


def _append_fill_paths(
    lines: list[str],
    fill_toolpath: "FillToolpath",
    speed_mm_min: int,
    laser_power: int,
    operation_mode: str,
) -> None:
    if not fill_toolpath.overscan_enabled or not fill_toolpath.overscan_segments:
        _append_paths(lines, fill_toolpath.segments, speed_mm_min, laser_power, operation_mode)
        return
    for segment in fill_toolpath.overscan_segments:
        lines.append("M5")
        lines.append(f"G0 X{segment.entry[0]:.2f} Y{segment.entry[1]:.2f} F{speed_mm_min}")
        lines.append(laser_mode_command(operation_mode))
        lines.append(
            f"G1 X{segment.engraving_start[0]:.2f} Y{segment.engraving_start[1]:.2f} "
            f"S0 F{speed_mm_min}"
        )
        lines.append(
            f"G1 X{segment.engraving_end[0]:.2f} Y{segment.engraving_end[1]:.2f} "
            f"S{laser_power} F{speed_mm_min}"
        )
        lines.append("M5")
        lines.append(f"G1 X{segment.exit[0]:.2f} Y{segment.exit[1]:.2f} S0 F{speed_mm_min}")
