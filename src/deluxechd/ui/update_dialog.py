"""Update check thread and the 'update available' dialog."""
from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTextBrowser, QVBoxLayout,
)

from deluxechd import __version__, updater
from deluxechd.ui import icons
from deluxechd.ui.widgets import scaled_font


class UpdateCheckThread(QThread):
    found = Signal(object)    # Release (newer than this version)
    up_to_date = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            rel = updater.fetch_latest(updater.install_method())
        except Exception as e:
            self.failed.emit(str(e))
            return
        if rel.version and updater.is_newer(rel.version):
            self.found.emit(rel)
        else:
            self.up_to_date.emit(rel)


class DownloadThread(QThread):
    progress = Signal(int, int)
    ok = Signal(str)
    failed = Signal(str)

    def __init__(self, rel, method, parent=None):
        super().__init__(parent)
        self.rel = rel
        self.method = method
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            dest = updater.staging_path(self.method, self.rel)
            updater.download(self.rel, dest, lambda d, t: self.progress.emit(d, t), lambda: self._cancel)
            self.ok.emit(dest)
        except Exception as e:
            self.failed.emit(str(e))


class UpdateDialog(QDialog):
    def __init__(self, rel, tokens, is_busy, parent=None):
        super().__init__(parent)
        self.rel = rel
        self.is_busy = is_busy
        self.method = updater.install_method()
        self.thread = None
        self.setWindowTitle("Update available")
        self.setMinimumSize(520, 440)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)

        head = QHBoxLayout()
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap("sparkle", tokens.accent, 30))
        head.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        titles = QVBoxLayout()
        title = QLabel(f"DeluxeCHD {rel.version} is available")
        title.setObjectName("HeroTitle")
        title.setFont(scaled_font(title, 1.35, bold=True))
        sub = QLabel(f"You have version {__version__}.")
        sub.setObjectName("Muted")
        titles.addWidget(title)
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        lay.addLayout(head)

        notes = QTextBrowser()
        notes.setObjectName("Notes")
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(rel.notes or "_No release notes._")
        lay.addWidget(notes, 1)

        self.status = QLabel("")
        self.status.setObjectName("Muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        lay.addWidget(self.bar)

        btns = QHBoxLayout()
        self.btn_page = QPushButton("View on GitHub")
        self.btn_page.setObjectName("SecondaryButton")
        self.btn_page.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(rel.page_url)))
        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("SecondaryButton")
        self.btn_later.clicked.connect(self.reject)
        self.btn_install = QPushButton("Download && install")
        self.btn_install.setObjectName("PrimaryButton")
        self.btn_install.setIcon(icons.icon("download", tokens.on_accent))
        self.btn_install.clicked.connect(self.start_install)
        btns.addWidget(self.btn_page)
        btns.addStretch()
        btns.addWidget(self.btn_later)
        btns.addWidget(self.btn_install)
        lay.addLayout(btns)

        if not self.method or not rel.asset_url:
            self.btn_install.setText("Open download page")
            self.btn_install.setIcon(icons.icon("external", tokens.on_accent))
            self.btn_page.hide()
            if not self.method:
                self.status.setText("This copy can't update itself (it isn't the AppImage or the "
                                    "Windows installer build). Download the new version from GitHub.")
        elif is_busy():
            self.btn_install.setEnabled(False)
            self.status.setText("Finish the current conversion before installing.")

    def start_install(self):
        if not self.method or not self.rel.asset_url:
            QDesktopServices.openUrl(QUrl(self.rel.page_url))
            self.accept()
            return
        if self.is_busy():
            self.status.setText("Finish the current conversion before installing.")
            return
        self.btn_install.setEnabled(False)
        self.btn_later.setText("Cancel")
        self.bar.show()
        self.bar.setRange(0, 0)
        self.status.setText(f"Downloading {self.rel.asset_name}…")
        self.thread = DownloadThread(self.rel, self.method, self)
        self.thread.progress.connect(self._on_progress)
        self.thread.ok.connect(self._on_downloaded)
        self.thread.failed.connect(self._on_failed)
        self.thread.start()

    def _on_progress(self, done, total):
        if total > 0:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(done * 1000 / total))
            self.status.setText(f"Downloading {self.rel.asset_name}… {done / 1048576:.1f} of {total / 1048576:.1f} MB")

    def _on_downloaded(self, path):
        self.status.setText("Verified. Installing and restarting…")
        try:
            updater.install_and_relaunch(self.method, path)
        except Exception as e:
            self._on_failed(str(e))
            return
        QApplication.instance().quit()

    def _on_failed(self, msg):
        self.bar.hide()
        self.btn_later.setText("Close")
        self.btn_install.setEnabled(True)
        self.btn_install.setText("Open download page")
        self.method = None
        self.status.setText(f"Update failed: {msg}")

    def reject(self):
        if self.thread and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(3000)
        super().reject()
