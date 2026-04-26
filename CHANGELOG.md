# Changelog

All notable changes to this project are documented in this file.

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
