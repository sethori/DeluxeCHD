# AGENTS.md

Shared context for any AI coding agent (Claude, Codex, Antigravity, and others) working in this repo. Read this first. For change history, see `CHANGELOG.md`. Open it only when you need past context.

## What this project is

**DeluxeCHD** is a desktop GUI app (Python 3 + PySide6) for Linux and Windows that batch-converts CD images (`.cue`/`.bin`, loose, in per-game folders, or inside `.zip`/`.7z`/`.rar` archives) into compressed **CHD** files using MAME's `chdman`. It can optionally re-zip the output and delete the originals. Its users are people shrinking emulator ROM libraries.

Layout (`src/deluxechd/`):
- `converter.py`: the engine (`Converter`). Pure Python, no Qt. All scanning, conversion and deletion logic lives here.
- `tools.py`: finds `chdman`/`7z`/`unrar` (bundled `tools/` folder first, then PATH) and runs them (no console window on Windows, clean `LD_LIBRARY_PATH` in frozen Linux builds).
- `theme.py`: system colours. Reads `~/.config/kdeglobals` on Linux (KDE and Material You schemes, watched live), otherwise Qt's platform palette. Builds the stylesheet from a few tokens.
- `updater.py`: GitHub release check and self-update (AppImage swap in place, or silent Inno Setup run). Refuses any download without a matching SHA-256.
- `ui/`: `main_window.py` (sidebar + hero + log), `update_dialog.py`, `widgets.py`, `icons.py` (inline SVG icons).
- `run.py` is the entry point for source runs and PyInstaller.

## Build and release

```bash
pip install -r requirements.txt && python3 run.py      # run from source
python3 -m unittest discover -s tests                  # engine + updater tests
pip install -r requirements-build.txt
python3 packaging/make_icons.py && pyinstaller packaging/DeluxeCHD.spec   # dist/DeluxeCHD/
packaging/linux/build_appimage.sh                      # dist/DeluxeCHD-x86_64.AppImage
```

- CI (`.github/workflows/build.yml`) tests and builds the AppImage (ubuntu-22.04) and the Windows installer (Inno Setup, `packaging/windows/DeluxeCHD.iss`, bundles `chdman.exe` from a pinned, checksummed MAME release plus 7-Zip) on every push.
- **Every push to `main` is a release.** CI picks the next version from the git tags (`packaging/version.py`: each part counts 0-9 and rolls over, 1.0.9 → 1.1.0 → … 1.9.9 → 2.0.0), stamps it into the build, and publishes tag `vX.Y.Z` with the commit subjects as notes. Don't create version tags by hand, and don't edit `__version__` (it stays `0.0.0` in source). Write commit subjects users can read, since they appear in the in-app update dialog.
- **The updater and `install.sh` depend on the exact asset names** `DeluxeCHD-x86_64.AppImage`, `DeluxeCHD-Setup-x64.exe` and `SHA256SUMS`. Don't rename them.
- The spec file prunes host system libraries (glib, GTK, X11, libstdc++ and others) from the Linux bundle on purpose. Keep that list when changing it.
- `build/` and `dist/` are gitignored. Never commit build output.

## Things every agent must know

- **The app deletes users' files.** Treat any change to deletion or cleanup logic as high risk. Current safety rules, which you must keep (and which `tests/test_converter.py` covers):
  - Originals are deleted only after `chdman verify` passes on the new CHD, and (for multi-disc items) only after **every** disc succeeds.
  - Loose-game deletion removes only the `.bin` files referenced by the `.cue`'s `FILE` lines. Never match by filename prefix.
  - Never delete a file the run just produced (a re-zipped `Game.zip` can replace its own source archive).
  - Parent-folder cleanup (`purge_empty_parent_tree`) never goes above the folder the user selected, and only removes folders that are empty or hold only `.txt/.nfo/.url/.ini/.db` files.
- Multi-disc games: each `.cue` becomes its own `.chd`, both in per-game folders and inside archives.
- Archives are extracted into a `tmp_<name>` folder next to the archive. Scans skip `tmp_*` folders.
- `$APPIMAGE` is inherited by child processes. Only trust it when our executable is inside `$APPDIR` (see `updater.running_appimage`), or the updater could overwrite another app.
- Tests use a stub `chdman` on PATH. Real `chdman` runs and the Windows build can only be checked in CI or by hand. Say clearly what was and wasn't tested for real.

## Milestones

- **v1.0** (2026-06-19): first public release. PyQt6 GUI, four scan modes, install script.
- **v1.0.1** (2026-11-19): rewrite on PySide6. Windows installer + AppImage built in GitHub Actions, self-updater, system/KDE Material You theming, new UI, test suite, new CD-with-diamond icon, automatic versioning. (A 2.0.0 release of the rewrite was published and withdrawn the same day.) Also carries the earlier unreleased fixes (re-zip crash, safer deletion, multi-disc). The old PyQt6 app lives on the `legacy-v1` branch.

## Known open issues

- The progress bar advances per item, not per byte (the ETA is byte-based).
- Not yet verified for real: a full CI run, the Windows installer and its silent self-update, and conversions with a real `chdman` (only a stub has been used).
- There is no cancel button; quitting mid-run can leave a partial `.chd` or a `tmp_` folder (originals are safe).

## How to work here (owner preferences)

- **Communication:** concise, plain answers. Explain trade-offs only when they matter.
- **Git:** commit freely on feature branches with clear messages. **Ask before pushing**, opening PRs, or touching `main`.
- **Upkeep (required on every change):**
  - Add a line to `CHANGELOG.md` for any user-visible change or fix, under a heading for today's date (create it if needed).
  - Update the **Milestones** and **Known open issues** sections above when they change.
  - Keep this file short. It is loaded into every agent's context, so put detail in the changelog, not here.
