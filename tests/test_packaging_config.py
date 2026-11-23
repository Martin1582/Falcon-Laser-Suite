from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_runtime_requirements_include_pillow() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()

    assert "pillow" in requirements


def test_dev_requirements_include_pyinstaller() -> None:
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").lower()

    assert "pyinstaller" in requirements


def test_pyinstaller_spec_collects_pillow_modules() -> None:
    spec = (ROOT / "laser_control.spec").read_text(encoding="utf-8")

    assert '["main.py"]' in spec
    assert "laser_control/app.py" not in spec
    assert 'collect_submodules("PIL")' in spec
    assert 'collect_submodules("PIL.ImagePlugin")' in spec
    assert "hiddenimports=hiddenimports" in spec


def test_build_script_uses_project_spec_and_dev_requirements() -> None:
    script = (ROOT / "build.ps1").read_text(encoding="utf-8")

    assert "requirements-dev.txt" in script
    assert "laser_control.spec" in script
    assert "import PIL" in script
    assert "PyInstaller" in script


def test_legacy_tkinter_app_is_removed() -> None:
    assert not (ROOT / "laser_control" / "app.py").exists()
    for module in (ROOT / "laser_control").rglob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert "import tkinter" not in source, module
        assert "from tkinter" not in source, module
