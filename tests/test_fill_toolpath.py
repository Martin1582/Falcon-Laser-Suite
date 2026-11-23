import math
import time

from laser_control.fill_toolpath import (
    build_fill_toolpath,
    build_layer_fill_toolpaths,
    calculate_automatic_overscan_mm,
)
from laser_control.gcode import build_layered_polyline_gcode
from laser_control.layers import JobLayer, LayerMode, LayerType, OverscanMode, layer_from_dict, layer_to_dict
from laser_control.preview_model import build_preview_model


def _layer(mode: LayerMode = LayerMode.FILL, spacing: float = 0.08, angle: int = 0) -> JobLayer:
    return JobLayer(
        "Gravur",
        LayerType.ENGRAVE,
        True,
        True,
        3000,
        40,
        10,
        1,
        mode,
        spacing,
        angle,
    )


def test_rectangle_generates_hatch_lines_with_correct_spacing_and_bounds() -> None:
    rectangle = [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0), (0.0, 0.0)]]

    fill = build_fill_toolpath(rectangle, "Gravur", 10, spacing_mm=1.0)

    assert fill.line_count == 5
    assert fill.bounds.width_mm == 10.0
    assert fill.bounds.height_mm == 5.0
    ys = [segment[0][1] for segment in fill.segments]
    assert ys == [0.5, 1.5, 2.5, 3.5, 4.5]


def test_circle_generates_fill_lines() -> None:
    circle = [
        [
            (5.0 + math.cos(math.tau * step / 48) * 5.0, 5.0 + math.sin(math.tau * step / 48) * 5.0)
            for step in range(49)
        ]
    ]

    fill = build_fill_toolpath(circle, "Kreis", 10, spacing_mm=0.5)

    assert fill.line_count > 10
    assert fill.closed_shape_count == 1
    assert all(len(segment) == 2 for segment in fill.segments)


def test_polygon_generates_only_segments_inside_shape() -> None:
    triangle = [[(0.0, 0.0), (10.0, 0.0), (5.0, 10.0), (0.0, 0.0)]]

    fill = build_fill_toolpath(triangle, "Polygon", 10, spacing_mm=1.0)

    assert fill.line_count == 10
    assert all(0.0 <= point[0] <= 10.0 for segment in fill.segments for point in segment)


def test_open_contour_generates_no_fill_and_warning() -> None:
    fill = build_fill_toolpath([[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]], "Offen", 10)

    assert fill.line_count == 0
    assert fill.open_shape_count == 1
    assert fill.unsafe_fill
    assert any("offene Kontur" in warning for warning in fill.warnings)


def test_rectangle_with_inner_hole_blocks_fill_generation() -> None:
    paths = [
        [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0), (5.0, 5.0)],
    ]

    fill = build_fill_toolpath(paths, "Loch", 10, spacing_mm=1.0)

    assert fill.unsafe_fill
    assert fill.line_count == 0
    assert any("verschachtelten Konturen" in warning for warning in fill.warnings)


def test_letter_o_like_nested_contours_block_fill_generation() -> None:
    outer = [
        (10.0 + math.cos(math.tau * step / 48) * 10.0, 10.0 + math.sin(math.tau * step / 48) * 10.0)
        for step in range(49)
    ]
    inner = [
        (10.0 + math.cos(math.tau * step / 48) * 4.0, 10.0 + math.sin(math.tau * step / 48) * 4.0)
        for step in range(49)
    ]

    fill = build_fill_toolpath([outer, inner], "O", 10, spacing_mm=1.0)

    assert fill.unsafe_fill
    assert fill.segments == []


def test_serpentine_alternates_scan_direction() -> None:
    rectangle = [[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0), (0.0, 0.0)]]

    fill = build_fill_toolpath(rectangle, "Gravur", 10, spacing_mm=1.0)

    assert fill.segments[0][0][0] < fill.segments[0][1][0]
    assert fill.segments[1][0][0] > fill.segments[1][1][0]
    assert fill.segments[2][0][0] < fill.segments[2][1][0]


def test_layer_fill_toolpaths_only_include_fill_enabled_layers() -> None:
    rectangle = [[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0), (0.0, 0.0)]]
    layers = [_layer(LayerMode.OUTLINE), _layer(LayerMode.OUTLINE_AND_FILL)]
    layers[1].order = 20

    fills = build_layer_fill_toolpaths(rectangle, layers)

    assert len(fills) == 1
    assert fills[0].layer_order == 20


def test_fill_layer_settings_roundtrip_through_project_data() -> None:
    layer = _layer(LayerMode.OUTLINE_AND_FILL, spacing=0.15, angle=90)

    restored = layer_from_dict(layer_to_dict(layer))

    assert restored.mode == LayerMode.OUTLINE_AND_FILL
    assert restored.fill_spacing_mm == 0.15
    assert restored.fill_angle_deg == 90
    assert restored.overscan_enabled
    assert restored.overscan_mode == OverscanMode.AUTOMATIC


def test_preview_contains_separate_fill_paths() -> None:
    rectangle = [[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0), (0.0, 0.0)]]
    layer = _layer(LayerMode.OUTLINE_AND_FILL, spacing=1.0)
    fills = build_layer_fill_toolpaths(rectangle, [layer])

    preview = build_preview_model(rectangle, [layer], 100.0, 80.0, fill_toolpaths=fills)

    path_types = {path.path_type for path in preview.render_layers[0].paths}
    assert path_types == {"outline", "fill", "overscan"}
    assert preview.fill_toolpaths == fills


def test_fill_gcode_uses_layer_parameters_and_m4() -> None:
    rectangle = [[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0), (0.0, 0.0)]]
    layer = _layer(LayerMode.FILL, spacing=1.0)
    fills = build_layer_fill_toolpaths(rectangle, [layer])

    gcode = build_layered_polyline_gcode(rectangle, [layer], fill_toolpaths=fills)

    assert "; fill spacing 1.00 mm angle 0 deg lines 2" in gcode
    assert "M4 ; dynamic laser power" in gcode
    assert "S400 F3000" in gcode
    assert "X4.00 Y0.50" in gcode
    assert "X0.00 Y1.50" in gcode
    assert "; overscan Automatisch 6.00 mm" in gcode
    assert "S0 F3000" in gcode


def test_unsafe_fill_gcode_is_not_generated() -> None:
    paths = [
        [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0), (0.0, 0.0)],
        [(5.0, 5.0), (15.0, 5.0), (15.0, 15.0), (5.0, 15.0), (5.0, 5.0)],
    ]
    layer = _layer(LayerMode.FILL, spacing=1.0)
    fills = build_layer_fill_toolpaths(paths, [layer])

    try:
        build_layered_polyline_gcode(paths, [layer], fill_toolpaths=fills)
    except ValueError as exc:
        assert "nicht sicher" in str(exc)
    else:
        raise AssertionError("Unsafe fill GCode was generated")


def test_outline_and_fill_runs_fill_before_outline_in_gcode_and_preview() -> None:
    rectangle = [[(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0), (0.0, 0.0)]]
    layer = _layer(LayerMode.OUTLINE_AND_FILL, spacing=1.0)
    fills = build_layer_fill_toolpaths(rectangle, [layer])

    gcode = build_layered_polyline_gcode(rectangle, [layer], fill_toolpaths=fills)
    preview = build_preview_model(rectangle, [layer], 100.0, 80.0, fill_toolpaths=fills)

    assert gcode.index("; toolpath fill") < gcode.index("; toolpath outline")
    path_types = [path.path_type for path in preview.render_layers[0].paths]
    assert path_types[: fills[0].line_count] == ["fill"] * fills[0].line_count
    assert path_types[-1] == "outline"


def test_large_rectangle_fill_generation_remains_fast() -> None:
    rectangle = [[(0.0, 0.0), (400.0, 0.0), (400.0, 415.0), (0.0, 415.0), (0.0, 0.0)]]

    started = time.perf_counter()
    fill = build_fill_toolpath(rectangle, "Falcon", 10, spacing_mm=0.08)
    elapsed = time.perf_counter() - started

    assert fill.line_count > 5_000
    assert elapsed < 1.0


def test_automatic_overscan_matches_falcon_speed_policy() -> None:
    assert calculate_automatic_overscan_mm(1000) == 2.0
    assert calculate_automatic_overscan_mm(2000) == 4.0
    assert calculate_automatic_overscan_mm(3000) == 6.0
    assert calculate_automatic_overscan_mm(5000) == 10.0
    assert calculate_automatic_overscan_mm(9000) == 10.0


def test_manual_overscan_is_used_for_fill() -> None:
    rectangle = [[(20.0, 0.0), (30.0, 0.0), (30.0, 2.0), (20.0, 2.0), (20.0, 0.0)]]
    layer = _layer(LayerMode.FILL, spacing=1.0)
    layer.overscan_mode = OverscanMode.MANUAL
    layer.overscan_mm = 3.5

    fill = build_layer_fill_toolpaths(rectangle, [layer], 100.0, 80.0)[0]

    assert fill.overscan_mm == 3.5
    assert fill.overscan_segments[0].entry == (16.5, 0.5)
    assert fill.overscan_segments[0].exit == (33.5, 0.5)


def test_overscan_is_clamped_to_workspace() -> None:
    rectangle = [[(1.0, 0.0), (9.0, 0.0), (9.0, 2.0), (1.0, 2.0), (1.0, 0.0)]]
    layer = _layer(LayerMode.FILL, spacing=1.0)

    fill = build_layer_fill_toolpaths(rectangle, [layer], 10.0, 10.0)[0]

    assert fill.overscan_segments[0].entry[0] == 0.0
    assert fill.overscan_segments[0].exit[0] == 10.0
    assert fill.overscan_clamped
    assert any("begrenzt" in warning for warning in fill.warnings)


def test_serpentine_overscan_follows_each_scan_direction() -> None:
    rectangle = [[(10.0, 0.0), (20.0, 0.0), (20.0, 3.0), (10.0, 3.0), (10.0, 0.0)]]
    fill = build_fill_toolpath(
        rectangle,
        "Gravur",
        10,
        spacing_mm=1.0,
        speed_mm_min=1000,
        work_width_mm=40.0,
        work_height_mm=20.0,
    )

    first, second = fill.overscan_segments[:2]
    assert first.entry[0] < first.engraving_start[0] < first.engraving_end[0] < first.exit[0]
    assert second.entry[0] > second.engraving_start[0] > second.engraving_end[0] > second.exit[0]


def test_outline_only_generates_no_overscan_gcode() -> None:
    rectangle = [[(10.0, 0.0), (20.0, 0.0), (20.0, 2.0), (10.0, 2.0), (10.0, 0.0)]]
    layer = _layer(LayerMode.OUTLINE, spacing=1.0)

    fills = build_layer_fill_toolpaths(rectangle, [layer], 100.0, 80.0)
    gcode = build_layered_polyline_gcode(rectangle, [layer], fill_toolpaths=fills)

    assert fills == []
    assert "overscan" not in gcode.lower()


def test_cut_fill_does_not_enable_overscan() -> None:
    rectangle = [[(10.0, 0.0), (20.0, 0.0), (20.0, 2.0), (10.0, 2.0), (10.0, 0.0)]]
    layer = _layer(LayerMode.FILL, spacing=1.0)
    layer.layer_type = LayerType.CUT

    fill = build_layer_fill_toolpaths(rectangle, [layer], 100.0, 80.0)[0]

    assert not fill.overscan_enabled
    assert fill.overscan_segments == []
