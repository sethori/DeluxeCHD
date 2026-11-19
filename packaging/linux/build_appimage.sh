#!/usr/bin/env bash
# Wraps the PyInstaller one-folder build (dist/DeluxeCHD) into dist/DeluxeCHD-x86_64.AppImage.
# Usage: packaging/linux/build_appimage.sh   (run from anywhere, after `pyinstaller packaging/DeluxeCHD.spec`)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPDIR="$ROOT/build/AppDir"
TOOL_VERSION="${APPIMAGETOOL_VERSION:-1.9.1}"
TOOL="$ROOT/build/appimagetool-x86_64.AppImage"
ID="com.sethori.DeluxeCHD"

[ -x "$ROOT/dist/DeluxeCHD/DeluxeCHD" ] || { echo "Run pyinstaller packaging/DeluxeCHD.spec first" >&2; exit 1; }

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/lib" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/scalable/apps" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$ROOT/dist/DeluxeCHD" "$APPDIR/usr/lib/DeluxeCHD"
install -m 755 "$ROOT/packaging/linux/AppRun" "$APPDIR/AppRun"
install -m 644 "$ROOT/packaging/linux/$ID.desktop" "$APPDIR/$ID.desktop"
install -m 644 "$ROOT/packaging/linux/$ID.desktop" "$APPDIR/usr/share/applications/$ID.desktop"
install -m 644 "$ROOT/src/deluxechd/assets/$ID.svg" "$APPDIR/$ID.svg"
install -m 644 "$ROOT/src/deluxechd/assets/$ID.svg" "$APPDIR/usr/share/icons/hicolor/scalable/apps/$ID.svg"
if [ -f "$ROOT/build/icons/DeluxeCHD-256.png" ]; then
    install -m 644 "$ROOT/build/icons/DeluxeCHD-256.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/$ID.png"
    install -m 644 "$ROOT/build/icons/DeluxeCHD-256.png" "$APPDIR/.DirIcon"
fi

if [ ! -x "$TOOL" ]; then
    curl -fsSL -o "$TOOL" "https://github.com/AppImage/appimagetool/releases/download/$TOOL_VERSION/appimagetool-x86_64.AppImage"
    chmod +x "$TOOL"
fi

mkdir -p "$ROOT/dist"
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$TOOL" --no-appstream "$APPDIR" "$ROOT/dist/DeluxeCHD-x86_64.AppImage"
echo "Built $ROOT/dist/DeluxeCHD-x86_64.AppImage"
