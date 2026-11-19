# DeluxeCHD

Batch-convert CD images to compressed **CHD** files with MAME's `chdman`. Point it at a folder of
`.cue`/`.bin` games (loose, one folder per game, or inside `.zip`/`.7z`/`.rar` archives) and it
converts everything, optionally re-zips the output, and can delete the originals once each new CHD
has been verified. Built for PS1 libraries, but it works with any CD image that has a `.cue` sheet.

- Follows your system theme: light/dark and accent colour on Windows, and your KDE Plasma colour
  scheme on Linux (including Material You schemes), updated live.
- Checks GitHub for a new version on startup and can download and install it for you
  (AppImage and Windows installer builds).

## Download

Download directly. These links always point to the newest release:

| Platform | Download |
| --- | --- |
| Windows 10/11 (x64) | [DeluxeCHD-Setup-x64.exe](https://github.com/sethori/DeluxeCHD/releases/latest/download/DeluxeCHD-Setup-x64.exe). Bundles `chdman` and 7-Zip. No extra installs needed. |
| Linux (x86_64) | [DeluxeCHD-x86_64.AppImage](https://github.com/sethori/DeluxeCHD/releases/latest/download/DeluxeCHD-x86_64.AppImage) |

Checksums for both are in [SHA256SUMS](https://github.com/sethori/DeluxeCHD/releases/latest/download/SHA256SUMS). Older versions are on the [Releases](https://github.com/sethori/DeluxeCHD/releases) page.

Both builds check for updates on startup and can install them for you, however you installed them.

### Linux

The AppImage uses the `chdman` and `7z` already on your system:

```bash
# Arch
sudo pacman -S mame-tools p7zip          # unrar is an optional fallback for .rar
# Debian/Ubuntu
sudo apt install mame-tools p7zip-full
```

**Option 1: download the AppImage directly.** Make it executable and run it:

```bash
chmod +x DeluxeCHD-x86_64.AppImage
./DeluxeCHD-x86_64.AppImage
```

Keep it somewhere you can write to (for example `~/Applications`) so it can update itself. To get a
menu entry, use a tool like Gear Lever or AppImageLauncher, or use option 2.

**Option 2: install script.** Downloads the AppImage to `~/.local/bin`, checks its checksum, and adds
a menu entry and icon:

```bash
curl -sSL https://raw.githubusercontent.com/sethori/DeluxeCHD/main/install.sh | bash
```

## Safety

DeluxeCHD only deletes originals when you turn on **Delete originals**, and then only after
`chdman verify` passes on the new CHD (for multi-disc games, after every disc passes). Loose games
lose only the files their `.cue` references. Empty leftover folders are cleaned up, but never above
the folder you picked.

## Building from source

```bash
pip install -r requirements.txt
python3 run.py                               # run from source
python3 -m unittest discover -s tests        # engine tests (stub chdman, no Qt needed)

pip install -r requirements-build.txt
python3 packaging/make_icons.py
pyinstaller packaging/DeluxeCHD.spec         # dist/DeluxeCHD/
packaging/linux/build_appimage.sh            # dist/DeluxeCHD-x86_64.AppImage
```

The Windows installer is built with Inno Setup by GitHub Actions (`.github/workflows/build.yml`).
Pushing a `vX.Y.Z` tag that matches `__version__` in `src/deluxechd/__init__.py` publishes a release.
