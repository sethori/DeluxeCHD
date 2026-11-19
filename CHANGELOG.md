# Changelog

All notable changes to DeluxeCHD are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Multi-disc support. Each `.cue` in a per-game folder or archive is converted to its own `.chd`.
- New CHDs are checked with `chdman verify` before they count as successful.
- `chdman` error output now appears in the log.
- README lists `p7zip` (and optional `unrar`) for `.7z`/`.rar` archives.
- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and this changelog.

### Fixed
- The "Re-zip" option crashed with `NameError: final_zip` after conversion.
- Re-zipping when the output zip has the same name as the original archive now replaces the original safely.
- Archives with several discs converted only the first disc and then deleted the archive, losing the other discs.

### Changed
- Loose-game deletion removes only the `.bin` files referenced by the `.cue`. Before, any `.bin` whose name started with the game name was deleted (e.g. "FF" deleting "FF VII").
- Originals are deleted only when every disc of an item converts and verifies.
- Conversion logic moved into `DeluxeCHDWorker.convert_cue()`.

### Removed
- Tracked PyInstaller output (`build/`, `dist/`) removed from git. `.gitignore` replaced with the intended rules from the old `gitignore.txt`.

## [1.0.0] - 2026-06-19

### Added
- First release: PyQt6 GUI for batch-converting `.cue`/`.bin` images (loose, per-game folders, `.zip`/`.7z`/`.rar` archives) to CHD with `chdman`.
- Options to delete originals, re-zip the output, and open the folder when finished.
- Live elapsed/ETA display, progress bar, and space-saved summary.
- `install.sh` one-line installer (binary, icon, desktop entry).

[Unreleased]: https://github.com/sethori/DeluxeCHD/compare/v1.0...HEAD
[1.0.0]: https://github.com/sethori/DeluxeCHD/releases/tag/v1.0
