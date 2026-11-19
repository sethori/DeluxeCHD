"""The main DeluxeCHD window: top bar, sidebar (source, scan mode, options), hero and log."""
import html
import os
import time

from PySide6.QtCore import QSettings, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QPushButton, QTextBrowser, QToolButton, QVBoxLayout, QWidget,
)

from deluxechd import APP_NAME, __version__, converter, tools, updater
from deluxechd.ui import icons
from deluxechd.ui.update_dialog import UpdateCheckThread, UpdateDialog
from deluxechd.ui.widgets import (
    FolderButton, NavRow, StatusDot, ToggleRow, scaled_font, section_header,
)

MODES = [
    ("recursive", "scan", "Automatic scan", "Every subfolder, all formats"),
    ("folders", "folders", "Per-game folders", "One folder per game"),
    ("all_in_one", "file", "All in one folder", "Loose .bin / .cue files"),
    ("archives", "archive", "Individual archives", ".zip, .7z, .rar"),
]


def format_time(seconds):
    if seconds < 0:
        return "--:--"
    s = int(seconds)
    if s >= 3600:
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"
    return f"{s // 60:02d}:{s % 60:02d}"


def human_bytes(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024


class ConvertWorker(QThread):
    file_started = Signal(str, int, int)
    progress_updated = Signal(int)
    log = Signal(str, str)
    all_done = Signal(float)

    def __init__(self, folder, mode, delete_originals, rezip_output):
        super().__init__()
        self.engine = converter.Converter(
            folder, mode, delete_originals, rezip_output,
            on_file_started=self.file_started.emit,
            on_progress=self.progress_updated.emit,
            on_log=self.log.emit,
        )

    def run(self):
        saved = 0
        try:
            saved = self.engine.run()
        except Exception as e:
            self.log.emit(f"❌ Unexpected error: {e}", converter.ERROR)
        self.all_done.emit(float(saved))


class MainWindow(QMainWindow):
    def __init__(self, theme, check_updates=True):
        super().__init__()
        self.theme = theme
        self.tokens = theme.tokens
        self.settings = QSettings("sethori", APP_NAME)
        self.selected_folder = ""
        self.worker = None
        self.start_time = 0.0
        self.pending_release = None
        self.check_thread = None
        self.state = "empty"

        self.setWindowTitle(APP_NAME)
        self.setAcceptDrops(True)
        self.resize(1040, 720)
        self.setMinimumSize(820, 600)
        icon_path = tools.asset_path("com.sethori.DeluxeCHD.svg")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.ui_timer = QTimer(self, interval=1000)
        self.ui_timer.timeout.connect(self.update_live_clocks)

        self._build()
        self.refresh_tools()
        self.set_state("empty")
        theme.changed.connect(self.apply_tokens)
        self.apply_tokens(self.tokens)

        if check_updates and self.settings.value("check_updates", True, type=bool):
            QTimer.singleShot(1500, lambda: self.check_for_updates(manual=False))

    # ------------------------------------------------------------------ layout

    def _build(self):
        root = QWidget(objectName="Root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_top_bar())
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_main(), 1)
        outer.addLayout(body, 1)

    def _build_top_bar(self):
        bar = QFrame(objectName="TopBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(10)

        brand = QFrame(objectName="BrandTab")
        brand.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(10, 5, 14, 5)
        bl.setSpacing(8)
        logo = QLabel()
        icon_path = tools.asset_path("com.sethori.DeluxeCHD.svg")
        if os.path.exists(icon_path):
            logo.setPixmap(QIcon(icon_path).pixmap(20, 20))
        name = QLabel(APP_NAME, objectName="BrandName")
        name.setFont(scaled_font(name, 1.12, bold=True))
        bl.addWidget(logo)
        bl.addWidget(name)
        lay.addWidget(brand)

        self.top_status_dot = StatusDot()
        lay.addWidget(self.top_status_dot)
        self.top_status = QLabel("Ready", objectName="TopTab")
        lay.addWidget(self.top_status)
        lay.addStretch()

        self.update_chip = QPushButton(objectName="UpdateChip")
        self.update_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_chip.clicked.connect(self.show_update_dialog)
        self.update_chip.hide()
        lay.addWidget(self.update_chip)
        return bar

    def _build_sidebar(self):
        side = QFrame(objectName="Sidebar")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(310)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(12, 16, 12, 0)
        lay.setSpacing(6)

        lay.addWidget(self._padded(section_header("Source folder")))
        self.folder_btn = FolderButton()
        self.folder_btn.clicked.connect(self.browse_folder)
        lay.addWidget(self.folder_btn)
        lay.addSpacing(12)

        lay.addWidget(self._padded(section_header("How are your files stored?")))
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_rows = []
        for value, icon_name, title, sub in MODES:
            row = NavRow(icon_name, title, sub, value)
            self.mode_group.addButton(row)
            self.mode_rows.append(row)
            lay.addWidget(row)
        self.mode_rows[0].setChecked(True)
        lay.addSpacing(12)

        lay.addWidget(self._padded(section_header("Options")))
        self.opt_open = ToggleRow("Open folder when finished")
        self.opt_rezip = ToggleRow("Re-zip the new CHD", "Wrap each CHD in a .zip")
        self.opt_delete = ToggleRow("Delete originals", "Only after the CHD verifies", danger=True)
        for row in (self.opt_open, self.opt_rezip, self.opt_delete):
            lay.addWidget(row)
        lay.addStretch(1)

        tools_box = QVBoxLayout()
        tools_box.setContentsMargins(10, 4, 10, 10)
        tools_box.setSpacing(6)
        tools_box.addWidget(section_header("Tools"))
        self.tool_rows = {}
        for label in ("chdman", "7-Zip"):
            row = QHBoxLayout()
            dot = StatusDot()
            name = QLabel(label)
            state = QLabel(objectName="Muted")
            state.setFont(scaled_font(state, 0.9))
            row.addWidget(dot)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(state)
            tools_box.addLayout(row)
            self.tool_rows[label] = (dot, state)
        lay.addLayout(tools_box)

        footer = QFrame(objectName="SidebarFooter")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(10, 8, 2, 8)
        self.version_lbl = QLabel(f"Version {__version__}", objectName="Version")
        fl.addWidget(self.version_lbl)
        fl.addStretch()
        self.settings_btn = QToolButton(objectName="IconButton")
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_btn.setMenu(self._build_settings_menu())
        fl.addWidget(self.settings_btn)
        lay.addWidget(footer)
        return side

    def _build_settings_menu(self):
        menu = QMenu(self)
        menu.addAction("Check for updates now", lambda: self.check_for_updates(manual=True))
        self.act_auto_update = QAction("Check for updates on startup", self, checkable=True)
        self.act_auto_update.setChecked(self.settings.value("check_updates", True, type=bool))
        self.act_auto_update.toggled.connect(lambda on: self.settings.setValue("check_updates", on))
        menu.addAction(self.act_auto_update)
        menu.addSeparator()
        menu.addAction("Rescan for tools", self.refresh_tools)
        menu.addAction("Open releases page", lambda: QDesktopServices.openUrl(QUrl(updater.RELEASES_PAGE)))
        menu.addAction(f"About {APP_NAME}", self.show_about)
        return menu

    @staticmethod
    def _padded(widget, left=10):
        wrap = QWidget()
        l = QHBoxLayout(wrap)
        l.setContentsMargins(left, 0, 0, 4)
        l.addWidget(widget)
        return wrap

    def _build_main(self):
        main = QWidget(objectName="MainArea")
        main.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(main)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Hero
        hero = QWidget()
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(40, 30, 40, 30)
        hl.setSpacing(10)
        hl.addStretch(1)
        self.hero_glyph = QLabel(alignment=Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self.hero_glyph)
        hl.addSpacing(6)
        self.hero_title = QLabel(objectName="HeroTitle", alignment=Qt.AlignmentFlag.AlignCenter)
        self.hero_title.setFont(scaled_font(self.hero_title, 1.7, bold=True))
        self.hero_title.setWordWrap(True)
        hl.addWidget(self.hero_title)
        self.hero_sub = QLabel(objectName="HeroSub", alignment=Qt.AlignmentFlag.AlignCenter)
        self.hero_sub.setWordWrap(True)
        self.hero_sub.setTextFormat(Qt.TextFormat.PlainText)
        self.hero_sub.setFixedWidth(520)
        hl.addWidget(self.hero_sub, 0, Qt.AlignmentFlag.AlignHCenter)
        hl.addSpacing(8)

        self.progress_bar = QProgressBar(textVisible=False)
        self.progress_bar.setFixedWidth(440)
        hl.addWidget(self.progress_bar, 0, Qt.AlignmentFlag.AlignHCenter)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        chips.addStretch()
        self.chip_elapsed = QLabel("Elapsed 00:00", objectName="StatChip")
        self.chip_eta = QLabel("Remaining --:--", objectName="StatChip")
        self.chip_count = QLabel("", objectName="StatChip")
        for c in (self.chip_count, self.chip_elapsed, self.chip_eta):
            chips.addWidget(c)
        chips.addStretch()
        self.chips_box = QWidget()
        self.chips_box.setLayout(chips)
        hl.addWidget(self.chips_box)
        hl.addSpacing(8)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch()
        self.btn_start = QPushButton("Start DeluxeCHD", objectName="PrimaryButton")
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_conversion)
        self.btn_open = QPushButton("  Open folder", objectName="SecondaryButton")
        self.btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open.clicked.connect(self.open_selected_folder)
        btns.addWidget(self.btn_start)
        btns.addWidget(self.btn_open)
        btns.addStretch()
        hl.addLayout(btns)
        hl.addStretch(1)
        lay.addWidget(hero, 3)

        # Log panel
        panel = QFrame(objectName="LogPanel")
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        header = QFrame(objectName="LogHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hdr = QHBoxLayout(header)
        hdr.setContentsMargins(20, 8, 12, 8)
        title = QLabel("Log", objectName="LogTitle")
        title.setFont(scaled_font(title, 1.1, bold=True))
        sub = QLabel("summary report", objectName="Muted")
        hdr.addWidget(title)
        hdr.addWidget(sub)
        hdr.addStretch()
        self.btn_copy = QToolButton(objectName="IconButton", toolTip="Copy log")
        self.btn_copy.clicked.connect(self.copy_log)
        self.btn_clear = QToolButton(objectName="IconButton", toolTip="Clear log")
        self.btn_clear.clicked.connect(self.clear_log)
        hdr.addWidget(self.btn_copy)
        hdr.addWidget(self.btn_clear)
        pl.addWidget(header)
        self.log_view = QTextBrowser(objectName="Log")
        self.log_view.setOpenLinks(False)
        self.log_view.setPlaceholderText("Operation summary report will appear here…")
        self.log_view.document().setDocumentMargin(16)
        pl.addWidget(self.log_view, 1)
        lay.addWidget(panel, 2)
        return main

    # ------------------------------------------------------------------ theming

    def apply_tokens(self, tokens):
        self.tokens = tokens
        t = tokens
        for row in self.mode_rows:
            row.set_tokens(t)
        for row in (self.opt_open, self.opt_rezip, self.opt_delete):
            row.set_tokens(t)
        self.folder_btn.set_tokens(t)
        self.settings_btn.setIcon(icons.icon("settings", t.muted, 18))
        self.btn_copy.setIcon(icons.icon("copy", t.muted, 16))
        self.btn_clear.setIcon(icons.icon("trash", t.muted, 16))
        self.btn_start.setIcon(icons.icon("play", t.on_accent, 16))
        self.btn_open.setIcon(icons.icon("external", t.text, 16))
        self.update_chip.setIcon(icons.icon("download", t.accent, 14))
        self.refresh_tools()
        self.set_state(self.state)
        self.rerender_log()

    # ------------------------------------------------------------------ state

    def set_state(self, state, **info):
        """empty → ready → running → done."""
        self.state = state
        t = self.tokens
        running = state == "running"
        glyph = {"empty": "folder", "ready": "disc", "running": "disc", "done": "check"}[state]
        glyph_color = t.positive if state == "done" else t.accent
        self.hero_glyph.setPixmap(icons.pixmap(glyph, glyph_color, 72, stroke_width=1.6))

        if state == "empty":
            self.hero_title.setText("Pick a folder to get started")
            self.hero_sub.setText("Choose the folder that holds your disc images (.cue/.bin, per-game "
                                  "folders, or .zip/.7z/.rar archives). You can also drop a folder here.")
        elif state == "ready":
            name = os.path.basename(self.selected_folder.rstrip("/\\")) or self.selected_folder
            self.hero_title.setText(f"Convert {name}")
            self.hero_sub.setText("Pick how your files are stored in the sidebar, set your options, "
                                  "then start. Every new CHD is verified before anything is deleted.")
        elif state == "running":
            if "name" in info:
                self.hero_title.setText(info["name"])
                self.chip_count.setText(f"{info['cur']} of {info['tot']}")
            else:
                self.hero_title.setText("Scanning…")
                self.chip_count.setText("")
            self.hero_sub.setText("Converting with chdman. This can take a while for large libraries.")
        elif state == "done":
            self.hero_title.setText("All done")
            self.hero_sub.setText(info.get("summary", self.hero_sub.text()))

        self.hero_sub.setMinimumHeight(self.hero_sub.heightForWidth(self.hero_sub.width()))
        self.progress_bar.setVisible(state in ("running", "done"))
        self.chips_box.setVisible(state in ("running", "done"))
        self.chip_count.setVisible(bool(self.chip_count.text()) and running)
        self.btn_start.setVisible(state in ("ready", "done", "empty"))
        self.btn_start.setText("  Start again" if state == "done" else "  Start DeluxeCHD")
        has_chdman = bool(tools.chdman())
        self.btn_start.setEnabled(bool(self.selected_folder) and not running and has_chdman)
        self.btn_start.setToolTip("" if has_chdman else "chdman wasn't found. Install mame-tools.")
        self.btn_open.setVisible(state == "done")

        self.folder_btn.setEnabled(not running)
        for row in self.mode_rows:
            row.setEnabled(not running)
        self.opt_rezip.setEnabled(not running)
        self.opt_delete.setEnabled(not running)

        dot_color = {"running": t.accent, "done": t.positive}.get(state, t.muted)
        self.top_status_dot.set_color(dot_color)
        self.top_status.setText({"empty": "Ready", "ready": "Ready", "running": "Converting",
                                 "done": "Finished"}[state])

    def refresh_tools(self):
        if not self.tokens:
            return
        status = tools.tool_status()
        for label, (dot, state) in self.tool_rows.items():
            path = status.get(label)
            dot.set_color(self.tokens.positive if path else (self.tokens.negative if label == "chdman" else self.tokens.neutral))
            if path:
                state.setText("Bundled" if os.path.dirname(path) == tools.bundled_tools_dir() else "Found")
                state.setToolTip(path)
            else:
                state.setText("Missing" if label == "chdman" else "Missing (.7z/.rar)")
                state.setToolTip("Install mame-tools" if label == "chdman" else "Install p7zip for .7z and .rar archives")
        if hasattr(self, "btn_start") and self.state != "running":
            self.btn_start.setEnabled(bool(self.selected_folder) and bool(status["chdman"]))

    # ------------------------------------------------------------------ folder

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", self.selected_folder or os.path.expanduser("~"))
        if folder:
            self.set_folder(folder)

    def set_folder(self, folder):
        self.selected_folder = os.path.abspath(folder)
        self.folder_btn.set_folder(self.selected_folder)
        self.set_state("ready")

    def dragEnterEvent(self, e):
        if self.state != "running" and e.mimeData().hasUrls():
            urls = e.mimeData().urls()
            if urls and urls[0].isLocalFile() and os.path.isdir(urls[0].toLocalFile()):
                e.acceptProposedAction()

    def dropEvent(self, e):
        self.set_folder(e.mimeData().urls()[0].toLocalFile())

    def open_selected_folder(self):
        if self.selected_folder and os.path.exists(self.selected_folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.selected_folder))

    # ------------------------------------------------------------------ log

    def clear_log(self):
        self.log_entries = []
        self.log_view.clear()

    def copy_log(self):
        QGuiApplication.clipboard().setText(self.log_view.toPlainText())

    def append_log(self, text, kind=converter.INFO):
        if not hasattr(self, "log_entries"):
            self.log_entries = []
        self.log_entries.append((text, kind))
        self.log_view.append(self._log_html(text, kind))
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _log_html(self, text, kind):
        t = self.tokens
        color = {
            converter.SUCCESS: t.positive, converter.ERROR: t.negative, converter.SKIP: t.muted,
            converter.DETAIL: t.muted, "title": t.title, "total": t.accent,
        }.get(kind, t.text).name()
        weight = "700" if kind in ("title", "total") else "400"
        body = html.escape(text).replace(" ", "&nbsp;&nbsp;") if text.startswith("  ") else html.escape(text)
        return f'<span style="color:{color}; font-weight:{weight}; white-space:pre-wrap">{body}</span>'

    def rerender_log(self):
        entries = getattr(self, "log_entries", [])
        self.log_view.clear()
        for text, kind in entries:
            self.log_view.append(self._log_html(text, kind))

    # ------------------------------------------------------------------ run

    def is_busy(self):
        return self.worker is not None and self.worker.isRunning()

    def start_conversion(self):
        if not self.selected_folder or self.is_busy():
            return
        if not os.path.isdir(self.selected_folder):
            QMessageBox.warning(self, APP_NAME, "The selected folder no longer exists.")
            return
        self.progress_bar.setValue(0)
        self.chip_elapsed.setText("Elapsed 00:00")
        self.chip_eta.setText("Remaining: calculating…")
        self.chip_count.setText("")
        self.clear_log()
        self.append_log("=== DELUXECHD SUMMARY REPORT ===", "title")
        self.append_log("Processed Items:", "title")

        mode = self.mode_group.checkedButton().value
        self.worker = ConvertWorker(self.selected_folder, mode, self.opt_delete.isChecked(), self.opt_rezip.isChecked())
        self.worker.file_started.connect(lambda name, cur, tot: self.set_state("running", name=name, cur=cur, tot=tot))
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.log.connect(self.append_log)
        self.worker.all_done.connect(self.on_all_done)
        self.set_state("running")
        self.start_time = time.time()
        self.ui_timer.start()
        self.worker.start()

    def update_live_clocks(self):
        if not self.is_busy():
            return
        elapsed = time.time() - self.start_time
        self.chip_elapsed.setText(f"Elapsed {format_time(elapsed)}")
        engine = self.worker.engine
        processed = engine.bytes_processed_so_far
        total = engine.total_bytes_to_process
        if processed > 0 and elapsed > 0:
            remaining = total - processed
            self.chip_eta.setText(f"Remaining {format_time(remaining / (processed / elapsed)) if remaining > 0 else '00:00'}")

    def on_all_done(self, total_bytes_saved):
        self.ui_timer.stop()
        self.worker.wait()
        self.progress_bar.setValue(100)
        self.chip_eta.setText("Remaining 00:00")
        self.chip_elapsed.setText(f"Elapsed {format_time(time.time() - self.start_time)}")
        self.append_log("")
        self.append_log("=================================", "total")
        self.append_log(f"TOTAL SPACE SAVED: {total_bytes_saved / (1024 * 1024):.2f} MB", "total")
        self.append_log("=================================", "total")
        self.set_state("done", summary=f"Saved {human_bytes(max(0.0, total_bytes_saved))}. "
                                       "The log below lists every item.")
        if self.opt_open.isChecked():
            self.open_selected_folder()
        QApplication.alert(self)  # flash the taskbar entry if the window is in the background

    def closeEvent(self, e):
        if self.is_busy():
            answer = QMessageBox.question(
                self, APP_NAME,
                "A conversion is still running. Quit anyway?\n\nThe current item may leave a partial "
                ".chd or a tmp_ folder behind. Its originals are not deleted.",
            )
            if answer != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            os._exit(1)
        super().closeEvent(e)

    # ------------------------------------------------------------------ updates

    def check_for_updates(self, manual=False):
        if self.check_thread and self.check_thread.isRunning():
            return
        self.check_thread = UpdateCheckThread(self)
        self.check_thread.found.connect(self.on_update_found)
        if manual:
            self.check_thread.found.connect(lambda _r: self.show_update_dialog())
            self.check_thread.up_to_date.connect(
                lambda r: QMessageBox.information(self, APP_NAME, f"You're on the latest version ({__version__})."))
            self.check_thread.failed.connect(
                lambda msg: QMessageBox.warning(self, APP_NAME, f"Couldn't check for updates.\n\n{msg}"))
        self.check_thread.start()

    def on_update_found(self, rel):
        self.pending_release = rel
        self.update_chip.setText(f"Update {rel.version}")
        self.update_chip.show()

    def show_update_dialog(self):
        if self.pending_release:
            UpdateDialog(self.pending_release, self.tokens, self.is_busy, self).exec()

    def show_about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME} {__version__}</b><br>Batch-convert CD images to CHD with chdman.<br><br>"
            f'<a href="https://github.com/sethori/DeluxeCHD">github.com/sethori/DeluxeCHD</a>',
        )
