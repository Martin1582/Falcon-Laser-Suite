import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


Point = tuple[float, float]
Polyline = list[Point]
Matrix = tuple[float, float, float, float, float, float]


@dataclass
class SvgImportResult:
    width_mm: float
    height_mm: float
    paths: list[Polyline]


def path_bounds(paths: list[Polyline]) -> tuple[float, float, float, float]:
    points = [point for polyline in paths for point in polyline]
    if not points:
        raise ValueError("Keine SVG-Punkte vorhanden.")
    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_x = max(point[0] for point in points)
    max_y = max(point[1] for point in points)
    return min_x, min_y, max_x, max_y


def transform_paths(paths: list[Polyline], scale: float, offset_x: float, offset_y: float) -> list[Polyline]:
    min_x, min_y, _, _ = path_bounds(paths)
    return [
        [((x - min_x) * scale + offset_x, (y - min_y) * scale + offset_y) for x, y in polyline]
        for polyline in paths
    ]


def fit_paths_to_area(
    paths: list[Polyline],
    area_width: float,
    area_height: float,
    margin: float,
) -> tuple[list[Polyline], float, float]:
    min_x, min_y, max_x, max_y = path_bounds(paths)
    source_width = max_x - min_x
    source_height = max_y - min_y
    usable_width = max(1.0, area_width - margin * 2)
    usable_height = max(1.0, area_height - margin * 2)
    scale = min(usable_width / source_width, usable_height / source_height)
    fitted_width = source_width * scale
    fitted_height = source_height * scale
    offset_x = margin + (usable_width - fitted_width) / 2
    offset_y = margin + (usable_height - fitted_height) / 2
    return transform_paths(paths, scale, offset_x, offset_y), fitted_width, fitted_height


def scale_paths_to_width(
    paths: list[Polyline],
    target_width: float,
    offset_x: float,
    offset_y: float,
) -> tuple[list[Polyline], float, float]:
    min_x, min_y, max_x, max_y = path_bounds(paths)
    source_width = max_x - min_x
    source_height = max_y - min_y
    scale = target_width / source_width
    return transform_paths(paths, scale, offset_x, offset_y), target_width, source_height * scale


COMMAND_RE = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
POINT_RE = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
TRANSFORM_RE = re.compile(r"(matrix|translate|scale|rotate)\s*\(([^)]*)\)")


def import_svg(path: str) -> SvgImportResult:
    root = ET.parse(path).getroot()
    view_box = _parse_view_box(root.get("viewBox"))
    width = _parse_length(root.get("width"), view_box[2] if view_box else 100.0)
    height = _parse_length(root.get("height"), view_box[3] if view_box else 100.0)
    scale_x = width / view_box[2] if view_box and view_box[2] else 1.0
    scale_y = height / view_box[3] if view_box and view_box[3] else 1.0
    offset_x = view_box[0] if view_box else 0.0
    offset_y = view_box[1] if view_box else 0.0

    paths = _collect_paths(root, _identity_matrix())

    normalized = [_normalize(polyline, offset_x, offset_y, scale_x, scale_y) for polyline in paths if len(polyline) >= 2]
    if not normalized:
        raise ValueError(f"Keine unterstuetzte SVG-Geometrie gefunden: {Path(path).name}")

    return SvgImportResult(width_mm=width, height_mm=height, paths=normalized)


def _collect_paths(element: ET.Element, parent_transform: Matrix) -> list[Polyline]:
    transform = _multiply_matrix(parent_transform, _parse_transform(element.get("transform")))
    tag = _local_name(element.tag)
    paths: list[Polyline] = []

    if tag == "rect":
        paths.append(_apply_matrix_to_polyline(_rect(element), transform))
    elif tag == "line":
        paths.append(_apply_matrix_to_polyline(_line(element), transform))
    elif tag == "polyline":
        paths.append(_apply_matrix_to_polyline(_points(element.get("points", ""), close=False), transform))
    elif tag == "polygon":
        paths.append(_apply_matrix_to_polyline(_points(element.get("points", ""), close=True), transform))
    elif tag == "circle":
        paths.append(_apply_matrix_to_polyline(_ellipse(element, circle=True), transform))
    elif tag == "ellipse":
        paths.append(_apply_matrix_to_polyline(_ellipse(element, circle=False), transform))
    elif tag == "path":
        paths.extend(_apply_matrix_to_polyline(polyline, transform) for polyline in _path(element.get("d", "")))

    for child in list(element):
        paths.extend(_collect_paths(child, transform))
    return paths


def _parse_length(value: str | None, fallback: float) -> float:
    if not value:
        return fallback
    match = re.match(r"\s*([-+]?(?:\d*\.\d+|\d+\.?))\s*([a-zA-Z]*)", value)
    if not match:
        return fallback
    number = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "cm":
        return number * 10
    if unit == "in":
        return number * 25.4
    if unit == "px":
        return number * 25.4 / 96
    return number


def _parse_view_box(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    numbers = [float(item) for item in POINT_RE.findall(value)]
    if len(numbers) != 4:
        return None
    return numbers[0], numbers[1], numbers[2], numbers[3]


def _identity_matrix() -> Matrix:
    return 1.0, 0.0, 0.0, 1.0, 0.0, 0.0


def _multiply_matrix(left: Matrix, right: Matrix) -> Matrix:
    la, lb, lc, ld, le, lf = left
    ra, rb, rc, rd, re, rf = right
    return (
        la * ra + lc * rb,
        lb * ra + ld * rb,
        la * rc + lc * rd,
        lb * rc + ld * rd,
        la * re + lc * rf + le,
        lb * re + ld * rf + lf,
    )


def _apply_matrix(point: Point, matrix: Matrix) -> Point:
    a, b, c, d, e, f = matrix
    x, y = point
    return a * x + c * y + e, b * x + d * y + f


def _apply_matrix_to_polyline(polyline: Polyline, matrix: Matrix) -> Polyline:
    return [_apply_matrix(point, matrix) for point in polyline]


def _parse_transform(value: str | None) -> Matrix:
    matrix = _identity_matrix()
    if not value:
        return matrix

    for name, raw_args in TRANSFORM_RE.findall(value):
        args = [float(item) for item in POINT_RE.findall(raw_args)]
        if name == "matrix" and len(args) == 6:
            next_matrix = tuple(args)  # type: ignore[assignment]
        elif name == "translate":
            tx = args[0] if args else 0.0
            ty = args[1] if len(args) > 1 else 0.0
            next_matrix = (1.0, 0.0, 0.0, 1.0, tx, ty)
        elif name == "scale":
            sx = args[0] if args else 1.0
            sy = args[1] if len(args) > 1 else sx
            next_matrix = (sx, 0.0, 0.0, sy, 0.0, 0.0)
        elif name == "rotate" and args:
            angle = math.radians(args[0])
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            rotate = (cos_a, sin_a, -sin_a, cos_a, 0.0, 0.0)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                next_matrix = _multiply_matrix(
                    _multiply_matrix((1.0, 0.0, 0.0, 1.0, cx, cy), rotate),
                    (1.0, 0.0, 0.0, 1.0, -cx, -cy),
                )
            else:
                next_matrix = rotate
        else:
            continue
        matrix = _multiply_matrix(matrix, next_matrix)
    return matrix


def _rect(element: ET.Element) -> Polyline:
    x = _float_attr(element, "x")
    y = _float_attr(element, "y")
    width = _float_attr(element, "width")
    height = _float_attr(element, "height")
    return [(x, y), (x + width, y), (x + width, y + height), (x, y + height), (x, y)]


def _line(element: ET.Element) -> Polyline:
    return [
        (_float_attr(element, "x1"), _float_attr(element, "y1")),
        (_float_attr(element, "x2"), _float_attr(element, "y2")),
    ]


def _points(value: str, close: bool) -> Polyline:
    numbers = [float(item) for item in POINT_RE.findall(value)]
    points = [(numbers[index], numbers[index + 1]) for index in range(0, len(numbers) - 1, 2)]
    if close and points and points[0] != points[-1]:
        points.append(points[0])
    return points


def _ellipse(element: ET.Element, circle: bool) -> Polyline:
    cx = _float_attr(element, "cx")
    cy = _float_attr(element, "cy")
    rx = _float_attr(element, "r" if circle else "rx")
    ry = rx if circle else _float_attr(element, "ry")
    points = []
    for step in range(49):
        angle = math.tau * step / 48
        points.append((cx + math.cos(angle) * rx, cy + math.sin(angle) * ry))
    return points


def _path(value: str) -> list[Polyline]:
    tokens = COMMAND_RE.findall(value)
    paths: list[Polyline] = []
    current: Point = (0.0, 0.0)
    start: Point = current
    active: Polyline = []
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
        if op == "M":
            point = _read_point(tokens, index, current if relative else (0.0, 0.0))
            index += 2
            if active:
                paths.append(active)
            current = point
            start = point
            active = [current]
            command = "l" if relative else "L"
            last_control = None
        elif op == "L":
            point = _read_point(tokens, index, current if relative else (0.0, 0.0))
            index += 2
            current = point
            active.append(current)
            last_control = None
        elif op == "H":
            value_x = float(tokens[index])
            index += 1
            current = (current[0] + value_x, current[1]) if relative else (value_x, current[1])
            active.append(current)
            last_control = None
        elif op == "V":
            value_y = float(tokens[index])
            index += 1
            current = (current[0], current[1] + value_y) if relative else (current[0], value_y)
            active.append(current)
            last_control = None
        elif op == "C":
            p1 = _read_point(tokens, index, current if relative else (0.0, 0.0))
            p2 = _read_point(tokens, index + 2, current if relative else (0.0, 0.0))
            p3 = _read_point(tokens, index + 4, current if relative else (0.0, 0.0))
            index += 6
            active.extend(_cubic_points(current, p1, p2, p3))
            current = p3
            last_control = p2
        elif op == "S":
            p1 = _reflect_point(last_control, current) if last_control else current
            p2 = _read_point(tokens, index, current if relative else (0.0, 0.0))
            p3 = _read_point(tokens, index + 2, current if relative else (0.0, 0.0))
            index += 4
            active.extend(_cubic_points(current, p1, p2, p3))
            current = p3
            last_control = p2
        elif op == "Q":
            p1 = _read_point(tokens, index, current if relative else (0.0, 0.0))
            p2 = _read_point(tokens, index + 2, current if relative else (0.0, 0.0))
            index += 4
            active.extend(_quadratic_points(current, p1, p2))
            current = p2
            last_control = p1
        elif op == "T":
            p1 = _reflect_point(last_control, current) if last_control else current
            p2 = _read_point(tokens, index, current if relative else (0.0, 0.0))
            index += 2
            active.extend(_quadratic_points(current, p1, p2))
            current = p2
            last_control = p1
        elif op == "A":
            point = _read_point(tokens, index + 5, current if relative else (0.0, 0.0))
            index += 7
            current = point
            active.append(current)
            last_control = None
        elif op == "Z":
            if active and active[-1] != start:
                active.append(start)
            command = ""
            last_control = None
        else:
            raise ValueError(f"SVG path command nicht unterstuetzt: {command}")

    if active:
        paths.append(active)
    return paths


def _read_point(tokens: list[str], index: int, base: Point) -> Point:
    return base[0] + float(tokens[index]), base[1] + float(tokens[index + 1])


def _reflect_point(point: Point | None, around: Point) -> Point:
    if point is None:
        return around
    return around[0] * 2 - point[0], around[1] * 2 - point[1]


def _cubic_points(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 16) -> Polyline:
    points = []
    for step in range(1, steps + 1):
        t = step / steps
        mt = 1 - t
        x = mt**3 * p0[0] + 3 * mt**2 * t * p1[0] + 3 * mt * t**2 * p2[0] + t**3 * p3[0]
        y = mt**3 * p0[1] + 3 * mt**2 * t * p1[1] + 3 * mt * t**2 * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def _quadratic_points(p0: Point, p1: Point, p2: Point, steps: int = 12) -> Polyline:
    points = []
    for step in range(1, steps + 1):
        t = step / steps
        mt = 1 - t
        x = mt**2 * p0[0] + 2 * mt * t * p1[0] + t**2 * p2[0]
        y = mt**2 * p0[1] + 2 * mt * t * p1[1] + t**2 * p2[1]
        points.append((x, y))
    return points


def _normalize(polyline: Polyline, offset_x: float, offset_y: float, scale_x: float, scale_y: float) -> Polyline:
    return [((x - offset_x) * scale_x, (y - offset_y) * scale_y) for x, y in polyline]


def _float_attr(element: ET.Element, name: str) -> float:
    return _parse_length(element.get(name), 0.0)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
