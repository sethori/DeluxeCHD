"""Update checks and self-update against GitHub releases. No Qt here.

Install methods:
  * "appimage": the running AppImage ($APPIMAGE) is replaced in place, then relaunched.
  * "windows":  the Inno Setup installer is downloaded and run silently; it relaunches the app.
  * None:       running from source or an unmanaged copy. The UI opens the release page instead.

Every download is checked against a SHA-256 from GitHub (the asset's `digest`, or the
release's SHA256SUMS file). Nothing is installed if the hash can't be verified.
"""
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass

from deluxechd import GITHUB_REPO, __version__, tools

API_LATEST = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases/latest"
APPIMAGE_ASSET = "DeluxeCHD-x86_64.AppImage"
WINDOWS_ASSET = "DeluxeCHD-Setup-x64.exe"
CHECKSUMS_ASSET = "SHA256SUMS"
USER_AGENT = f"DeluxeCHD-Updater/{__version__}"


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    tag: str
    notes: str
    page_url: str
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    sha256: str = ""
    checksums_url: str = ""


def parse_version(text):
    """'v2.1.0' → (2, 1, 0). Pre-release suffixes are ignored."""
    core = re.split(r"[-+]", (text or "").strip().lstrip("vV"), maxsplit=1)[0]
    nums = [int(n) for n in re.findall(r"\d+", core)[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def is_newer(remote, local=__version__):
    return parse_version(remote) > parse_version(local)


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url, timeout=15, accept=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    if accept:
        req.add_header("Accept", accept)
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context())


def running_appimage():
    """Path of the AppImage we are running from, or None.

    $APPIMAGE/$APPDIR are inherited by child processes, so if another AppImage launched us they
    would name *that* app. Only trust them when our own executable lives inside $APPDIR.
    """
    appimage, appdir = os.environ.get("APPIMAGE"), os.environ.get("APPDIR")
    if not (sys.platform.startswith("linux") and tools.FROZEN and appimage and appdir):
        return None
    exe = os.path.realpath(sys.executable)
    root = os.path.realpath(appdir)
    if os.path.commonpath([exe, root]) != root or not os.path.isfile(appimage):
        return None
    return os.path.abspath(appimage)


def install_method():
    if running_appimage():
        return "appimage"
    if tools.IS_WINDOWS and tools.FROZEN:
        exe_dir = os.path.dirname(sys.executable)
        if any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in os.listdir(exe_dir)):
            return "windows"
    return None


def wanted_asset(method):
    return {"appimage": APPIMAGE_ASSET, "windows": WINDOWS_ASSET}.get(method)


def fetch_latest(method=None, timeout=15):
    """Returns the latest stable Release (pre-releases excluded)."""
    try:
        with _open(API_LATEST, timeout, "application/vnd.github+json") as resp:
            data = json.load(resp)
    except Exception as e:
        raise UpdateError(f"Couldn't reach GitHub: {e}") from e
    tag = data.get("tag_name") or ""
    rel = Release(version=tag.lstrip("vV"), tag=tag, notes=data.get("body") or "",
                  page_url=data.get("html_url") or RELEASES_PAGE)
    name = wanted_asset(method)
    for asset in data.get("assets", []):
        if asset.get("name") == CHECKSUMS_ASSET:
            rel.checksums_url = asset.get("browser_download_url", "")
        if name and asset.get("name") == name:
            rel.asset_name = name
            rel.asset_url = asset.get("browser_download_url", "")
            rel.asset_size = int(asset.get("size") or 0)
            digest = asset.get("digest") or ""
            if digest.startswith("sha256:"):
                rel.sha256 = digest.split(":", 1)[1].lower()
    return rel


def _expected_sha256(rel):
    if rel.sha256:
        return rel.sha256
    if rel.checksums_url:
        with _open(rel.checksums_url) as resp:
            for line in resp.read().decode("utf-8", "replace").splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[-1].lstrip("*") == rel.asset_name:
                    return parts[0].lower()
    raise UpdateError("The release has no checksum for this download, so it can't be verified.")


def download(rel, dest_path, progress=None, cancelled=lambda: False):
    """Downloads the release asset to dest_path and verifies its SHA-256."""
    if not rel.asset_url:
        raise UpdateError("This release has no download for your platform.")
    expected = _expected_sha256(rel)
    h = hashlib.sha256()
    done = 0
    try:
        with _open(rel.asset_url, timeout=30) as resp, open(dest_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or rel.asset_size or 0)
            while True:
                if cancelled():
                    raise UpdateError("Download cancelled.")
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except UpdateError:
        _silent_remove(dest_path)
        raise
    except Exception as e:
        _silent_remove(dest_path)
        raise UpdateError(f"Download failed: {e}") from e
    if h.hexdigest().lower() != expected:
        _silent_remove(dest_path)
        raise UpdateError("Downloaded file failed its checksum check. Nothing was installed.")
    return dest_path


def _silent_remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def staging_path(method, rel):
    """Where to save the download. AppImages go next to the current one so the swap is atomic."""
    if method == "appimage":
        target = running_appimage()
        folder = os.path.dirname(os.path.abspath(target))
        if not os.access(folder, os.W_OK) or not os.access(target, os.W_OK):
            raise UpdateError(f"Can't write to {folder}.")
        return os.path.join(folder, f".{os.path.basename(target)}.update")
    return os.path.join(tempfile.gettempdir(), rel.asset_name or "DeluxeCHD-update.bin")


def install_and_relaunch(method, downloaded):
    """Installs the verified download and starts the new version. The caller must quit right after."""
    if method == "appimage":
        target = running_appimage()
        os.chmod(downloaded, 0o755)
        os.replace(downloaded, target)  # atomic; the running copy keeps its open inode
        env = tools.child_env()
        for var in ("APPIMAGE", "APPDIR", "ARGV0", "OWD"):
            env.pop(var, None)
        subprocess.Popen([target], env=env, start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif method == "windows":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([downloaded, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                          "/RELAUNCH=1"], creationflags=flags, close_fds=True)
    else:
        raise UpdateError("Automatic install isn't supported for this copy of DeluxeCHD.")
