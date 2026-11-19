"""Locating and running the external command-line tools (chdman, 7z, unrar).

Bundled copies (the Windows build ships chdman.exe and 7z.exe in a ``tools`` folder)
take priority over whatever is on PATH.
"""
import os
import shutil
import subprocess
import sys

IS_WINDOWS = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)


def resource_dir():
    """Folder holding bundled data files (PyInstaller's _MEIPASS, or the package folder)."""
    if FROZEN:
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def asset_path(name):
    return os.path.join(resource_dir(), "assets", name)


def bundled_tools_dir():
    return os.path.join(resource_dir(), "tools")


def find_tool(*names):
    """Returns the full path of the first tool found (bundled first, then PATH), or None."""
    tools_dir = bundled_tools_dir()
    for name in names:
        exe = name + ".exe" if IS_WINDOWS and not name.endswith(".exe") else name
        candidate = os.path.join(tools_dir, exe)
        if os.path.isfile(candidate):
            return candidate
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def chdman():
    return find_tool("chdman")


def sevenzip():
    return find_tool("7z", "7zz", "7za")


def unrar():
    return find_tool("unrar")


def child_env():
    """Environment for child processes.

    A frozen Linux build sets LD_LIBRARY_PATH to its bundled libraries; system tools such as
    chdman must not inherit that, or they may load the wrong libstdc++/zlib.
    """
    env = dict(os.environ)
    if FROZEN and not IS_WINDOWS:
        orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if orig is not None:
            env["LD_LIBRARY_PATH"] = orig
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def run(args, **kwargs):
    """subprocess.run that never flashes a console window on Windows."""
    if IS_WINDOWS:
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    kwargs.setdefault("env", child_env())
    kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(args, **kwargs)


def tool_status():
    """{tool label: path or None} for the UI's status panel."""
    return {
        "chdman": chdman(),
        "7-Zip": sevenzip(),
    }
