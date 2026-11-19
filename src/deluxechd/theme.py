"""System-following colours.

* KDE Plasma (including Material You schemes, which are written into kdeglobals): the colour
  scheme is read straight from ~/.config/kdeglobals, because a bundled Qt (AppImage/PyInstaller)
  can't load KDE's own platform theme plugin. The file is watched, so scheme changes apply live.
* Windows / GNOME / others: Qt's platform palette (dark/light mode and the accent colour).

Everything visual is derived from a small set of tokens built from the active palette.
"""
import configparser
import os
import sys
from dataclasses import dataclass

from PySide6.QtCore import QFileSystemWatcher, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette

Role = QPalette.ColorRole
Group = QPalette.ColorGroup


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """Linear blend: t=0 → a, t=1 → b."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def luminance(c: QColor) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.red()) + 0.7152 * ch(c.green()) + 0.0722 * ch(c.blue())


def contrast(a: QColor, b: QColor) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---------------------------------------------------------------- KDE colour schemes

def kdeglobals_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "kdeglobals")


def _parse_color(value):
    value = (value or "").strip()
    if not value:
        return None
    if value.startswith("#"):
        c = QColor(value)
        return c if c.isValid() else None
    parts = [p.strip() for p in value.split(",")]
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    if len(nums) in (3, 4):
        return QColor(*nums)
    return None


def read_kde_scheme(path=None):
    """Returns {section: {key: QColor}} for the [Colors:*] groups, or None if unavailable."""
    path = path or kdeglobals_path()
    if not os.path.isfile(path):
        return None
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            cp.read_file(fh)
    except (OSError, configparser.Error):
        return None
    scheme = {}
    for section in cp.sections():
        if section.startswith("Colors:"):
            colors = {k: _parse_color(v) for k, v in cp.items(section)}
            scheme[section[7:]] = {k: v for k, v in colors.items() if v is not None}
    needed = ("Window", "View", "Selection")
    if not all(s in scheme and "BackgroundNormal" in scheme[s] for s in needed):
        return None
    return scheme


def palette_from_kde(scheme) -> QPalette:
    def get(section, key, fallback):
        return scheme.get(section, {}).get(key) or fallback

    window_bg = get("Window", "BackgroundNormal", QColor("#202326"))
    window_fg = get("Window", "ForegroundNormal", QColor("#fcfcfc"))
    view_bg = get("View", "BackgroundNormal", window_bg)
    view_alt = get("View", "BackgroundAlternate", view_bg)
    view_fg = get("View", "ForegroundNormal", window_fg)
    view_inactive = get("View", "ForegroundInactive", mix(view_fg, view_bg, 0.45))
    button_bg = get("Button", "BackgroundNormal", window_bg)
    button_fg = get("Button", "ForegroundNormal", window_fg)
    sel_bg = get("Selection", "BackgroundNormal", QColor("#3daee9"))
    sel_fg = get("Selection", "ForegroundNormal", QColor("#ffffff"))
    tip_bg = get("Tooltip", "BackgroundNormal", window_bg)
    tip_fg = get("Tooltip", "ForegroundNormal", window_fg)
    link = get("View", "ForegroundLink", sel_bg)
    visited = get("View", "ForegroundVisited", link)

    pal = QPalette()
    roles = {
        Role.Window: window_bg, Role.WindowText: window_fg,
        Role.Base: view_bg, Role.AlternateBase: view_alt, Role.Text: view_fg,
        Role.Button: button_bg, Role.ButtonText: button_fg, Role.BrightText: QColor("#ffffff"),
        Role.Highlight: sel_bg, Role.HighlightedText: sel_fg,
        Role.ToolTipBase: tip_bg, Role.ToolTipText: tip_fg,
        Role.Link: link, Role.LinkVisited: visited, Role.PlaceholderText: view_inactive,
        Role.Light: button_bg.lighter(150), Role.Midlight: button_bg.lighter(125),
        Role.Mid: button_bg.darker(130), Role.Dark: button_bg.darker(160), Role.Shadow: QColor(0, 0, 0),
    }
    if hasattr(Role, "Accent"):
        roles[Role.Accent] = get("Selection", "DecorationFocus", sel_bg) or sel_bg
    for role, color in roles.items():
        pal.setColor(Group.All, role, color)
    for role in (Role.WindowText, Role.Text, Role.ButtonText):
        pal.setColor(Group.Disabled, role, mix(pal.color(role), window_bg, 0.55))
    pal.setColor(Group.Disabled, Role.Highlight, mix(sel_bg, window_bg, 0.6))
    pal.setColor(Group.Inactive, Role.Highlight, sel_bg)
    return pal


def fallback_dark_palette() -> QPalette:
    """Used when the platform reports dark mode but hands Qt a light palette (some Linux desktops)."""
    pal = QPalette()
    window, base, text = QColor("#1c1f22"), QColor("#141618"), QColor("#e6e8ea")
    accent = QColor("#7cc4e0")
    for role, color in {
        Role.Window: window, Role.WindowText: text, Role.Base: base, Role.AlternateBase: window,
        Role.Text: text, Role.Button: QColor("#25292d"), Role.ButtonText: text,
        Role.Highlight: accent, Role.HighlightedText: QColor("#0f2a35"),
        Role.ToolTipBase: window, Role.ToolTipText: text, Role.Link: accent,
        Role.PlaceholderText: QColor("#7c858c"),
    }.items():
        pal.setColor(Group.All, role, color)
    if hasattr(Role, "Accent"):
        pal.setColor(Group.All, Role.Accent, accent)
    return pal


# ---------------------------------------------------------------- tokens

@dataclass
class Tokens:
    is_dark: bool
    bg: QColor           # main content area
    sidebar: QColor      # sidebar + top bar
    log_bg: QColor       # log panel
    card: QColor         # inputs, chips, hovered rows
    card_hover: QColor
    border: QColor
    text: QColor
    title: QColor        # strongest text
    muted: QColor
    accent: QColor
    on_accent: QColor
    accent_soft: QColor  # selected rows, soft chips
    positive: QColor
    negative: QColor
    neutral: QColor

    def hex(self, name):
        return getattr(self, name).name()


def tokens_from_palette(pal: QPalette, kde_scheme=None) -> Tokens:
    window = pal.color(Role.Window)
    base = pal.color(Role.Base)
    wtext = pal.color(Role.WindowText)
    vtext = pal.color(Role.Text)
    is_dark = luminance(window) < 0.2
    accent = pal.color(Role.Highlight)
    if hasattr(Role, "Accent") and not kde_scheme:
        a = pal.color(Role.Accent)
        if a.isValid() and a != QColor(0, 0, 0):
            accent = a
    on_accent = pal.color(Role.HighlightedText)
    if contrast(accent, on_accent) < 3:
        on_accent = QColor("#000000") if luminance(accent) > 0.4 else QColor("#ffffff")

    title = vtext if contrast(vtext, window) > contrast(wtext, window) else wtext
    text = mix(title, window, 0.08)

    def kde(section, key, fallback):
        if kde_scheme:
            return kde_scheme.get(section, {}).get(key) or fallback
        return fallback

    positive = kde("View", "ForegroundPositive", QColor("#3ec28f" if is_dark else "#1e8a5a"))
    negative = kde("View", "ForegroundNegative", QColor("#ff6b81" if is_dark else "#c62f45"))
    neutral = kde("View", "ForegroundNeutral", QColor("#f4a62a" if is_dark else "#b56a00"))

    toward = QColor("#ffffff") if is_dark else QColor("#000000")
    sidebar = mix(window, base, 0.55) if is_dark else mix(window, toward, 0.03)
    return Tokens(
        is_dark=is_dark,
        bg=window,
        sidebar=sidebar,
        log_bg=mix(window, base, 0.3),
        card=mix(window, toward, 0.06 if is_dark else 0.05),
        card_hover=mix(window, toward, 0.10 if is_dark else 0.09),
        border=mix(window, toward, 0.10 if is_dark else 0.12),
        text=text,
        title=title,
        muted=mix(title, window, 0.42),
        accent=accent,
        on_accent=on_accent,
        accent_soft=mix(window, accent, 0.18 if is_dark else 0.14),
        positive=positive,
        negative=negative,
        neutral=neutral,
    )


def stylesheet(t: Tokens) -> str:
    h = t.hex
    accent_hover = (t.accent.lighter(110) if t.is_dark else t.accent.darker(108)).name()
    accent_pressed = (t.accent.darker(110)).name()
    return f"""
* {{ outline: none; }}
QMainWindow, QDialog, #Root, #MainArea {{ background: {h('bg')}; color: {h('text')}; }}
QLabel {{ color: {h('text')}; background: transparent; }}
QToolTip {{ background: {h('card')}; color: {h('title')}; border: 1px solid {h('border')};
            border-radius: 6px; padding: 4px 8px; }}

#TopBar {{ background: {h('sidebar')}; border-bottom: 1px solid {h('border')}; }}
#BrandTab {{ background: {h('card')}; border-radius: 10px; border-bottom: 2px solid {h('accent')}; }}
#BrandName {{ color: {h('title')}; font-weight: 700; }}
#TopTab {{ color: {h('muted')}; }}

#Sidebar {{ background: {h('sidebar')}; border-right: 1px solid {h('border')}; }}
#SectionHeader {{ color: {h('muted')}; font-weight: 700; letter-spacing: 1.5px; }}
#SidebarFooter {{ border-top: 1px solid {h('border')}; }}
#Muted, #NavSub, #ToggleSub {{ color: {h('muted')}; }}
#NavTitle, #ToggleTitle {{ color: {h('text')}; font-weight: 600; }}
#ToggleTitle[danger="true"] {{ color: {h('negative')}; }}
#Version {{ color: {h('muted')}; }}

#FolderButton {{ background: {h('card')}; border: 1px solid {h('border')}; border-radius: 12px;
                 padding: 10px 12px; text-align: left; color: {h('text')}; }}
#FolderButton:hover {{ background: {h('card_hover')}; border-color: {h('accent')}; }}
#FolderButton:disabled {{ color: {h('muted')}; }}

#NavRow {{ background: transparent; border: none; border-radius: 10px; text-align: left; }}
#NavRow:hover {{ background: {h('card')}; }}
#NavRow:checked {{ background: {h('accent_soft')}; }}
#NavRow:disabled {{ background: transparent; }}
#NavRow:checked:disabled {{ background: {h('card')}; }}
#ToggleRow {{ border-radius: 10px; }}
#ToggleRow:hover {{ background: {h('card')}; }}

#HeroTitle {{ color: {h('title')}; font-weight: 700; }}
#HeroSub {{ color: {h('muted')}; }}
#StatChip {{ background: {h('card')}; border: 1px solid {h('border')}; border-radius: 10px;
             padding: 5px 12px; color: {h('text')}; }}

QPushButton#PrimaryButton {{ background: {h('accent')}; color: {h('on_accent')}; border: none;
    border-radius: 12px; padding: 11px 26px; font-weight: 700; }}
QPushButton#PrimaryButton:hover {{ background: {accent_hover}; }}
QPushButton#PrimaryButton:pressed {{ background: {accent_pressed}; }}
QPushButton#PrimaryButton:disabled {{ background: {h('card')}; color: {h('muted')}; }}

QPushButton#SecondaryButton {{ background: {h('card')}; color: {h('text')}; border: 1px solid {h('border')};
    border-radius: 12px; padding: 10px 20px; font-weight: 600; }}
QPushButton#SecondaryButton:hover {{ background: {h('card_hover')}; }}
QPushButton#SecondaryButton:disabled {{ color: {h('muted')}; }}

QToolButton#IconButton {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton#IconButton:hover {{ background: {h('card_hover')}; }}
QToolButton#IconButton::menu-indicator {{ image: none; width: 0; }}

QPushButton#UpdateChip {{ background: {h('accent_soft')}; color: {h('title')}; border: 1px solid {h('accent')};
    border-radius: 11px; padding: 5px 14px; font-weight: 600; }}
QPushButton#UpdateChip:hover {{ background: {h('accent')}; color: {h('on_accent')}; }}

QProgressBar {{ background: {h('card')}; border: none; border-radius: 4px; max-height: 8px; min-height: 8px; }}
QProgressBar::chunk {{ background: {h('accent')}; border-radius: 4px; }}

#LogPanel {{ background: {h('log_bg')}; border-top: 1px solid {h('border')}; }}
#LogHeader {{ border-bottom: 1px solid {h('border')}; }}
#LogTitle {{ color: {h('title')}; font-weight: 700; }}
QTextBrowser#Log, QTextBrowser#Notes {{ background: transparent; border: none; color: {h('text')};
    selection-background-color: {h('accent')}; selection-color: {h('on_accent')}; }}
QTextBrowser#Notes {{ background: {h('card')}; border: 1px solid {h('border')}; border-radius: 10px; padding: 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {h('border')}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {h('muted')}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {h('border')}; border-radius: 3px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {h('card')}; color: {h('text')}; border: 1px solid {h('border')}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px 7px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {h('accent_soft')}; color: {h('title')}; }}
QMenu::separator {{ height: 1px; background: {h('border')}; margin: 4px 6px; }}
QMenu::indicator {{ width: 14px; height: 14px; margin-left: 6px; }}
"""


# ---------------------------------------------------------------- manager

class ThemeManager(QObject):
    """Applies the system colours and re-applies them whenever they change."""

    changed = Signal(object)  # Tokens

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.tokens = None
        self._kde_path = kdeglobals_path() if sys.platform.startswith("linux") else None
        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self.apply)
        self._watcher = None
        self._applying = False
        if self._kde_path:
            self._watcher = QFileSystemWatcher(self)
            # Watch the directory too: colour tools often replace kdeglobals atomically
            self._watcher.addPath(os.path.dirname(self._kde_path))
            if os.path.exists(self._kde_path):
                self._watcher.addPath(self._kde_path)
            self._watcher.fileChanged.connect(self._schedule)
            self._watcher.directoryChanged.connect(self._schedule)
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._schedule)

    def _schedule(self, *_):
        if self._watcher and self._kde_path and os.path.exists(self._kde_path) \
                and self._kde_path not in self._watcher.files():
            self._watcher.addPath(self._kde_path)
        self._debounce.start()

    def _platform_palette(self):
        self.app.setPalette(QPalette())  # drop any override so we read the platform's own palette
        pal = self.app.palette()
        hints = QGuiApplication.styleHints()
        dark_mode = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
        if dark_mode and luminance(pal.color(Role.Window)) > 0.4:
            pal = fallback_dark_palette()
            self.app.setPalette(pal)
        return pal

    def apply(self):
        self._applying = True
        try:
            scheme = read_kde_scheme(self._kde_path) if self._kde_path else None
            if scheme:
                pal = palette_from_kde(scheme)
                self.app.setPalette(pal)
            else:
                pal = self._platform_palette()
            tokens = tokens_from_palette(pal, scheme)
            self.app.setStyleSheet(stylesheet(tokens))
            self.tokens = tokens
        finally:
            self._applying = False
        self.changed.emit(tokens)
        return tokens
