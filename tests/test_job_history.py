from laser_control.job_history import (
    JobHistoryEntry,
    append_job_history,
    export_job_history,
    import_job_history,
    load_job_history,
)


def test_job_history_uses_configurable_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(tmp_path / "history.json"))
    entry = JobHistoryEntry(
        timestamp="2026-05-01T12:00:00",
        material_name="Probe",
        operation_mode="gravieren",
        power_percent=30,
        speed_mm_min=1000,
        passes=1,
        work_width_mm=100,
        work_height_mm=80,
        command_count=5,
        movement_count=2,
        estimated_runtime_seconds=3.5,
        warning_count=0,
        result="good",
        notes="ok",
    )

    append_job_history(entry)

    loaded = load_job_history()
    assert loaded[0].material_name == "Probe"
    assert loaded[0].result == "good"


def test_job_history_exports_and_imports(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.json"
    exported = tmp_path / "exported.json"
    target = tmp_path / "target.json"
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(source))
    append_job_history(
        JobHistoryEntry(
            timestamp="2026-05-01T12:00:00",
            material_name="Probe",
            operation_mode="gravieren",
            power_percent=30,
            speed_mm_min=1000,
            passes=1,
            work_width_mm=100,
            work_height_mm=80,
            command_count=5,
            movement_count=2,
            estimated_runtime_seconds=3.5,
            warning_count=0,
            result="problem",
            notes="zu hell",
        )
    )
    export_job_history(str(exported))

    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(target))
    imported = import_job_history(str(exported))

    assert imported[0].result == "problem"
    assert load_job_history()[0].notes == "zu hell"
