#!/usr/bin/env python3
import os
import re
import sys
import shutil
import subprocess
import time
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QFileDialog, QLabel, QProgressBar, QStyleFactory,
    QCheckBox, QTextEdit, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QIcon

def get_asset_path(relative_path):
    """Gets absolute path to resource, safely handling PyInstaller temporary runtime trees."""
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)

class DeluxeCHDWorker(QThread):
    file_started = pyqtSignal(str, int, int)
    progress_updated = pyqtSignal(int)
    item_verified = pyqtSignal(str)
    all_done = pyqtSignal(int)

    def __init__(self, folder_path, mode, delete_originals, open_finished, rezip_output):
        super().__init__()
        self.folder_path = folder_path
        self.mode = mode  # "folders", "all_in_one", "archives", "recursive"
        self.delete_originals = delete_originals
        self.open_finished = open_finished
        self.rezip_output = rezip_output
        
        self.total_bytes_to_process = 0
        self.bytes_processed_so_far = 0
        self.current_item_size = 0

    def cue_bin_files(self, cue_path):
        """Returns the files a .cue sheet references (existing ones only), so we never touch unrelated files."""
        parent = os.path.dirname(cue_path)
        found = []
        try:
            with open(cue_path, 'r', encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    m = re.match(r'\s*FILE\s+(?:"([^"]+)"|(\S+))', line, re.IGNORECASE)
                    if m:
                        candidate = os.path.join(parent, os.path.basename((m.group(1) or m.group(2)).replace('\\', '/')))
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
        """Calculates precise item or file collection sizes for progress tracking."""
        if t_type == 'archive':
            return os.path.getsize(path)
        if t_type == 'folder':
            return sum(os.path.getsize(os.path.join(r, f)) for r, _, files in os.walk(path) for f in files if os.path.exists(os.path.join(r, f)))
        if t_type == 'loose_cue':
            size = os.path.getsize(path)
            size += sum(os.path.getsize(f) for f in self.cue_bin_files(path))
            return size
        return 0

    def extract_archive(self, archive_path, destination_dir):
        """Extracts .zip, .7z, or .rar safely using available system utilities."""
        ext = os.path.splitext(archive_path)[1].lower()
        if ext == '.zip':
            subprocess.run(["unzip", "-q", archive_path, "-d", destination_dir], check=True)
        elif ext in ('.7z', '.rar'):
            if shutil.which("7z"):
                subprocess.run(["7z", "x", "-y", f"-o{destination_dir}", archive_path], stdout=subprocess.DEVNULL, check=True)
            elif ext == '.rar' and shutil.which("unrar"):
                subprocess.run(["unrar", "x", "-y", archive_path, destination_dir], stdout=subprocess.DEVNULL, check=True)
            else:
                raise RuntimeError(f"Missing extraction tool (7z/unrar) for archive format: {ext}")

    def should_clean_directory(self, path):
        """Checks if a directory is empty or only contains disposable metadata files (e.g., .txt, .nfo)."""
        if not os.path.exists(path) or not os.path.isdir(path):
            return False
        disposable_extensions = ('.txt', '.nfo', '.url', '.ini', '.db')
        for root, dirs, files in os.walk(path):
            for f in files:
                if not f.lower().endswith(disposable_extensions):
                    return False
        return True

    def purge_empty_parent_tree(self, target_folder):
        """Walks up the directory tree and deletes parent folders that are now empty or text-only."""
        current = os.path.abspath(target_folder)
        stop_at = os.path.abspath(self.folder_path)
        
        # Keep climbing and cleaning until we hit the root user-selected starting folder
        while current != stop_at and current.startswith(stop_at):
            if self.should_clean_directory(current):
                try:
                    shutil.rmtree(current)
                except Exception:
                    break
            else:
                break
            # Move up to the next parent directory
            current = os.path.dirname(current)

    def convert_cue(self, cue_path, out_base, out_chd, out_zip, replace_path):
        """Converts one .cue to CHD (optionally zipped). Returns (final_size, label, error); final_size is None on failure."""
        work = os.path.dirname(cue_path)
        tmp_chd = os.path.join(work, f"{out_base}.chd")
        res = subprocess.run(["chdman", "createcd", "-i", cue_path, "-o", tmp_chd], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0 or not os.path.exists(tmp_chd):
            lines = (res.stderr or "").strip().splitlines()
            if os.path.exists(tmp_chd):
                os.remove(tmp_chd)
            return None, "", "chdman engine failed" + (f" ({lines[-1]})" if lines else "")
        # Never report success (or allow deletion of originals) unless the new CHD verifies
        if subprocess.run(["chdman", "verify", "-i", tmp_chd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            os.remove(tmp_chd)
            return None, "", "CHD verification failed"
        if not self.rezip_output:
            shutil.move(tmp_chd, out_chd)
            return os.path.getsize(out_chd), "Raw CHD File", ""
        tmp_zip = os.path.join(work, f"{out_base}.chdtmp.zip")
        zres = subprocess.run(["zip", "-q", "-j", tmp_zip, tmp_chd])
        os.remove(tmp_chd)
        if zres.returncode != 0 or not os.path.exists(tmp_zip):
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
            return None, "", "zip step failed"
        # The new zip may share a name with the original archive it replaces
        if self.delete_originals and replace_path and os.path.abspath(replace_path) == os.path.abspath(out_zip):
            os.remove(replace_path)
        shutil.move(tmp_zip, out_zip)
        return os.path.getsize(out_zip), "Compressed Zip", ""

    def cleanup_tmp(self, t_type, host_folder, base_name):
        tmp_root = os.path.join(host_folder, f"tmp_{base_name}")
        if t_type == 'archive' and os.path.exists(tmp_root):
            shutil.rmtree(tmp_root)

    def run(self):
        archive_extensions = ('.zip', '.7z', '.rar')
        targets = []

        try:
            if self.mode == "recursive":
                for root, dirs, files in os.walk(self.folder_path):
                    if any(part.startswith('tmp_') for part in root.split(os.sep)):
                        continue
                    for f in files:
                        full_path = os.path.join(root, f)
                        if f.lower().endswith('.cue'):
                            targets.append(('loose_cue', full_path))
                        elif f.lower().endswith(archive_extensions):
                            targets.append(('archive', full_path))
            else:
                items = os.listdir(self.folder_path)
                if self.mode == "folders":
                    for item in items:
                        full_path = os.path.join(self.folder_path, item)
                        if os.path.isdir(full_path) and not item.startswith('tmp_'):
                            cue_names = sorted(f for f in os.listdir(full_path) if f.lower().endswith('.cue'))
                            if len(cue_names) == 1:
                                targets.append(('folder', full_path))
                            else:
                                # Multi-disc folder: each .cue is converted to its own CHD
                                for cue_name in cue_names:
                                    targets.append(('loose_cue', os.path.join(full_path, cue_name)))
                elif self.mode == "all_in_one":
                    for item in items:
                        full_path = os.path.join(self.folder_path, item)
                        if item.lower().endswith('.cue'):
                            targets.append(('loose_cue', full_path))
                elif self.mode == "archives":
                    for item in items:
                        full_path = os.path.join(self.folder_path, item)
                        if item.lower().endswith(archive_extensions):
                            targets.append(('archive', full_path))
        except Exception as e:
            self.item_verified.emit(f"❌ Error reading directories: {e}")
            self.all_done.emit(0)
            return

        total_items = len(targets)
        if total_items == 0:
            self.item_verified.emit("No eligible games found matching search target criteria.")
            self.all_done.emit(0)
            return

        self.total_bytes_to_process = 0
        item_sizes = {}
        for t_type, path in targets:
            size = self.get_associated_size(path, t_type)
            item_sizes[path] = size
            self.total_bytes_to_process += size

        total_bytes_saved = 0
        self.bytes_processed_so_far = 0

        for index, (t_type, path) in enumerate(targets):
            display_name = os.path.basename(path)
            self.current_item_size = item_sizes[path]
            self.file_started.emit(display_name, index + 1, total_items)
            
            base_name = os.path.splitext(display_name)[0]
            host_folder = os.path.dirname(path)
            
            # Setup expected final path targets in root matching configuration states
            expected_chd = os.path.join(self.folder_path, f"{base_name}.chd")
            expected_zip_output = os.path.join(self.folder_path, f"{base_name}.zip" if self.delete_originals else f"{base_name}_CHD.zip")
            
            # Check for duplication upfront
            if (not self.rezip_output and os.path.exists(expected_chd)) or (self.rezip_output and os.path.exists(expected_zip_output)):
                self.item_verified.emit(f"• ⏭️ {base_name} → Already Exists (Skipped conversion)")
                
                if self.delete_originals:
                    try:
                        if t_type == 'archive' and os.path.exists(path):
                            os.remove(path)
                            self.item_verified.emit(f"  └─ Automatically deleted original archive: {display_name}")
                        elif t_type == 'folder' and os.path.exists(path):
                            shutil.rmtree(path)
                            self.item_verified.emit(f"  └─ Automatically deleted original game subfolder: {display_name}")
                        elif t_type == 'loose_cue':
                            self.delete_loose_game(path)
                            self.item_verified.emit(f"  └─ Automatically deleted original loose bin/cue: {base_name}")
                            
                            # Clean up deep path parent structural chain upward
                            if (self.mode == "recursive" or self.mode == "folders") and host_folder != self.folder_path:
                                self.purge_empty_parent_tree(host_folder)
                    except Exception as clean_error:
                        self.item_verified.emit(f"  └─ ⚠️ Cleanup error tracking target: {clean_error}")
                
                self.bytes_processed_so_far += self.current_item_size
                self.progress_updated.emit(int(((index + 1) / total_items) * 100))
                continue

            tmp_root = os.path.join(host_folder, f"tmp_{base_name}")
            cue_jobs = []  # (cue_path, output_base_name)
            if t_type == 'loose_cue':
                cue_jobs = [(path, base_name)]
            elif t_type == 'folder':
                sub_cues = [f for f in os.listdir(path) if f.lower().endswith('.cue')]
                cue_jobs = [(os.path.join(path, sub_cues[0]), base_name)]
            elif t_type == 'archive':
                os.makedirs(tmp_root, exist_ok=True)
                try:
                    self.extract_archive(path, tmp_root)
                    found = sorted(os.path.join(r, f) for r, _, fs in os.walk(tmp_root) for f in fs if f.lower().endswith('.cue'))
                except Exception as e:
                    self.item_verified.emit(f"• ❌ {display_name} → Unpacking Failed ({e})")
                    self.cleanup_tmp(t_type, host_folder, base_name)
                    self.bytes_processed_so_far += self.current_item_size
                    self.progress_updated.emit(int(((index + 1) / total_items) * 100))
                    continue
                if not found:
                    self.item_verified.emit(f"• ⏭️ {display_name} → Skipped (No .cue sheet inside archive)")
                    self.cleanup_tmp(t_type, host_folder, base_name)
                    self.bytes_processed_so_far += self.current_item_size
                    self.progress_updated.emit(int(((index + 1) / total_items) * 100))
                    continue
                if len(found) == 1:
                    cue_jobs = [(found[0], base_name)]
                else:
                    cue_jobs = [(c, os.path.splitext(os.path.basename(c))[0]) for c in found]

            all_ok = True
            share = self.current_item_size / len(cue_jobs)
            for cue_path, out_base in cue_jobs:
                out_chd = os.path.join(self.folder_path, f"{out_base}.chd")
                out_zip = os.path.join(self.folder_path, f"{out_base}.zip" if self.delete_originals else f"{out_base}_CHD.zip")
                if len(cue_jobs) > 1 and os.path.exists(out_zip if self.rezip_output else out_chd):
                    self.item_verified.emit(f"• ⏭️ {out_base} → Already Exists (Skipped conversion)")
                    continue
                final_size, label, err = self.convert_cue(cue_path, out_base, out_chd, out_zip, path if t_type == 'archive' else None)
                if final_size is None:
                    all_ok = False
                    self.item_verified.emit(f"• {out_base} → ERROR: {err} (originals kept).")
                    continue
                total_bytes_saved += (share - final_size)
                pct = (1.0 - (final_size / share)) * 100 if share > 0 else 0.0
                self.item_verified.emit(f"• [CHD] {out_base} → {label} (Shrunk by {max(0.0, pct):.1f}%)")

            if all_ok and self.delete_originals:
                if t_type == 'archive':
                    if os.path.exists(path):
                        os.remove(path)
                elif t_type == 'folder':
                    shutil.rmtree(path)
                elif t_type == 'loose_cue':
                    self.delete_loose_game(path)
                if t_type != 'archive' and (self.mode == "recursive" or self.mode == "folders") and host_folder != self.folder_path:
                    self.purge_empty_parent_tree(host_folder)

            self.cleanup_tmp(t_type, host_folder, base_name)

            self.bytes_processed_so_far += self.current_item_size
            self.progress_updated.emit(int(((index + 1) / total_items) * 100))

        self.all_done.emit(total_bytes_saved)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.ui_timer = QTimer()
        self.ui_timer.setInterval(1000)
        self.ui_timer.timeout.connect(self.update_live_clocks)
        self.start_time = 0

    def init_ui(self):
        self.setWindowTitle("DeluxeCHD")
        self.resize(550, 560)
        
        icon_path = get_asset_path("com.sethori.DeluxeCHD.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Folder Selector Row
        folder_block = QHBoxLayout()
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setWordWrap(True)
        self.btn_browse = QPushButton("Select Folder")
        self.btn_browse.clicked.connect(self.browse_folder)
        folder_block.addWidget(self.folder_label, stretch=4)
        folder_block.addWidget(self.btn_browse, stretch=1)
        main_layout.addLayout(folder_block)

        # Dropdown Selection Row
        mode_block = QHBoxLayout()
        mode_label = QLabel("How are your files stored?")
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("Automatic / Recursive Scan (All Formats)", "recursive")
        self.combo_mode.addItem("Per Game Folders", "folders")
        self.combo_mode.addItem("All in one folder (Loose .bin/.cue files)", "all_in_one")
        self.combo_mode.addItem("Individual Archives (.zip, .7z, .rar)", "archives")
        mode_block.addWidget(mode_label)
        mode_block.addWidget(self.combo_mode, stretch=1)
        main_layout.addLayout(mode_block)

        # Options Checkboxes
        self.cb_open_folder = QCheckBox("Open folder when finished")
        self.cb_delete_orig = QCheckBox("Delete original files when complete")
        self.cb_rezip_output = QCheckBox("Re-zip the new CHD file upon completion")
        main_layout.addWidget(self.cb_open_folder)
        main_layout.addWidget(self.cb_delete_orig)
        main_layout.addWidget(self.cb_rezip_output)

        # Control Execution Button
        self.btn_start = QPushButton("Start DeluxeCHD")
        self.btn_start.setEnabled(False)
        self.btn_start.setStyleSheet("font-weight: bold; padding: 8px;")
        self.btn_start.clicked.connect(self.start_conversion)
        main_layout.addWidget(self.btn_start)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)

        # Live Realtime Time Clock Display
        time_block = QHBoxLayout()
        self.lbl_elapsed = QLabel("Elapsed: 00:00")
        self.lbl_eta = QLabel("Remaining: --:--")
        self.lbl_elapsed.setStyleSheet("font-size: 11px;")
        self.lbl_eta.setStyleSheet("font-size: 11px; font-weight: bold;")
        time_block.addWidget(self.lbl_elapsed)
        time_block.addStretch()
        time_block.addWidget(self.lbl_eta)
        main_layout.addLayout(time_block)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Operation summary report will appear here upon completion...")
        main_layout.addWidget(self.log_output)
        
        self.statusBar().showMessage("DeluxeCHD engine ready.")
        self.selected_folder = ""

    def format_time(self, seconds):
        if seconds < 0: return "--:--"
        return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.selected_folder = folder
            self.folder_label.setText(f"<b>Selected:</b> {folder}")
            self.btn_start.setEnabled(True)

    def start_conversion(self):
        self.btn_browse.setEnabled(False)
        self.btn_start.setEnabled(False)
        self.combo_mode.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_elapsed.setText("Elapsed: 00:00")
        self.lbl_eta.setText("Remaining ETA: Calculating...")
        self.log_output.clear()
        self.log_output.append("=== DELUXECHD SUMMARY REPORT ===")
        self.log_output.append("Processed Items:")
        
        selected_mode = self.combo_mode.currentData()
        
        self.worker = DeluxeCHDWorker(
            self.selected_folder,
            selected_mode,
            self.cb_delete_orig.isChecked(),
            self.cb_open_folder.isChecked(),
            self.cb_rezip_output.isChecked()
        )
        self.worker.file_started.connect(lambda name, cur, tot: self.status_label.setText(f"Processing: <i>{name}</i> ({cur} of {tot})"))
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.item_verified.connect(self.log_output.append)
        self.worker.all_done.connect(self.on_all_done)
        
        self.start_time = time.time()
        self.ui_timer.start()
        self.worker.start()

    def update_live_clocks(self):
        if not hasattr(self, 'worker') or not self.worker.isRunning():
            return
        elapsed = time.time() - self.start_time
        self.lbl_elapsed.setText(f"Elapsed: {self.format_time(elapsed)}")
        
        processed = self.worker.bytes_processed_so_far
        total = self.worker.total_bytes_to_process
        if processed > 0 and elapsed > 0:
            rem_bytes = total - processed
            if rem_bytes > 0:
                self.lbl_eta.setText(f"Remaining ETA: {self.format_time(rem_bytes / (processed / elapsed))}")
            else:
                self.lbl_eta.setText("Remaining ETA: 00:00")

    def on_all_done(self, total_bytes_saved):
        self.ui_timer.stop()
        self.status_label.setText("<b>Execution Finished!</b>")
        self.progress_bar.setValue(100)
        self.lbl_eta.setText("Remaining ETA: 00:00")
        
        self.log_output.append("\n=================================")
        self.log_output.append(f"TOTAL SPACE SAVED: {total_bytes_saved / (1024 * 1024):.2f} MB")
        self.log_output.append("=================================")
        self.log_output.moveCursor(self.log_output.textCursor().MoveOperation.End)
        
        if self.cb_open_folder.isChecked() and os.path.exists(self.selected_folder):
            subprocess.Popen(['xdg-open', self.selected_folder])

        self.btn_browse.setEnabled(True)
        self.btn_start.setEnabled(True)
        self.combo_mode.setEnabled(True)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Breeze" if "Breeze" in QStyleFactory.keys() else "Fusion")
    app.setDesktopSettingsAware(True)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())