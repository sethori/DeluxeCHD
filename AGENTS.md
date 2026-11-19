# AGENTS.md

Shared context for any AI coding agent (Claude, Codex, Antigravity, and others) working in this repo. Read this first. For change history, see `CHANGELOG.md`. Open it only when you need past context.

## What this project is

**DeluxeCHD** is a Linux desktop GUI app (Python 3 + PyQt6) that batch-converts PS1 disc images (`.cue`/`.bin`, loose, in per-game folders, or inside `.zip`/`.7z`/`.rar` archives) into compressed **CHD** files using MAME's `chdman`. It can optionally re-zip the output and delete the originals. Its users are people shrinking emulator ROM libraries.

- Single source file: `src/DeluxeCHD.py`
  - `DeluxeCHDWorker` (`QThread`): finds targets, extracts, converts, cleans up
  - `MainWindow`: the UI
- Icon: `src/com.sethori.DeluxeCHD.svg` (bundled into the binary via `DeluxeCHD.spec`)
- `install.sh`: downloads `DeluxeCHD_linux.tar.gz` from the latest GitHub release into `~/.local/bin`, installs the icon, and writes a `.desktop` entry
- Runtime dependencies are external CLIs: `chdman` (mame-tools), `unzip`, `zip`, `7z` (p7zip), and optionally `unrar`

## Build and release

```bash
pip install pyqt6 pyinstaller
python3 src/DeluxeCHD.py            # run from source
pyinstaller DeluxeCHD.spec          # builds dist/DeluxeCHD (single binary)
tar -czf DeluxeCHD_linux.tar.gz -C dist DeluxeCHD   # attach to a GitHub release
```

`build/` and `dist/` are gitignored. Never commit build output. `install.sh` depends on the release asset being named exactly `DeluxeCHD_linux.tar.gz`.

## Things every agent must know

- **The app deletes users' files.** Treat any change to deletion or cleanup logic as high risk. Current safety rules, which you must keep:
  - Originals are deleted only after `chdman verify` passes on the new CHD, and (for multi-disc items) only after **every** disc succeeds.
  - Loose-game deletion removes only the `.bin` files referenced by the `.cue`'s `FILE` lines. Never match by filename prefix.
  - Parent-folder cleanup (`purge_empty_parent_tree`) never goes above the folder the user selected, and only removes folders that are empty or hold only `.txt/.nfo/.url/.ini/.db` files.
- Multi-disc games: each `.cue` becomes its own `.chd`, both in per-game folders and inside archives.
- Archives are extracted into a `tmp_<name>` folder next to the archive. Scans skip `tmp_*` folders.
- There is no automated test suite yet. To test without `chdman`, stub it on `PATH` and stub the PyQt6 imports, then call `DeluxeCHDWorker.run()` directly. Say clearly what was and wasn't tested for real.
- Target platform is Linux only (`xdg-open`, `.desktop` files, `~/.local`).

## Milestones

- **v1.0** (2026-06-19): first public release. PyQt6 GUI, four scan modes, install script.
- **Unreleased** (2026-11-19): fixed the re-zip crash, made deletion safer (verify before delete, cue-referenced files only), added multi-disc support, untracked build artifacts.

## Known open issues

- The progress bar advances per item, not per byte (the ETA is byte-based).
- The re-zip path and real `chdman` runs haven't been verified on this branch since the 2026-11-19 changes.
- The README describes the app as PS1-only, but it works for any CD image with a `.cue` sheet.

## How to work here (owner preferences)

- **Communication:** concise, plain answers. Explain trade-offs only when they matter.
- **Git:** commit freely on feature branches with clear messages. **Ask before pushing**, opening PRs, or touching `main`.
- **Upkeep (required on every change):**
  - Add a line under `[Unreleased]` in `CHANGELOG.md` for any user-visible change or fix (Keep a Changelog format, SemVer).
  - Update the **Milestones** and **Known open issues** sections above when they change.
  - Keep this file short. It is loaded into every agent's context, so put detail in the changelog, not here.
