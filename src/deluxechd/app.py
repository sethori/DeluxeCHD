"""Application entry point."""
import os
import sys

from deluxechd import APP_ID, APP_NAME, __version__, tools


def _prepare_environment():
    if tools.FROZEN and not tools.IS_WINDOWS:
        # The bundled libraries are already loaded; restore the user's LD_LIBRARY_PATH so anything
        # we launch (xdg-open → file manager, chdman, the updated AppImage) uses system libraries.
        clean = tools.child_env()
        os.environ.clear()
        os.environ.update(clean)
    if tools.IS_WINDOWS:
        try:  # own taskbar group + icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    smoke_test = "--smoke-test" in argv  # CI: start, render, quit
    if smoke_test:
        argv.remove("--smoke-test")
    _prepare_environment()
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from deluxechd.theme import ThemeManager
    from deluxechd.ui.main_window import MainWindow

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("sethori")
    app.setDesktopFileName(APP_ID)  # lets Wayland/KDE match the .desktop entry and icon
    app.setStyle("Fusion")  # consistent base for the themed stylesheet on every platform
    icon_path = tools.asset_path("com.sethori.DeluxeCHD.svg")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    theme = ThemeManager(app)
    theme.apply()
    window = MainWindow(theme, check_updates=not smoke_test)
    window.show()
    if smoke_test:
        from PySide6.QtCore import QTimer
        ok = os.path.exists(icon_path) and window.grab().width() > 0
        QTimer.singleShot(300, lambda: app.exit(0 if ok else 1))
    return app.exec()
