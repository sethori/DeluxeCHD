#!/usr/bin/env bash
set -e

# Configuration
REPO="sethori/DeluxeCHD"
BIN_DIR="$HOME/.local/bin"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
APP_DIR="$HOME/.local/share/applications"
TMP_DIR=$(mktemp -d)

echo "Fetching latest DeluxeCHD release asset..."
LATEST_URL=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" \
  | grep "browser_download_url" \
  | grep "DeluxeCHD_linux.tar.gz" \
  | cut -d '"' -f 4)

if [ -z "$LATEST_URL" ]; then
    echo "Error: Could not find the latest release asset on GitHub."
    exit 1
fi

echo "Downloading DeluxeCHD binary tarball..."
curl -L "$LATEST_URL" -o "$TMP_DIR/DeluxeCHD_linux.tar.gz"

echo "Extracting binary to local path..."
mkdir -p "$BIN_DIR"
tar -xzf "$TMP_DIR/DeluxeCHD_linux.tar.gz" -C "$TMP_DIR"
mv "$TMP_DIR/DeluxeCHD" "$BIN_DIR/DeluxeCHD"
chmod +x "$BIN_DIR/DeluxeCHD"

echo "Installing scalable system application icon asset..."
mkdir -p "$ICON_DIR"
curl -sSL "https://raw.githubusercontent.com/$REPO/main/src/com.sethori.DeluxeCHD.svg" -o "$ICON_DIR/com.sethori.DeluxeCHD.svg"

echo "Generating native application menu desktop entry shortcut..."
mkdir -p "$APP_DIR"
cat << EOF > "$APP_DIR/com.sethori.DeluxeCHD.desktop"
[Desktop Entry]
Type=Application
Version=1.0
Name=DeluxeCHD
Comment=Batch convert zipped PS1 games to CHD format
Exec=$BIN_DIR/DeluxeCHD
Icon=com.sethori.DeluxeCHD
Terminal=false
Categories=Utility;FileTools;
StartupWMClass=DeluxeCHD
EOF

if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APP_DIR"
fi

rm -rf "$TMP_DIR"
echo "============================================="
echo " DeluxeCHD installation execution finished!"
echo "============================================="
