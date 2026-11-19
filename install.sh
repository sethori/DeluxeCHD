#!/usr/bin/env bash
# Installs the latest DeluxeCHD AppImage for the current user, with a menu entry and icon.
# The app updates itself in place afterwards (Settings → Check for updates).
set -euo pipefail

REPO="sethori/DeluxeCHD"
ASSET="DeluxeCHD-x86_64.AppImage"
BIN_DIR="$HOME/.local/bin"
TARGET="$BIN_DIR/DeluxeCHD.AppImage"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APP_DIR="$HOME/.local/share/applications"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

echo "Fetching the latest DeluxeCHD release..."
LATEST_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | grep '"browser_download_url"' | grep "/$ASSET\"" | cut -d '"' -f 4 || true)
SUMS_URL="https://github.com/$REPO/releases/latest/download/SHA256SUMS"

if [ -z "$LATEST_URL" ]; then
    echo "Error: couldn't find $ASSET in the latest GitHub release." >&2
    exit 1
fi

echo "Downloading $ASSET..."
curl -fL "$LATEST_URL" -o "$TMP_DIR/$ASSET"
curl -fsSL "$SUMS_URL" -o "$TMP_DIR/SHA256SUMS"
(cd "$TMP_DIR" && grep " \*\?$ASSET\$" SHA256SUMS | sha256sum -c -)

mkdir -p "$BIN_DIR"
install -m 755 "$TMP_DIR/$ASSET" "$TARGET"

# The 1.x installer put a plain binary here; it's replaced by the AppImage
if [ -f "$BIN_DIR/DeluxeCHD" ] && [ ! -L "$BIN_DIR/DeluxeCHD" ]; then
    rm -f "$BIN_DIR/DeluxeCHD"
    echo "Removed the old 1.x binary at $BIN_DIR/DeluxeCHD"
fi
ln -sf "$TARGET" "$BIN_DIR/DeluxeCHD"

echo "Installing icon and menu entry..."
mkdir -p "$ICON_DIR" "$APP_DIR"
curl -fsSL "https://raw.githubusercontent.com/$REPO/main/src/deluxechd/assets/com.sethori.DeluxeCHD.svg" \
  -o "$ICON_DIR/com.sethori.DeluxeCHD.svg"
cat > "$APP_DIR/com.sethori.DeluxeCHD.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=DeluxeCHD
Comment=Batch convert CD images (.cue/.bin, .zip, .7z, .rar) to CHD
Exec=$TARGET
Icon=com.sethori.DeluxeCHD
Terminal=false
Categories=Utility;Archiving;
StartupWMClass=DeluxeCHD
DESKTOP

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APP_DIR" || true
fi

if ! command -v chdman >/dev/null 2>&1; then
    echo
    echo "Note: chdman wasn't found. Install it before converting:"
    echo "  Arch: sudo pacman -S mame-tools    Debian/Ubuntu: sudo apt install mame-tools"
fi
echo "DeluxeCHD installed to $TARGET"
