# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Changed
- Switched the default app entry point from Tkinter to a new PySide6/Qt main window.
- Updated startup dependency checks to install both `pyserial` and `PySide6`.

### Added
- Shared workflow helpers for cut-profile derivation and cut-parameter warnings.
- PySide6 work area preview, G-code editor, log panel, project controls, material database controls, and simulator/GRBL controls.
- Researched starter material profiles for common Falcon 10W engraving and cutting workflows.
- G-code analysis with path bounds, movement count, laser-power warnings, relative-positioning warnings, and runtime estimates.
- Job and profile services to keep preflight/profile logic outside the PySide6 window.
- Persistent top action bar for frequent machine actions.
- Local assistant layer with risk scoring, recommendations from saved job history, and 3x3 material test-matrix generation.
- Job history storage for saving good/problematic material outcomes and notes.
- Automatic COM-port detection that probes likely serial ports for a GRBL-compatible laser.
- Profile and job-history JSON import/export.
- GRBL status parsing for Idle/Hold/Alarm and reported machine position.

### Changed
- Project files now use version 2 and persist the selected operation mode while still loading v1 files.
- Material database storage now prefers the user AppData folder and falls back to the legacy project-local file.

### Fixed
- G-code motion validation now accepts `G0` travel moves.
- G-code analysis no longer misclassifies `G21` as a `G2` arc command.

## v0.1.1 - 2026-04-26

### Added
- Dedicated operation mode selector in UI: `Gravieren` and `Cutten`.
- Cut-specific parameter defaults derived from engraving profiles.
- Additional tests for cut profile derivation and cut warning thresholds.

### Changed
- Mode-aware G-code generation across current job types:
  - `Gravieren` uses `M4` (dynamic power)
  - `Cutten` uses `M3` (constant power)
- Job confirmation dialogs now include operation mode and active laser strategy.
- Profile parameters are persisted separately per operation mode during a session.

### Safety
- Added extra cut warning confirmation for aggressive cut settings (high power, low speed, many passes).

## v0.1.0 - 2026-04-26

### Added
- Initial Laser Control desktop app with simulator and GRBL/USB modes.
- Project save/load, SVG import, placement controls, material measurement, and material database.
- Desktop helper scripts: `start.ps1`, `run-tests.ps1`, and `create-shortcut.ps1`.
- Test suite for G-code preparation and SVG transform behavior.

### Changed
- Improved startup flow to auto-detect Python and auto-install missing runtime dependencies.
- Updated README with quick start, testing, shortcut setup, and safety workflow guidance.
- Added hardware preflight checks before GRBL job start (dependency, port, connection, homing).

### Fixed
- Corrected motion-command detection in job preparation so non-motion commands are not misclassified.
- Fixed engraving laser-mode sequencing so laser is re-enabled correctly after travel moves.
- Added Dry Run mode with motion-only sanitized G-code and forced laser-off (`M5`).
