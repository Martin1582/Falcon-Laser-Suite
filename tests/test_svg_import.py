from laser_control.svg_import import fit_paths_to_area, scale_paths_to_width


def test_fit_paths_to_area_respects_margin_and_area() -> None:
    paths = [[(10.0, 5.0), (110.0, 5.0), (110.0, 55.0), (10.0, 55.0)]]

    transformed, fitted_width, fitted_height = fit_paths_to_area(
        paths=paths,
        area_width=200.0,
        area_height=100.0,
        margin=10.0,
    )

    assert fitted_width <= 180.0
    assert fitted_height <= 80.0
    flat = [point for polyline in transformed for point in polyline]
    min_x = min(point[0] for point in flat)
    min_y = min(point[1] for point in flat)
    max_x = max(point[0] for point in flat)
    max_y = max(point[1] for point in flat)
    assert min_x >= 10.0
    assert min_y >= 10.0
    assert max_x <= 190.0
    assert max_y <= 90.0


def test_scale_paths_to_width_scales_height_proportionally() -> None:
    paths = [[(0.0, 0.0), (50.0, 0.0), (50.0, 25.0)]]

    transformed, fitted_width, fitted_height = scale_paths_to_width(
        paths=paths,
        target_width=100.0,
        offset_x=5.0,
        offset_y=7.0,
    )

    assert fitted_width == 100.0
    assert fitted_height == 50.0
    assert transformed[0][0] == (5.0, 7.0)
