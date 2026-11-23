from laser_control.artwork_interaction import ArtworkSnapService


def test_snap_to_workspace_center() -> None:
    result = ArtworkSnapService(3.0).snap(
        42.0,
        39.0,
        20.0,
        20.0,
        100.0,
        100.0,
    )

    assert result.x_mm == 40.0
    assert result.y_mm == 40.0
    assert result.vertical_guide_mm == 50.0
    assert result.horizontal_guide_mm == 50.0


def test_snap_to_workspace_edges() -> None:
    service = ArtworkSnapService(3.0)

    lower_left = service.snap(2.0, 1.0, 20.0, 10.0, 100.0, 80.0)
    upper_right = service.snap(79.0, 71.0, 20.0, 10.0, 100.0, 80.0)

    assert (lower_left.x_mm, lower_left.y_mm) == (0.0, 0.0)
    assert (upper_right.x_mm, upper_right.y_mm) == (80.0, 70.0)


def test_snap_can_be_disabled() -> None:
    result = ArtworkSnapService(3.0).snap(
        39.0,
        41.0,
        20.0,
        20.0,
        100.0,
        100.0,
        enabled=False,
    )

    assert (result.x_mm, result.y_mm) == (39.0, 41.0)
    assert result.vertical_guide_mm is None
    assert result.horizontal_guide_mm is None
