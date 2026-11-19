# -*- mode: python ; coding: utf-8 -*-
# Build with:  pyinstaller packaging/DeluxeCHD.spec   (from the repo root)
# Produces a one-folder build in dist/DeluxeCHD/ (used by the AppImage and the Windows installer).
#
# Optional:
#   build/tools/       bundled CLI tools (Windows: chdman.exe, 7z.exe, 7z.dll); copied to <app>/_internal/tools
#   build/icons/DeluxeCHD.ico   Windows executable icon (made by packaging/make_icons.py)
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
datas = [(os.path.join(ROOT, "src", "deluxechd", "assets"), "assets")]
tools_dir = os.path.join(ROOT, "build", "tools")
if os.path.isdir(tools_dir) and os.listdir(tools_dir):
    datas.append((tools_dir, "tools"))

ico = os.path.join(ROOT, "build", "icons", "DeluxeCHD.ico")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtSvg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore"],
    noarchive=False,
    optimize=0,
)
# ---- Trim the bundle --------------------------------------------------------------------------
# Unused Qt pieces (PDF/QML/Quick/virtual keyboard come in through optional plugins) and Qt
# translations (the app is English-only).
DROP_ANYWHERE = (
    "libQt6Pdf", "libQt6Qml", "libQt6Quick", "libQt6VirtualKeyboard", "libQt6Network",
    "libqpdf", "libqtvirtualkeyboardplugin", "libqgtk3",
    "Qt6Pdf", "Qt6Qml", "Qt6Quick", "Qt6VirtualKeyboard", "Qt6Network", "qpdf", "qtvirtualkeyboardplugin",
)
# Linux: libraries that must come from the user's system, not the build machine. Bundling them
# breaks GPU drivers, input methods and theming on newer distros.
LINUX_SYSTEM_LIBS = (
    "libstdc++", "libgcc_s", "libglib-", "libgobject-", "libgio-", "libgmodule-", "libgthread-",
    "libgtk-", "libgdk", "libatk", "libatspi", "libcairo", "libpango", "libharfbuzz", "libfontconfig",
    "libfreetype", "libpng", "libX", "libxcb.so", "libxcb-glx", "libxcb-render.so", "libxcb-shm",
    "libxcb-xfixes", "libxcb-sync", "libxcb-xkb", "libxkbcommon.so", "libdbus-", "libsystemd", "libkrb5",
    "libk5crypto", "libgssapi", "libcom_err", "libkeyutils", "libmount", "libblkid", "libselinux",
    "libseccomp", "libglycin", "libtinysparql", "libcloudproviders", "libjson-glib", "libepoxy",
    "libthai", "libdatrie", "libfribidi", "libgraphite2", "libpixman", "libbrotli", "libpcre2",
    "libxml2", "libicudata.so.7", "libicuuc.so.7", "libicui18n.so.7", "libGL", "libEGL", "libdrm",
    "libwayland-", "libgbm",
)


def keep(entry):
    dest = entry[0].replace("\\", "/")
    base = os.path.basename(dest)
    if any(base.startswith(p) for p in DROP_ANYWHERE):
        return False
    if "/translations/" in dest or dest.endswith("/translations"):
        return False
    if sys.platform.startswith("linux") and "/" not in dest.strip("/"):
        # top-level shared libraries only; Qt's own ICU under PySide6/Qt/lib is kept
        if any(base.startswith(p) for p in LINUX_SYSTEM_LIBS):
            return False
    return True


a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DeluxeCHD",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=ico if sys.platform == "win32" and os.path.exists(ico) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DeluxeCHD",
)
