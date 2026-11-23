from __future__ import annotations

from dataclasses import dataclass, field
from math import cos, hypot, radians, sin

from laser_control.artwork_transform import ArtworkBounds
from laser_control.layers import JobLayer, LayerType, OverscanMode
from laser_control.svg_import import Point, Polyline, path_bounds


SUPPORTED_HATCH_ANGLES = (0, 45, 90)
MAX_RECOMMENDED_FILL_LINES = 20_000
FALCON_10W_ACCELERATION_MM_S2 = 500.0
OVERSCAN_MIN_MM = 2.0
OVERSCAN_MAX_MM = 10.0


@dataclass(frozen=True)
class OverscanSegment:
    entry: Point
    engraving_start: Point
    engraving_end: Point
    exit: Point
    requested_mm: float
    entry_mm: float
    exit_mm: float

    @property
    def additional_distance_mm(self) -> float:
        return self.entry_mm + self.exit_mm

    @property
    def was_clamped(self) -> bool:
        return self.entry_mm + 1e-6 < self.requested_mm or self.exit_mm + 1e-6 < self.requested_mm


@dataclass(frozen=True)
class FillToolpath:
    layer_name: str
    layer_order: int
    spacing_mm: float
    angle_deg: int
    bounds: ArtworkBounds
    segments: list[Polyline]
    closed_shape_count: int
    open_shape_count: int
    warnings: list[str] = field(default_factory=list)
    overscan_enabled: bool = False
    overscan_mm: float = 0.0
    overscan_mode: str = OverscanMode.AUTOMATIC.value
    overscan_segments: list[OverscanSegment] = field(default_factory=list)
    unsafe_fill: bool = False

    @property
    def line_count(self) -> int:
        return len(self.segments)

    @property
    def additional_travel_mm(self) -> float:
        return sum(segment.additional_distance_mm for segment in self.overscan_segments)

    @property
    def overscan_clamped(self) -> bool:
        return any(segment.was_clamped for segment in self.overscan_segments)


def calculate_automatic_overscan_mm(
    speed_mm_min: int,
    acceleration_mm_s2: float = FALCON_10W_ACCELERATION_MM_S2,
    minimum_mm: float = OVERSCAN_MIN_MM,
    maximum_mm: float = OVERSCAN_MAX_MM,
) -> float:
    if speed_mm_min <= 0:
        raise ValueError("Gravurgeschwindigkeit muss groesser als 0 sein.")
    if acceleration_mm_s2 <= 0:
        raise ValueError("Maschinenbeschleunigung muss groesser als 0 sein.")
    if minimum_mm <= 0 or maximum_mm < minimum_mm:
        raise ValueError("Overscan-Grenzen sind ungueltig.")
    speed_mm_s = speed_mm_min / 60.0
    physical_distance = speed_mm_s * speed_mm_s / (2.0 * acceleration_mm_s2)
    falcon_calibrated_distance = speed_mm_min / 500.0
    return min(maximum_mm, max(minimum_mm, physical_distance, falcon_calibrated_distance))


def build_fill_toolpath(
    paths: list[Polyline],
    layer_name: str,
    layer_order: int,
    spacing_mm: float = 0.08,
    angle_deg: int = 0,
    speed_mm_min: int = 3000,
    overscan_enabled: bool = True,
    overscan_mode: OverscanMode = OverscanMode.AUTOMATIC,
    overscan_mm: float = 6.0,
    work_width_mm: float | None = None,
    work_height_mm: float | None = None,
) -> FillToolpath:
    if spacing_mm <= 0:
        raise ValueError("Fuellabstand muss groesser als 0 mm sein.")
    if angle_deg not in SUPPORTED_HATCH_ANGLES:
        raise ValueError(f"Fuellwinkel muss einer von {SUPPORTED_HATCH_ANGLES} sein.")

    closed = [path for path in paths if is_closed_path(path)]
    open_count = len(paths) - len(closed)
    warnings: list[str] = []
    if open_count:
        warnings.append(f"{open_count} offene Kontur(en) wurden nicht gefuellt.")
        warnings.append("SVG-Fuellung bei offenen Konturen aktuell nicht sicher unterstuetzt.")
    if not closed:
        return FillToolpath(
            layer_name,
            layer_order,
            spacing_mm,
            angle_deg,
            ArtworkBounds(0.0, 0.0, 0.0, 0.0),
            [],
            0,
            open_count,
            warnings or ["Keine geschlossene SVG-Flaeche fuer Fuellung gefunden."],
            unsafe_fill=True,
        )
    if open_count:
        min_x, min_y, max_x, max_y = path_bounds(closed)
        return FillToolpath(
            layer_name,
            layer_order,
            spacing_mm,
            angle_deg,
            ArtworkBounds(min_x, min_y, max_x, max_y),
            [],
            len(closed),
            open_count,
            warnings,
            unsafe_fill=True,
        )

    if has_nested_contours(closed):
        min_x, min_y, max_x, max_y = path_bounds(closed)
        warnings.append("SVG-Fuellung bei verschachtelten Konturen aktuell nicht sicher unterstuetzt.")
        return FillToolpath(
            layer_name,
            layer_order,
            spacing_mm,
            angle_deg,
            ArtworkBounds(min_x, min_y, max_x, max_y),
            [],
            len(closed),
            open_count,
            warnings,
            unsafe_fill=True,
        )

    all_segments: list[Polyline] = []
    for polygon in closed:
        all_segments.extend(hatch_polygon(polygon, spacing_mm, angle_deg))
    min_x, min_y, max_x, max_y = path_bounds(closed)
    if len(all_segments) > MAX_RECOMMENDED_FILL_LINES:
        warnings.append(
            f"Sehr hohe Fuelllinienanzahl: {len(all_segments)}. "
            "Groesseren Fuellabstand fuer fluessige Preview und kuerzere Laufzeit pruefen."
        )
    effective_overscan = 0.0
    overscan_segments: list[OverscanSegment] = []
    if overscan_enabled:
        effective_overscan = (
            calculate_automatic_overscan_mm(speed_mm_min)
            if overscan_mode == OverscanMode.AUTOMATIC
            else max(0.0, min(OVERSCAN_MAX_MM, overscan_mm))
        )
        overscan_segments = [
            build_overscan_segment(
                segment,
                effective_overscan,
                work_width_mm,
                work_height_mm,
            )
            for segment in all_segments
        ]
        if any(segment.was_clamped for segment in overscan_segments):
            warnings.append("Overscan wurde an der eingestellten Arbeitsflaeche begrenzt.")
    return FillToolpath(
        layer_name=layer_name,
        layer_order=layer_order,
        spacing_mm=spacing_mm,
        angle_deg=angle_deg,
        bounds=ArtworkBounds(min_x, min_y, max_x, max_y),
        segments=all_segments,
        closed_shape_count=len(closed),
        open_shape_count=open_count,
        warnings=warnings,
        overscan_enabled=overscan_enabled,
        overscan_mm=effective_overscan,
        overscan_mode=overscan_mode.value,
        overscan_segments=overscan_segments,
    )


def build_layer_fill_toolpaths(
    paths: list[Polyline],
    layers: list[JobLayer],
    work_width_mm: float | None = None,
    work_height_mm: float | None = None,
) -> list[FillToolpath]:
    return [
        build_fill_toolpath(
            paths,
            layer_name=layer.name,
            layer_order=layer.order,
            spacing_mm=layer.fill_spacing_mm,
            angle_deg=layer.fill_angle_deg,
            speed_mm_min=layer.speed_mm_min,
            overscan_enabled=layer.overscan_enabled and layer.layer_type == LayerType.ENGRAVE,
            overscan_mode=layer.overscan_mode,
            overscan_mm=layer.overscan_mm,
            work_width_mm=work_width_mm,
            work_height_mm=work_height_mm,
        )
        for layer in layers
        if layer.is_output_layer and layer.uses_fill
    ]


def build_overscan_segment(
    segment: Polyline,
    requested_mm: float,
    work_width_mm: float | None = None,
    work_height_mm: float | None = None,
) -> OverscanSegment:
    if len(segment) != 2:
        raise ValueError("Overscan benoetigt ein Fill-Segment mit genau zwei Punkten.")
    start, end = segment
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = hypot(dx, dy)
    if length <= 1e-9:
        return OverscanSegment(start, start, end, end, requested_mm, 0.0, 0.0)
    unit_x = dx / length
    unit_y = dy / length
    entry_limit = _distance_to_workspace_edge(start, -unit_x, -unit_y, work_width_mm, work_height_mm)
    exit_limit = _distance_to_workspace_edge(end, unit_x, unit_y, work_width_mm, work_height_mm)
    entry_mm = min(requested_mm, entry_limit)
    exit_mm = min(requested_mm, exit_limit)
    entry = (start[0] - unit_x * entry_mm, start[1] - unit_y * entry_mm)
    exit_point = (end[0] + unit_x * exit_mm, end[1] + unit_y * exit_mm)
    return OverscanSegment(entry, start, end, exit_point, requested_mm, entry_mm, exit_mm)


def _distance_to_workspace_edge(
    point: Point,
    unit_x: float,
    unit_y: float,
    work_width_mm: float | None,
    work_height_mm: float | None,
) -> float:
    if work_width_mm is None or work_height_mm is None:
        return float("inf")
    distances: list[float] = []
    if unit_x > 1e-12:
        distances.append((work_width_mm - point[0]) / unit_x)
    elif unit_x < -1e-12:
        distances.append((0.0 - point[0]) / unit_x)
    if unit_y > 1e-12:
        distances.append((work_height_mm - point[1]) / unit_y)
    elif unit_y < -1e-12:
        distances.append((0.0 - point[1]) / unit_y)
    valid = [max(0.0, value) for value in distances if value >= 0.0]
    return min(valid) if valid else 0.0


def hatch_polygon(polygon: Polyline, spacing_mm: float, angle_deg: int = 0) -> list[Polyline]:
    if not is_closed_path(polygon):
        return []
    scan_polygon = [_rotate(point, -angle_deg) for point in polygon]
    min_x, min_y, max_x, max_y = path_bounds([scan_polygon])
    segments: list[Polyline] = []
    line_index = 0
    y = min_y + spacing_mm / 2.0
    while y < max_y:
        intersections = _scanline_intersections(scan_polygon, y)
        for pair_index in range(0, len(intersections) - 1, 2):
            start_x = max(min_x, intersections[pair_index])
            end_x = min(max_x, intersections[pair_index + 1])
            if end_x - start_x <= 1e-9:
                continue
            start = _rotate((start_x, y), angle_deg)
            end = _rotate((end_x, y), angle_deg)
            if line_index % 2:
                start, end = end, start
            segments.append([start, end])
            line_index += 1
        y += spacing_mm
    return segments


def is_closed_path(path: Polyline, tolerance: float = 1e-6) -> bool:
    if len(path) < 4:
        return False
    first = path[0]
    last = path[-1]
    return abs(first[0] - last[0]) <= tolerance and abs(first[1] - last[1]) <= tolerance


def has_nested_contours(paths: list[Polyline]) -> bool:
    closed = [path for path in paths if is_closed_path(path)]
    bounds = [ArtworkBounds(*path_bounds([path])) for path in closed]
    inner_points: dict[int, Point] = {}
    for outer_index, outer in enumerate(closed):
        for inner_index, inner in enumerate(closed):
            if outer_index == inner_index:
                continue
            outer_bounds = bounds[outer_index]
            inner_bounds = bounds[inner_index]
            if not _bounds_contains(outer_bounds, inner_bounds):
                continue
            if inner_index not in inner_points:
                inner_points[inner_index] = _representative_point(inner)
            test_point = inner_points[inner_index]
            if point_in_polygon(test_point, outer):
                return True
    return False


def point_in_polygon(point: Point, polygon: Polyline) -> bool:
    x, y = point
    inside = False
    for index in range(len(polygon) - 1):
        x1, y1 = polygon[index]
        x2, y2 = polygon[index + 1]
        # The crossing test already excludes horizontal edges (y1 == y2), so dividing by the
        # signed y2 - y1 is safe; clamping it would flip the sign for descending edges.
        if ((y1 > y) != (y2 > y)) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _bounds_contains(outer: ArtworkBounds, inner: ArtworkBounds, tolerance: float = 1e-6) -> bool:
    return (
        outer.min_x <= inner.min_x + tolerance
        and outer.min_y <= inner.min_y + tolerance
        and outer.max_x >= inner.max_x - tolerance
        and outer.max_y >= inner.max_y - tolerance
        and (
            outer.min_x < inner.min_x - tolerance
            or outer.min_y < inner.min_y - tolerance
            or outer.max_x > inner.max_x + tolerance
            or outer.max_y > inner.max_y + tolerance
        )
    )


_REPRESENTATIVE_SCANLINES = 16


def _representative_point(path: Polyline) -> Point:
    """A point inside the closed contour, also for concave shapes.

    The vertex mean can fall outside a concave contour (e.g. into the opening of a C shape), so
    scan a horizontal line through the contour and take the middle of its widest interior span.
    """
    points = path[:-1] if is_closed_path(path) else path
    mean = (
        sum(point[0] for point in points) / max(1, len(points)),
        sum(point[1] for point in points) / max(1, len(points)),
    )
    ys = sorted({point[1] for point in points})
    gaps = list(zip(ys, ys[1:]))
    # Scan between neighbouring vertex heights so the line never passes through a vertex; a few
    # evenly spread gaps are enough and keep this linear for contours with many vertices.
    step = max(1, len(gaps) // _REPRESENTATIVE_SCANLINES)
    best: tuple[float, Point] | None = None
    for low, high in gaps[::step]:
        y = (low + high) / 2
        crossings = _scanline_intersections(path, y)
        for left, right in zip(crossings[0::2], crossings[1::2]):
            width = right - left
            if width > 0 and (best is None or width > best[0]):
                best = (width, ((left + right) / 2, y))
    return best[1] if best is not None else mean


def _scanline_intersections(polygon: Polyline, y: float) -> list[float]:
    intersections: list[float] = []
    for index in range(len(polygon) - 1):
        x1, y1 = polygon[index]
        x2, y2 = polygon[index + 1]
        if abs(y2 - y1) <= 1e-12:
            continue
        if not (min(y1, y2) <= y < max(y1, y2)):
            continue
        ratio = (y - y1) / (y2 - y1)
        intersections.append(x1 + ratio * (x2 - x1))
    intersections.sort()
    return intersections


def _rotate(point: Point, angle_deg: float) -> Point:
    angle = radians(angle_deg)
    cos_a = cos(angle)
    sin_a = sin(angle)
    x, y = point
    return x * cos_a - y * sin_a, x * sin_a + y * cos_a
