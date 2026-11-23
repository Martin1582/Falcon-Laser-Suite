from laser_control.workspace_coordinates import WorkspaceCoordinateMapper


def test_wpos_zero_zero_maps_to_lower_left_origin() -> None:
    mapper = WorkspaceCoordinateMapper(10.0, 20.0, 100.0, 80.0, 2.0)

    assert mapper.to_screen(0.0, 0.0) == (10.0, 180.0)


def test_wpos_max_maps_to_opposite_upper_right_corner() -> None:
    mapper = WorkspaceCoordinateMapper(10.0, 20.0, 100.0, 80.0, 2.0)

    assert mapper.to_screen(100.0, 80.0) == (210.0, 20.0)


def test_workspace_y_axis_is_inverted_once_for_qt() -> None:
    mapper = WorkspaceCoordinateMapper(0.0, 0.0, 100.0, 100.0, 1.0)

    _, y_at_zero = mapper.to_screen(0.0, 0.0)
    _, y_at_plus = mapper.to_screen(0.0, 10.0)

    assert y_at_plus < y_at_zero
    assert y_at_zero - y_at_plus == 10.0


def test_bounds_rect_uses_upper_workspace_y_as_screen_top() -> None:
    mapper = WorkspaceCoordinateMapper(10.0, 20.0, 100.0, 80.0, 2.0)

    assert mapper.rect_to_screen(5.0, 10.0, 25.0, 30.0) == (20.0, 120.0, 40.0, 40.0)


def test_screen_coordinates_roundtrip_to_workspace() -> None:
    mapper = WorkspaceCoordinateMapper(10.0, 20.0, 100.0, 80.0, 2.0)

    screen = mapper.to_screen(25.0, 30.0)

    assert mapper.to_workspace(*screen) == (25.0, 30.0)
