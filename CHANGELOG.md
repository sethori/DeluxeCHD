# Changelog

All notable changes to DeluxeCHD are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

Every push to `main` is released automatically with the next version number (1.0.1, 1.0.2 … 1.0.9, 1.1.0;
see `packaging/version.py`). Each release on GitHub lists its commits. This file groups the notable
changes by date, with the first version that included them.

## 2026-11-19 (from 1.0.1)

The rewrite. A short-lived 2.0.0 release of it was withdrawn when the version scheme changed.

### Added
- New app icon: a CD with a diamond badge.
- Automatic versioning: every push to `main` publishes the next version.
- Windows support, with an installer that bundles `chdman` and 7-Zip.
- Linux AppImage. `install.sh` now installs the AppImage (and verifies its checksum).
- GitHub Actions workflow that tests, builds the AppImage and Windows installer, and publishes tagged releases.
- Update check on startup. The AppImage and Windows builds can download, verify (SHA-256) and install the new version, then restart. It can be turned off in Settings.
- New interface: sidebar with folder, scan mode and options; progress view with elapsed/remaining time; colour-coded log with copy/clear; tool status panel; drag-and-drop a folder onto the window.
- Colours follow the system theme: Windows light/dark and accent colour, and the KDE Plasma colour scheme on Linux (including Material You), updated live when it changes.
- Asks for confirmation before quitting during a conversion.
- Automated tests for the conversion engine (`tests/`).
- Multi-disc support. Each `.cue` in a per-game folder or archive is converted to its own `.chd`.
- New CHDs are checked with `chdman verify` before they count as successful.
- `chdman` error output now appears in the log.
- README lists `p7zip` (and optional `unrar`) for `.7z`/`.rar` archives.
- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and this changelog.

### Fixed
- With "Re-zip" and "Delete originals" both on, an archive named `Game.zip` was treated as already converted and deleted without making a CHD. If it did convert, the new zip was deleted afterwards.
- A failure on one item no longer stops the whole run.
- The "Re-zip" option crashed with `NameError: final_zip` after conversion.
- Re-zipping when the output zip has the same name as the original archive now replaces the original safely.
- Archives with several discs converted only the first disc and then deleted the archive, losing the other discs.

### Changed
- Rewritten on PySide6 and split into modules (engine, tools, theme, updater, UI). The engine has no Qt dependency.
- `.zip` archives are extracted and created with Python's `zipfile`. `unzip` and `zip` are no longer needed (7-Zip is still used for `.7z`/`.rar`, and as a fallback for unusual `.zip` files).
- The Start button is disabled when `chdman` isn't installed.
- Loose-game deletion removes only the `.bin` files referenced by the `.cue`. Before, any `.bin` whose name started with the game name was deleted (e.g. "FF" deleting "FF VII").
- Originals are deleted only when every disc of an item converts and verifies.
- Conversion logic moved into `DeluxeCHDWorker.convert_cue()`.

### Removed
- The `DeluxeCHD_linux.tar.gz` single-binary build, replaced by the AppImage.
- Tracked PyInstaller output (`build/`, `dist/`) removed from git. `.gitignore` replaced with the intended rules from the old `gitignore.txt`.

## [1.0.0] - 2026-06-19

### Added
- First release: PyQt6 GUI for batch-converting `.cue`/`.bin` images (loose, per-game folders, `.zip`/`.7z`/`.rar` archives) to CHD with `chdman`.
- Options to delete originals, re-zip the output, and open the folder when finished.
- Live elapsed/ETA display, progress bar, and space-saved summary.
- `install.sh` one-line installer (binary, icon, desktop entry).

[1.0.0]: https://github.com/sethori/DeluxeCHD/releases/tag/v1.0
