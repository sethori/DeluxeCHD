#!/usr/bin/env python3
import os
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

    def get_associated_size(self, path, t_type):
        """Calculates precise item or file collection sizes for progress tracking."""
        if t_type == 'archive':
            return os.path.getsize(path)
        if t_type == 'folder':
            return sum(os.path.getsize(os.path.join(r, f)) for r, _, files in os.walk(path) for f in files if os.path.exists(os.path.join(r, f)))
        if t_type == 'loose_cue':
            size = os.path.getsize(path)
            base = os.path.splitext(os.path.basename(path))[0]
            parent = os.path.dirname(path)
            for f in os.listdir(parent):
                if f.startswith(base) and f.lower().endswith('.bin'):
                    size += os.path.getsize(os.path.join(parent, f))
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
                            if any(f.lower().endswith('.cue') for f in os.listdir(full_path)):
                                targets.append(('folder', full_path))
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
                            if os.path.exists(path):
                                os.remove(path)
                            for f in os.listdir(host_folder):
                                if f.startswith(base_name) and f.lower().endswith('.bin'):
                                    os.remove(os.path.join(host_folder, f))
                            self.item_verified.emit(f"  └─ Automatically deleted original loose bin/cue: {base_name}")
                            
                            # Clean up deep path parent structural chain upward
                            if (self.mode == "recursive" or self.mode == "folders") and host_folder != self.folder_path:
                                self.purge_empty_parent_tree(host_folder)
                    except Exception as clean_error:
                        self.item_verified.emit(f"  └─ ⚠️ Cleanup error tracking target: {clean_error}")
                
                self.bytes_processed_so_far += self.current_item_size
                self.progress_updated.emit(int(((index + 1) / total_items) * 100))
                continue

            if t_type == 'loose_cue':
                target_cue = path
                working_dir = host_folder
            elif t_type == 'folder':
                working_dir = path
                sub_cues = [f for f in os.listdir(working_dir) if f.lower().endswith('.cue')]
                target_cue = os.path.join(working_dir, sub_cues[0])
            elif t_type == 'archive':
                working_dir = os.path.join(host_folder, f"tmp_{base_name}")
                os.makedirs(working_dir, exist_ok=True)
                try:
                    self.extract_archive(path, working_dir)
                    
                    found_cue = None
                    for ext_root, _, ext_files in os.walk(working_dir):
                        cues = [f for f in ext_files if f.lower().endswith('.cue')]
                        if cues:
                            found_cue = os.path.join(ext_root, cues[0])
                            working_dir = ext_root
                            break
                            
                    if not found_cue:
                        self.item_verified.emit(f"• ⏭️ {display_name} → Skipped (No .cue sheet inside archive)")
                        shutil.rmtree(os.path.join(host_folder, f"tmp_{base_name}"))
                        self.bytes_processed_so_far += self.current_item_size
                        self.progress_updated.emit(int(((index + 1) / total_items) * 100))
                        continue
                    
                    target_cue = found_cue
                except Exception as e:
                    self.item_verified.emit(f"• ❌ {display_name} → Unpacking Failed ({e})")
                    tmp_root = os.path.join(host_folder, f"tmp_{base_name}")
                    if os.path.exists(tmp_root):
                        shutil.rmtree(tmp_root)
                    self.bytes_processed_so_far += self.current_item_size
                    self.progress_updated.emit(int(((index + 1) / total_items) * 100))
                    continue

            tmp_chd = os.path.join(working_dir, f"{base_name}.chd")

            res = subprocess.run(["chdman", "createcd", "-i", target_cue, "-o", tmp_chd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if res.returncode == 0 and os.path.exists(tmp_chd):
                if self.rezip_output:
                    subprocess.run(["zip", "-q", "-j", final_zip, tmp_chd])
                    final_size = os.path.getsize(final_zip)
                    label = "Compressed Zip"
                    if os.path.exists(tmp_chd):
                        os.remove(tmp_chd)
                else:
                    shutil.move(tmp_chd, expected_chd)
                    final_size = os.path.getsize(expected_chd)
                    label = "Raw CHD File"

                total_bytes_saved += (self.current_item_size - final_size)
                pct = (1.0 - (final_size / self.current_item_size)) * 100 if self.current_item_size > 0 else 0.0
                self.item_verified.emit(f"• [CHD] {base_name} → {label} (Shrunk by {max(0.0, pct):.1f}%)")

                if self.delete_originals:
                    if t_type == 'archive':
                        os.remove(path)
                    elif t_type == 'folder':
                        shutil.rmtree(path)
                        # Check up the tree from where the subfolder was located
                        if (self.mode == "recursive" or self.mode == "folders") and host_folder != self.folder_path:
                            self.purge_empty_parent_tree(host_folder)
                    elif t_type == 'loose_cue':
                        if os.path.exists(path):
                            os.remove(path)
                        for f in os.listdir(host_folder):
                            if f.startswith(base_name) and f.lower().endswith('.bin'):
                                os.remove(os.path.join(host_folder, f))
                        
                        # Check up the tree from where the loose files were located
                        if (self.mode == "recursive" or self.mode == "folders") and host_folder != self.folder_path:
                            self.purge_empty_parent_tree(host_folder)
            else:
                self.item_verified.emit(f"• {display_name} → ERROR: chdman engine failed.")

            tmp_root = os.path.join(host_folder, f"tmp_{base_name}")
            if t_type == 'archive' and os.path.exists(tmp_root):
                shutil.rmtree(tmp_root)

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