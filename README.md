# Laser Control

Windows desktop tool for preparing and controlling engraving laser jobs.

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
- installs missing dependencies from `requirements.txt` (including `pyserial`)

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
- project save/load as `.laser.json`
- SVG import for basic vector paths
- proportional SVG placement with automatic fit or manual width/offset
- material measurement from two laser head positions
- local material database for measured or manually entered sheets
- scrollable control sidebar for smaller screens
- basic work area preview
- simulator mode for connect, home, jog, frame, start, pause, and stop actions
- GRBL/USB mode with COM-port discovery, connect/disconnect, status, settings,
  homing, jog, pause/resume, and laser-off stop/reset
- generated G-code preview and rectangular frame starter output

## Next Milestones

1. Add automated tests for G-code preparation, SVG transforms, and GRBL status parsing.
2. Improve SVG arc accuracy and grouped import diagnostics.
3. Add PNG import/raster engraving.
4. Add a persistent profile library with import/export presets.
5. Expand safety checks (machine bounds, alarm/hold handling, and clearer preflight warnings).
