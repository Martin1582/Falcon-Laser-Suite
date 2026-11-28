# Laser Control

Windows desktop tool for preparing and controlling engraving laser jobs.
The current UI uses PySide6/Qt.

## Entry Point

`main.py` starts `laser_control.pyside_app.run_app`, the PySide6/Qt main window.

This first version is intentionally safe-by-default:

- laser communication can run in simulator mode or GRBL/USB mode
- generated G-code stays visible in the app
- real job start asks for confirmation before sending G-code

## Start

```powershell
.\start.ps1
```

`start.ps1` automatically:

- uses `.venv\Scripts\python.exe` if available
- otherwise falls back to `py` or `python`
- installs missing dependencies from `requirements.txt` (including `pyserial`, `PySide6`, and `Pillow`)

Manual start (if preferred):

```powershell
py -m pip install -r requirements.txt
py main.py
```

If Windows says that no Python installation was found, install Python 3.12 or newer
from [python.org](https://www.python.org/downloads/windows/) and enable the
"Add python.exe to PATH" option during setup.

## Testing

Install dev dependencies:

```powershell
py -m pip install -r requirements-dev.txt
```

Run tests:

```powershell
.\run-tests.ps1
```

## Windows Build

The project contains a PyInstaller configuration for a folder-based Windows build:

```powershell
.\build.ps1
```

`build.ps1` installs `requirements-dev.txt` if needed, runs the test suite, and then builds with
`laser_control.spec`. The spec explicitly collects Pillow/PIL modules and image plugins so PNG/JPG
import keeps working in packaged builds.

Build output:

```text
dist\LaserControl\LaserControl.exe
```

## Recommended Workflow

Before every real engraving or cutting job:

1. connect and home the machine
2. run **Rahmen fahren** or **Dry Run** to verify path and positioning
3. run a short low-power trial on scrap material
4. start the real job only after confirming alignment and safety

`Dry Run` sends motion-only G-code and forces laser off (`M5`).

## Operation Modes

- **Gravieren**: uses `M4` (dynamic laser power), suitable for engraving.
- **Cutten**: uses `M3` (constant laser power), suitable for cutting passes.
- Mode selection affects generated preview G-code for all current job types.
- Parameters are remembered per mode (`Leistung`, `Geschwindigkeit`, `Durchgaenge`) for each selected material.
- In cut mode, aggressive settings trigger an extra warning dialog before hardware start.
- Built-in material profiles are starter values researched from Creality Falcon/Falcon CR 10W material tables.
  Always run a small test matrix before using a new material batch.

## Desktop Shortcut

Create a desktop launcher that starts `start.ps1`:

```powershell
.\create-shortcut.ps1
```

Optional custom icon:

- place an `app.ico` file in the project root
- run `.\create-shortcut.ps1` again to apply it

## Current Features

- project/job settings
- material profile selection and editable power/speed/pass values
- local assistant with risk score, recommendations, test-matrix generation, and job-history learning
- profile and job-history import/export as JSON
- project save/load as `.laser.json`
- SVG import for basic vector paths
- PNG/JPG import as raster sources for preview/preflight; hardware start is blocked until raster G-code exists
- automatic proportional AutoFit for imported SVG/PNG/JPG sources
- proportional SVG placement with automatic fit or manual width/offset
- material measurement from two laser head positions
- local material database for measured or manually entered sheets
- remove the selected artwork from the object list (button or Delete key, with confirmation;
  the source file stays on disk)
- start a new project without restarting (machine connection, machine and material profiles
  stay untouched)
- scrollable control sidebar for smaller screens
- basic work area preview
- simulator mode for connect, home, jog, frame, start, pause, and stop actions
- GRBL/USB mode with COM-port discovery, connect/disconnect, status, settings,
  homing, jog, pause/resume, and laser-off stop/reset
- automatic laser COM-port detection with GRBL probing
- GRBL status tracking for Idle/Hold/Alarm and current position
- generated G-code preview and rectangular frame starter output

## Code Structure

| Area | Modules |
|---|---|
| Main window | `pyside_app.py` (layout, preview wiring) plus feature mixins `window_machine`, `window_job`, `window_materials`, `window_artwork`, `window_project`, `window_status`, `window_theme`, `window_project_lifecycle` (remove item / new project), `window_item_state` |
| Widgets/panels | `work_area_preview`, `qt_panels`, `machine_panel`, `status_panel`, `console_log_panel`, `machine_profile_dialog`, `project_edit_actions` (panel and confirmation dialogs) |
| Controllers | `application_controller`, `workflow_controller`, `job_controller`, `machine_state`, `start_validation` |
| Artwork & toolpaths | `svg_import`, `artwork_import`, `artwork_transform`, `artwork_scaling`, `fill_toolpath`, `svg_optimization`, `toolpath_optimizer` |
| G-code & hardware | `gcode`, `gcode_analysis`, `serial_grbl`, `serial_executor`, `serial_autodetect`, `serial_consistency`, `laser` (simulator) |
| Data | `project`, `project_workspace` (Qt-free project and artwork cache state), `material_db`, `job_history`, `machine_profiles`, `services/` |

New UI behaviour belongs in the matching `window_*` mixin; machine and job logic belongs in the
controllers/services so it stays testable without Qt.

## Next Milestones

1. Raster engraving G-code for PNG/JPG sources (currently preview/preflight only).
2. Faster GRBL streaming (character-counting protocol instead of waiting for `ok` per line).
3. Improve SVG arc accuracy and grouped import diagnostics.
4. Continue moving logic out of the `window_*` mixins into Qt-free controllers.
