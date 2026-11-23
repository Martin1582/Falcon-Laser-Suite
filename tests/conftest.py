import os

import pytest

# Qt widgets need a display; render offscreen so tests also run headless (CI, SSH).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolate_user_storage(tmp_path, monkeypatch):
    """Keep tests away from the real user data in %APPDATA%\\Laser Control.

    Every storage location the app resolves via environment variables is pointed
    at the per-test tmp_path. Tests may still override individual variables.
    """
    storage = tmp_path / "user_storage"
    monkeypatch.setenv("APPDATA", str(storage / "appdata"))
    # Material profiles are stored next to the material DB (material_profiles.json).
    monkeypatch.delenv("LASER_CONTROL_PROFILE_DB", raising=False)
    monkeypatch.setenv("LASER_CONTROL_MATERIAL_DB", str(storage / "materials.json"))
    monkeypatch.setenv("LASER_CONTROL_JOB_HISTORY", str(storage / "history.json"))
    monkeypatch.setenv("LASER_CONTROL_DIAGNOSTIC_LOG", str(storage / "diagnostic.log"))
    monkeypatch.setenv("LASER_CONTROL_MACHINE_PROFILES", str(storage / "machine_profiles.json"))
