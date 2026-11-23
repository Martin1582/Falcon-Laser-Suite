from laser_control.artwork_scaling import AutoFitService
from laser_control.artwork_transform import ArtworkTransform, transform_paths
from laser_control.gcode import build_polyline_gcode
from laser_control.models import MaterialProfile
from laser_control.preview_model import build_preview_model
from laser_control.layers import JobLayer, LayerType


def test_autofit_scales_large_artwork_without_distortion() -> None:
    result = AutoFitService().fit(600.0, 800.0, 400.0, 415.0)

    assert round(result.current_width_mm, 1) == 311.2
    assert round(result.current_height_mm, 1) == 415.0
    assert round(result.scale_factor, 3) == 0.519
    assert result.applied
    assert result.position == "zentriert"


def test_autofit_keeps_small_artwork_original_size_and_centers() -> None:
    result = AutoFitService().fit(100.0, 50.0, 400.0, 300.0)

    assert result.current_width_mm == 100.0
    assert result.current_height_mm == 50.0
    assert result.scale_factor == 1.0
    assert result.offset_x_mm == 150.0
    assert result.offset_y_mm == 125.0
    assert not result.applied


def test_autofit_transforms_vector_paths_consistently() -> None:
    paths = [[(10.0, 20.0), (610.0, 20.0), (610.0, 820.0)]]

    transformed, result = AutoFitService().fit_paths(paths, 400.0, 415.0)

    xs = [point[0] for polyline in transformed for point in polyline]
    ys = [point[1] for polyline in transformed for point in polyline]
    assert min(xs) == result.offset_x_mm
    assert min(ys) == result.offset_y_mm
    assert round(max(xs) - min(xs), 1) == 311.2
    assert round(max(ys) - min(ys), 1) == 415.0


def test_autofit_exposes_central_transform() -> None:
    transform = AutoFitService().fit_transform(600.0, 800.0, 400.0, 415.0)

    assert round(transform.current_width_mm, 1) == 311.2
    assert round(transform.current_height_mm, 1) == 415.0
    assert round(transform.scale, 3) == 0.519
    assert transform.bounds.within(400.0, 415.0)


def test_manual_width_transform_updates_scale_and_keeps_aspect_ratio() -> None:
    transform = ArtworkTransform(
        x_mm=10.0,
        y_mm=20.0,
        scale=1.0,
        original_width_mm=200.0,
        original_height_mm=100.0,
        current_width_mm=200.0,
        current_height_mm=100.0,
    ).with_width(50.0)

    assert transform.scale == 0.25
    assert transform.current_width_mm == 50.0
    assert transform.current_height_mm == 25.0
    assert transform.x_mm == 10.0
    assert transform.y_mm == 20.0


def test_manual_xy_position_is_applied_to_paths_without_y_inversion() -> None:
    transform = ArtworkTransform(
        x_mm=5.0,
        y_mm=7.0,
        scale=2.0,
        original_width_mm=10.0,
        original_height_mm=10.0,
        current_width_mm=20.0,
        current_height_mm=20.0,
    )

    paths = transform_paths([[(0.0, 0.0), (10.0, 10.0)]], transform)

    assert paths == [[(5.0, 7.0), (25.0, 27.0)]]


def test_transform_rejects_invalid_scale() -> None:
    transform = ArtworkTransform(
        x_mm=0.0,
        y_mm=0.0,
        scale=0.0,
        original_width_mm=10.0,
        original_height_mm=10.0,
        current_width_mm=10.0,
        current_height_mm=10.0,
    )

    try:
        transform.validate()
    except ValueError as exc:
        assert "Skalierung" in str(exc)
    else:
        raise AssertionError("ungueltige Skalierung wurde nicht abgelehnt")


def test_import_transform_defaults_to_zero_rotation_without_mirroring() -> None:
    transform = ArtworkTransform(0.0, 0.0, 1.0, 10.0, 20.0, 10.0, 20.0)
    source = [[(0.0, 0.0), (10.0, 0.0), (2.0, 20.0)]]

    assert transform.rotation_deg == 0.0
    assert transform.scale_x > 0
    assert transform.scale_y > 0
    assert transform_paths(source, transform) == source


def test_ninety_degree_rotation_updates_bounds() -> None:
    transform = ArtworkTransform(5.0, 7.0, 1.0, 10.0, 20.0, 10.0, 20.0).with_rotation(90.0)

    assert round(transform.current_width_mm, 6) == 20.0
    assert round(transform.current_height_mm, 6) == 10.0
    assert round(transform.bounds.max_x, 6) == 25.0
    assert round(transform.bounds.max_y, 6) == 17.0


def test_180_degree_rotation_only_happens_when_explicitly_requested() -> None:
    source = [[(0.0, 0.0), (10.0, 0.0), (2.0, 20.0)]]
    unchanged = ArtworkTransform(0.0, 0.0, 1.0, 10.0, 20.0, 10.0, 20.0)
    rotated = unchanged.with_rotation(180.0)

    assert transform_paths(source, unchanged) == source
    assert transform_paths(source, rotated) != source
    assert rotated.rotation_deg == 180.0


def test_height_change_updates_width_when_aspect_is_locked() -> None:
    transform = ArtworkTransform(0.0, 0.0, 1.0, 200.0, 100.0, 200.0, 100.0).with_height(25.0)

    assert transform.current_width_mm == 50.0
    assert transform.current_height_mm == 25.0
    assert transform.scale_percent == 25.0


def test_centering_uses_rotated_bounds() -> None:
    transform = ArtworkTransform(0.0, 0.0, 1.0, 10.0, 20.0, 10.0, 20.0, rotation_deg=90.0)

    centered = transform.centered_in(100.0, 80.0)

    assert round(centered.x_mm, 6) == 40.0
    assert round(centered.y_mm, 6) == 35.0


def test_preview_and_gcode_use_identical_transformed_points() -> None:
    source = [[(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)]]
    transform = ArtworkTransform(12.0, 8.0, 2.0, 10.0, 5.0, 20.0, 10.0, rotation_deg=90.0)
    transformed = transform_paths(source, transform)
    layer = JobLayer("Gravur", LayerType.ENGRAVE, True, True, 1000, 50, 10, 1)
    preview = build_preview_model(source, [layer], 100.0, 80.0, artwork_transform=transform)
    gcode = build_polyline_gcode(transformed, MaterialProfile("Test", 50, 1000, 1))

    assert preview.render_layers[0].paths[0].points == transformed[0]
    for x, y in transformed[0]:
        assert f"X{x:.2f} Y{y:.2f}" in gcode


def test_rotated_bounds_detect_workspace_overflow() -> None:
    transform = ArtworkTransform(90.0, 70.0, 1.0, 10.0, 20.0, 10.0, 20.0, rotation_deg=90.0)

    assert not transform.bounds.within(100.0, 80.0)
