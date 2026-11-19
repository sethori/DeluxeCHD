"""The conversion engine. Pure Python, no Qt, so it can be tested on its own.

SAFETY RULES (this code deletes users' files; keep these intact):
  * Originals are deleted only after `chdman verify` passes on the new CHD, and for
    multi-disc items only after every disc succeeds.
  * Loose-game deletion removes only the files referenced by the .cue's FILE lines.
  * Parent-folder cleanup never goes above the folder the user selected, and only removes
    folders that are empty or hold only .txt/.nfo/.url/.ini/.db files.
"""
import os
import re
import shutil
import subprocess
import zipfile

from deluxechd import tools

MODES = ("recursive", "folders", "all_in_one", "archives")
ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar")
DISPOSABLE_EXTENSIONS = (".txt", ".nfo", ".url", ".ini", ".db")

# Log line kinds, used by the UI for colouring
INFO, SUCCESS, SKIP, ERROR, DETAIL = "info", "success", "skip", "error", "detail"


def _noop(*_args):
    pass


def is_within(path, root):
    """True if `path` is `root` or lies inside it (case-insensitive on Windows)."""
    path = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives on Windows
        return False


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class Converter:
    """Finds targets in `folder_path`, extracts, converts with chdman, and cleans up.

    Callbacks:
      on_file_started(display_name, current_index, total)
      on_progress(percent)
      on_log(text, kind)
    """

    def __init__(self, folder_path, mode, delete_originals, rezip_output,
                 on_file_started=_noop, on_progress=_noop, on_log=_noop):
        if mode not in MODES:
            raise ValueError(f"unknown mode: {mode}")
        self.folder_path = os.path.abspath(folder_path)
        self.mode = mode
        self.delete_originals = delete_originals
        self.rezip_output = rezip_output
        self.on_file_started = on_file_started
        self.on_progress = on_progress
        self.on_log = on_log

        self.total_bytes_to_process = 0
        self.bytes_processed_so_far = 0
        self.current_item_size = 0

    def log(self, text, kind=INFO):
        self.on_log(text, kind)

    # ---------- file helpers ----------

    @staticmethod
    def cue_bin_files(cue_path):
        """Returns the files a .cue sheet references (existing ones only), so we never touch unrelated files."""
        parent = os.path.dirname(cue_path)
        found = []
        try:
            with open(cue_path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = re.match(r'\s*FILE\s+(?:"([^"]+)"|(\S+))', line, re.IGNORECASE)
                    if m:
                        name = os.path.basename((m.group(1) or m.group(2)).replace("\\", "/"))
                        candidate = os.path.join(parent, name)
                        if os.path.isfile(candidate):
                            found.append(candidate)
        except OSError:
            pass
        return found

    def delete_loose_game(self, cue_path):
        """Deletes a .cue and only the data files it references."""
        for f in self.cue_bin_files(cue_path):
            os.remove(f)
        if os.path.exists(cue_path):
            os.remove(cue_path)

    def get_associated_size(self, path, t_type):
        """Size of an item and its files, for progress/ETA tracking."""
        if t_type == "archive":
            return os.path.getsize(path)
        if t_type == "folder":
            return sum(os.path.getsize(os.path.join(r, f)) for r, _, files in os.walk(path)
                       for f in files if os.path.exists(os.path.join(r, f)))
        if t_type == "loose_cue":
            return os.path.getsize(path) + sum(os.path.getsize(f) for f in self.cue_bin_files(path))
        return 0

    @staticmethod
    def extract_archive(archive_path, destination_dir):
        """Extracts .zip, .7z, or .rar. Zip uses Python's zipfile (path-traversal safe); 7z/rar use 7-Zip or unrar."""
        ext = os.path.splitext(archive_path)[1].lower()
        if ext == ".zip":
            try:
                with zipfile.ZipFile(archive_path) as zf:
                    zf.extractall(destination_dir)
                return
            except NotImplementedError:
                # Compression method zipfile can't handle (e.g. Deflate64); let 7-Zip try
                if not tools.sevenzip():
                    raise
        sevenzip = tools.sevenzip()
        if ext in (".7z", ".rar", ".zip") and sevenzip:
            tools.run([sevenzip, "x", "-y", f"-o{destination_dir}", archive_path],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        elif ext == ".rar" and tools.unrar():
            tools.run([tools.unrar(), "x", "-y", archive_path, destination_dir + os.sep],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        else:
            raise RuntimeError(f"Missing extraction tool (7z/unrar) for archive format: {ext}")

    @staticmethod
    def should_clean_directory(path):
        """True if a directory is empty or only contains disposable metadata files (e.g. .txt, .nfo)."""
        if not os.path.isdir(path):
            return False
        for _root, _dirs, files in os.walk(path):
            for f in files:
                if not f.lower().endswith(DISPOSABLE_EXTENSIONS):
                    return False
        return True

    def purge_empty_parent_tree(self, target_folder):
        """Walks up from target_folder deleting folders that are now empty or text-only.
        Never touches the user-selected folder or anything above it."""
        current = os.path.abspath(target_folder)
        stop_at = self.folder_path
        while (os.path.normcase(current) != os.path.normcase(stop_at)
               and is_within(current, stop_at)):
            if not self.should_clean_directory(current):
                break
            try:
                shutil.rmtree(current)
            except OSError:
                break
            current = os.path.dirname(current)

    def output_paths(self, out_base):
        out_chd = os.path.join(self.folder_path, f"{out_base}.chd")
        zip_name = f"{out_base}.zip" if self.delete_originals else f"{out_base}_CHD.zip"
        return out_chd, os.path.join(self.folder_path, zip_name)

    def convert_cue(self, cue_path, out_base, out_chd, out_zip, replace_path):
        """Converts one .cue to CHD (optionally zipped).
        Returns (final_size, label, error); final_size is None on failure."""
        chdman = tools.chdman()
        if not chdman:
            return None, "", "chdman not found"
        work = os.path.dirname(cue_path)
        tmp_chd = os.path.join(work, f"{out_base}.chd")
        res = tools.run([chdman, "createcd", "-i", cue_path, "-o", tmp_chd],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        text=True, errors="replace")
        if res.returncode != 0 or not os.path.exists(tmp_chd):
            lines = (res.stderr or "").strip().splitlines()
            if os.path.exists(tmp_chd):
                os.remove(tmp_chd)
            return None, "", "chdman engine failed" + (f" ({lines[-1]})" if lines else "")
        # Never report success (or allow deletion of originals) unless the new CHD verifies
        verify = tools.run([chdman, "verify", "-i", tmp_chd],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if verify.returncode != 0:
            os.remove(tmp_chd)
            return None, "", "CHD verification failed"
        if not self.rezip_output:
            shutil.move(tmp_chd, out_chd)
            return os.path.getsize(out_chd), "Raw CHD File", ""
        tmp_zip = os.path.join(work, f"{out_base}.chdtmp.zip")
        try:
            with zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zf:
                zf.write(tmp_chd, arcname=os.path.basename(tmp_chd))
            zip_ok = True
        except OSError:
            zip_ok = False
        os.remove(tmp_chd)
        if not zip_ok or not os.path.exists(tmp_zip):
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            return None, "", "zip step failed"
        # The new zip may share a name with the original archive it replaces
        if (self.delete_originals and replace_path
                and same_path(replace_path, out_zip)):
            os.remove(replace_path)
        shutil.move(tmp_zip, out_zip)
        return os.path.getsize(out_zip), "Compressed Zip", ""

    @staticmethod
    def cleanup_tmp(t_type, host_folder, base_name):
        tmp_root = os.path.join(host_folder, f"tmp_{base_name}")
        if t_type == "archive" and os.path.exists(tmp_root):
            shutil.rmtree(tmp_root)

    # ---------- scanning ----------

    def find_targets(self):
        targets = []
        if self.mode == "recursive":
            for root, _dirs, files in os.walk(self.folder_path):
                rel = os.path.relpath(root, self.folder_path)
                if any(part.startswith("tmp_") for part in rel.split(os.sep)):
                    continue
                for f in files:
                    full_path = os.path.join(root, f)
                    if f.lower().endswith(".cue"):
                        targets.append(("loose_cue", full_path))
                    elif f.lower().endswith(ARCHIVE_EXTENSIONS):
                        targets.append(("archive", full_path))
            return targets

        items = os.listdir(self.folder_path)
        for item in items:
            full_path = os.path.join(self.folder_path, item)
            if self.mode == "folders":
                if os.path.isdir(full_path) and not item.startswith("tmp_"):
                    cue_names = sorted(f for f in os.listdir(full_path) if f.lower().endswith(".cue"))
                    if len(cue_names) == 1:
                        targets.append(("folder", full_path))
                    else:
                        # Multi-disc folder: each .cue is converted to its own CHD
                        for cue_name in cue_names:
                            targets.append(("loose_cue", os.path.join(full_path, cue_name)))
            elif self.mode == "all_in_one":
                if item.lower().endswith(".cue"):
                    targets.append(("loose_cue", full_path))
            elif self.mode == "archives":
                if item.lower().endswith(ARCHIVE_EXTENSIONS):
                    targets.append(("archive", full_path))
        return targets

    # ---------- main loop ----------

    def run(self):
        """Processes everything. Returns total bytes saved."""
        try:
            targets = self.find_targets()
        except Exception as e:
            self.log(f"❌ Error reading directories: {e}", ERROR)
            return 0

        total_items = len(targets)
        if total_items == 0:
            self.log("No eligible games found matching search target criteria.", SKIP)
            return 0

        item_sizes = {}
        self.total_bytes_to_process = 0
        for t_type, path in targets:
            size = self.get_associated_size(path, t_type)
            item_sizes[path] = size
            self.total_bytes_to_process += size

        total_bytes_saved = 0
        self.bytes_processed_so_far = 0

        for index, (t_type, path) in enumerate(targets):
            self.current_item_size = item_sizes[path]
            try:
                total_bytes_saved += self.process_item(index, total_items, t_type, path)
            except Exception as e:  # keep going with the next item; originals are untouched on failure paths
                self.log(f"• ❌ {os.path.basename(path)} → ERROR: {e}", ERROR)
                self.cleanup_tmp(t_type, os.path.dirname(path), os.path.splitext(os.path.basename(path))[0])
            self.bytes_processed_so_far += self.current_item_size
            self.on_progress(int(((index + 1) / total_items) * 100))

        return total_bytes_saved

    def delete_original(self, t_type, path):
        if t_type == "archive":
            if os.path.exists(path):
                os.remove(path)
        elif t_type == "folder":
            if os.path.exists(path):
                shutil.rmtree(path)
        elif t_type == "loose_cue":
            self.delete_loose_game(path)

    def maybe_purge_parents(self, host_folder):
        if self.mode in ("recursive", "folders") and not same_path(host_folder, self.folder_path):
            self.purge_empty_parent_tree(host_folder)

    def process_item(self, index, total_items, t_type, path):
        """Handles one target. Returns bytes saved."""
        display_name = os.path.basename(path)
        self.on_file_started(display_name, index + 1, total_items)
        base_name = os.path.splitext(display_name)[0]
        host_folder = os.path.dirname(path)

        expected_chd, expected_zip = self.output_paths(base_name)
        expected = expected_zip if self.rezip_output else expected_chd

        # Output already exists: skip conversion (and optionally remove the original).
        # With re-zip + delete, "Game.zip" is both the original archive and the expected output;
        # that isn't a finished output, so it must be converted, not skipped and deleted.
        if os.path.exists(expected) and not same_path(expected, path):
            self.log(f"• ⏭️ {base_name} → Already Exists (Skipped conversion)", SKIP)
            if self.delete_originals:
                try:
                    if t_type == "archive" and os.path.exists(path):
                        os.remove(path)
                        self.log(f"  └─ Automatically deleted original archive: {display_name}", DETAIL)
                    elif t_type == "folder" and os.path.exists(path):
                        shutil.rmtree(path)
                        self.log(f"  └─ Automatically deleted original game subfolder: {display_name}", DETAIL)
                    elif t_type == "loose_cue":
                        self.delete_loose_game(path)
                        self.log(f"  └─ Automatically deleted original loose bin/cue: {base_name}", DETAIL)
                        self.maybe_purge_parents(host_folder)
                except Exception as clean_error:
                    self.log(f"  └─ ⚠️ Cleanup error tracking target: {clean_error}", ERROR)
            return 0

        cue_jobs = []  # (cue_path, output_base_name)
        if t_type == "loose_cue":
            cue_jobs = [(path, base_name)]
        elif t_type == "folder":
            sub_cues = sorted(f for f in os.listdir(path) if f.lower().endswith(".cue"))
            cue_jobs = [(os.path.join(path, sub_cues[0]), base_name)]
        elif t_type == "archive":
            tmp_root = os.path.join(host_folder, f"tmp_{base_name}")
            os.makedirs(tmp_root, exist_ok=True)
            try:
                self.extract_archive(path, tmp_root)
                found = sorted(os.path.join(r, f) for r, _, fs in os.walk(tmp_root)
                               for f in fs if f.lower().endswith(".cue"))
            except Exception as e:
                self.log(f"• ❌ {display_name} → Unpacking Failed ({e})", ERROR)
                self.cleanup_tmp(t_type, host_folder, base_name)
                return 0
            if not found:
                self.log(f"• ⏭️ {display_name} → Skipped (No .cue sheet inside archive)", SKIP)
                self.cleanup_tmp(t_type, host_folder, base_name)
                return 0
            if len(found) == 1:
                cue_jobs = [(found[0], base_name)]
            else:
                cue_jobs = [(c, os.path.splitext(os.path.basename(c))[0]) for c in found]

        saved = 0
        all_ok = True
        produced = []
        share = self.current_item_size / len(cue_jobs)
        for cue_path, out_base in cue_jobs:
            out_chd, out_zip = self.output_paths(out_base)
            if len(cue_jobs) > 1 and os.path.exists(out_zip if self.rezip_output else out_chd):
                self.log(f"• ⏭️ {out_base} → Already Exists (Skipped conversion)", SKIP)
                continue
            final_size, label, err = self.convert_cue(cue_path, out_base, out_chd, out_zip,
                                                      path if t_type == "archive" else None)
            if final_size is None:
                all_ok = False
                self.log(f"• {out_base} → ERROR: {err} (originals kept).", ERROR)
                continue
            produced.append(out_zip if self.rezip_output else out_chd)
            saved += share - final_size
            pct = (1.0 - (final_size / share)) * 100 if share > 0 else 0.0
            self.log(f"• [CHD] {out_base} → {label} (Shrunk by {max(0.0, pct):.1f}%)", SUCCESS)

        if all_ok and self.delete_originals:
            # Never delete a file we just wrote (a re-zipped output can replace its own archive)
            if not any(same_path(p, path) for p in produced):
                self.delete_original(t_type, path)
            if t_type != "archive":
                self.maybe_purge_parents(host_folder)

        self.cleanup_tmp(t_type, host_folder, base_name)
        return saved
