from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from laser_control.svg_import import COMMAND_RE, POINT_RE, Point, _parse_length, _parse_view_box


@dataclass(frozen=True)
class BezierCurveAnalysis:
    cubic_count: int = 0
    quadratic_count: int = 0
    curve_count: int = 0
    estimated_curve_length_mm: float = 0.0
    min_curve_radius_mm: float | None = None
    high_curvature_count: int = 0
    recommended_flattening_tolerance_mm: float = 0.05
    warnings: list[str] = field(default_factory=list)


def analyze_svg_beziers(path: str) -> BezierCurveAnalysis:
    source_path = Path(path)
    if not source_path.exists() or source_path.suffix.lower() != ".svg":
        return BezierCurveAnalysis()

    root = ET.parse(source_path).getroot()
    view_box = _parse_view_box(root.get("viewBox"))
    width_mm = _parse_length(root.get("width"), view_box[2] if view_box else 100.0)
    height_mm = _parse_length(root.get("height"), view_box[3] if view_box else 100.0)
    scale_x = width_mm / view_box[2] if view_box and view_box[2] else 1.0
    scale_y = height_mm / view_box[3] if view_box and view_box[3] else 1.0
    scale = (abs(scale_x) + abs(scale_y)) / 2.0

    cubic_count = 0
    quadratic_count = 0
    length = 0.0
    radii: list[float] = []
    high_curvature = 0

    for element in root.iter():
        if _local_name(element.tag) != "path":
            continue
        for curve in _path_curves(element.get("d", "")):
            kind, points = curve
            if kind == "cubic":
                cubic_count += 1
                scaled = [_scale_point(point, scale_x, scale_y) for point in points]
                length += _polyline_length(_sample_cubic(*scaled))
                curve_radii = _cubic_radii(*scaled)
            else:
                quadratic_count += 1
                scaled = [_scale_point(point, scale_x, scale_y) for point in points]
                length += _polyline_length(_sample_quadratic(*scaled))
                curve_radii = _quadratic_radii(*scaled)
            radii.extend(curve_radii)
            high_curvature += sum(1 for radius in curve_radii if radius < 0.5)

    curve_count = cubic_count + quadratic_count
    min_radius = min(radii) if radii else None
    tolerance = _recommended_tolerance(min_radius, scale)
    warnings: list[str] = []
    if min_radius is not None and min_radius < 0.2:
        warnings.append("Bezier-Details unter 0.20 mm: auf Falcon 10W nur begrenzt sinnvoll.")
    if high_curvature:
        warnings.append(f"Stark gekruemmte Bereiche erkannt: {high_curvature}.")
    return BezierCurveAnalysis(
        cubic_count=cubic_count,
        quadratic_count=quadratic_count,
        curve_count=curve_count,
        estimated_curve_length_mm=length,
        min_curve_radius_mm=min_radius,
        high_curvature_count=high_curvature,
        recommended_flattening_tolerance_mm=tolerance,
        warnings=warnings,
    )


def _path_curves(value: str) -> list[tuple[str, list[Point]]]:
    tokens = COMMAND_RE.findall(value)
    curves: list[tuple[str, list[Point]]] = []
    current: Point = (0.0, 0.0)
    start = current
    command = ""
    index = 0
    last_control: Point | None = None

    while index < len(tokens):
        token = tokens[index]
        if token.isalpha():
            command = token
            index += 1
        if not command:
            break
        relative = command.islower()
        op = command.upper()
        base = current if relative else (0.0, 0.0)
        if op == "M":
            current = _read_point(tokens, index, base)
            start = current
            index += 2
            command = "l" if relative else "L"
            last_control = None
        elif op == "L":
            current = _read_point(tokens, index, base)
            index += 2
            last_control = None
        elif op == "H":
            x = float(tokens[index])
            current = (current[0] + x, current[1]) if relative else (x, current[1])
            index += 1
            last_control = None
        elif op == "V":
            y = float(tokens[index])
            current = (current[0], current[1] + y) if relative else (current[0], y)
            index += 1
            last_control = None
        elif op == "C":
            p1 = _read_point(tokens, index, base)
            p2 = _read_point(tokens, index + 2, base)
            p3 = _read_point(tokens, index + 4, base)
            curves.append(("cubic", [current, p1, p2, p3]))
            current = p3
            last_control = p2
            index += 6
        elif op == "S":
            p1 = _reflect_point(last_control, current) if last_control else current
            p2 = _read_point(tokens, index, base)
            p3 = _read_point(tokens, index + 2, base)
            curves.append(("cubic", [current, p1, p2, p3]))
            current = p3
            last_control = p2
            index += 4
        elif op == "Q":
            p1 = _read_point(tokens, index, base)
            p2 = _read_point(tokens, index + 2, base)
            curves.append(("quadratic", [current, p1, p2]))
            current = p2
            last_control = p1
            index += 4
        elif op == "T":
            p1 = _reflect_point(last_control, current) if last_control else current
            p2 = _read_point(tokens, index, base)
            curves.append(("quadratic", [current, p1, p2]))
            current = p2
            last_control = p1
            index += 2
        elif op == "A":
            current = _read_point(tokens, index + 5, base)
            index += 7
            last_control = None
        elif op == "Z":
            current = start
            command = ""
            last_control = None
        else:
            break
    return curves


def _read_point(tokens: list[str], index: int, base: Point) -> Point:
    return base[0] + float(tokens[index]), base[1] + float(tokens[index + 1])


def _reflect_point(point: Point | None, around: Point) -> Point:
    if point is None:
        return around
    return around[0] * 2 - point[0], around[1] * 2 - point[1]


def _scale_point(point: Point, scale_x: float, scale_y: float) -> Point:
    return point[0] * scale_x, point[1] * scale_y


def _sample_cubic(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 32) -> list[Point]:
    return [_cubic_point(p0, p1, p2, p3, step / steps) for step in range(steps + 1)]


def _sample_quadratic(p0: Point, p1: Point, p2: Point, steps: int = 24) -> list[Point]:
    return [_quadratic_point(p0, p1, p2, step / steps) for step in range(steps + 1)]


def _cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    mt = 1 - t
    return (
        mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0],
        mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1],
    )


def _quadratic_point(p0: Point, p1: Point, p2: Point, t: float) -> Point:
    mt = 1 - t
    return (
        mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0],
        mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1],
    )


def _cubic_radii(p0: Point, p1: Point, p2: Point, p3: Point) -> list[float]:
    radii = []
    for step in range(1, 32):
        t = step / 32
        dx = 3 * (1 - t) ** 2 * (p1[0] - p0[0]) + 6 * (1 - t) * t * (p2[0] - p1[0]) + 3 * t**2 * (p3[0] - p2[0])
        dy = 3 * (1 - t) ** 2 * (p1[1] - p0[1]) + 6 * (1 - t) * t * (p2[1] - p1[1]) + 3 * t**2 * (p3[1] - p2[1])
        ddx = 6 * (1 - t) * (p2[0] - 2 * p1[0] + p0[0]) + 6 * t * (p3[0] - 2 * p2[0] + p1[0])
        ddy = 6 * (1 - t) * (p2[1] - 2 * p1[1] + p0[1]) + 6 * t * (p3[1] - 2 * p2[1] + p1[1])
        radius = _curvature_radius(dx, dy, ddx, ddy)
        if radius is not None:
            radii.append(radius)
    return radii


def _quadratic_radii(p0: Point, p1: Point, p2: Point) -> list[float]:
    ddx = 2 * (p2[0] - 2 * p1[0] + p0[0])
    ddy = 2 * (p2[1] - 2 * p1[1] + p0[1])
    radii = []
    for step in range(1, 24):
        t = step / 24
        dx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
        dy = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
        radius = _curvature_radius(dx, dy, ddx, ddy)
        if radius is not None:
            radii.append(radius)
    return radii


def _curvature_radius(dx: float, dy: float, ddx: float, ddy: float) -> float | None:
    numerator = (dx * dx + dy * dy) ** 1.5
    denominator = abs(dx * ddy - dy * ddx)
    if denominator <= 1e-9:
        return None
    return numerator / denominator


def _polyline_length(points: list[Point]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _recommended_tolerance(min_radius: float | None, scale: float) -> float:
    if min_radius is None:
        return max(0.02, min(0.08, scale * 0.01))
    if min_radius < 0.5:
        return 0.02
    if min_radius < 2.0:
        return 0.05
    return 0.08


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
