"""Reusable pieces of the DeluxeCHD interface."""
from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from deluxechd.ui import icons


def scaled_font(widget, factor=1.0, bold=False):
    f = widget.font()
    if f.pointSizeF() > 0:
        f.setPointSizeF(f.pointSizeF() * factor)
    else:
        f.setPixelSize(max(1, round(f.pixelSize() * factor)))
    if bold:
        f.setBold(True)
    return f


def section_header(text):
    lbl = QLabel(text.upper())
    lbl.setObjectName("SectionHeader")
    lbl.setFont(scaled_font(lbl, 0.82, bold=True))
    return lbl


class Switch(QAbstractButton):
    """A small animated on/off switch painted with theme colours."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)
        self.tokens = None

    def sizeHint(self):
        return QSize(40, 22)

    def _get_knob(self):
        return self._pos

    def _set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def setChecked(self, on):
        super().setChecked(on)
        self._anim.stop()
        self._pos = 1.0 if on else 0.0
        self.update()

    def paintEvent(self, _e):
        t = self.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        on_track = t.accent if t else self.palette().highlight().color()
        off_track = t.card_hover if t else self.palette().mid().color()
        track = QColor(
            round(off_track.red() + (on_track.red() - off_track.red()) * self._pos),
            round(off_track.green() + (on_track.green() - off_track.green()) * self._pos),
            round(off_track.blue() + (on_track.blue() - off_track.blue()) * self._pos),
        )
        if not self.isEnabled():
            track.setAlphaF(0.45)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        knob = (t.on_accent if self._pos > 0.5 else t.muted) if t else self.palette().base().color()
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        if self.hasFocus():
            pen = p.pen()
            p.setPen(on_track)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-0.5, -0.5, 0.5, 0.5), r.height() / 2, r.height() / 2)
            p.setPen(pen)


class ToggleRow(QFrame):
    """Title + description on the left, Switch on the right. Clicking anywhere toggles."""

    toggled = Signal(bool)

    def __init__(self, title, subtitle="", danger=False, parent=None):
        super().__init__(parent)
        self.setObjectName("ToggleRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(10)
        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = QLabel(title)
        self.title.setObjectName("ToggleTitle")
        self.title.setProperty("danger", danger)
        text.addWidget(self.title)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("ToggleSub")
            sub.setFont(scaled_font(sub, 0.88))
            sub.setWordWrap(True)
            text.addWidget(sub)
        lay.addLayout(text, 1)
        self.switch = Switch()
        self.switch.toggled.connect(self.toggled)
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, e):
        if self.isEnabled() and e.button() == Qt.MouseButton.LeftButton:
            self.switch.toggle()
        super().mouseReleaseEvent(e)

    def isChecked(self):
        return self.switch.isChecked()

    def setChecked(self, on):
        self.switch.setChecked(on)

    def set_tokens(self, tokens):
        self.switch.tokens = tokens
        self.switch.update()


class NavRow(QPushButton):
    """Checkable sidebar row with an icon, title and a muted subtitle (like a channel list)."""

    def __init__(self, icon_name, title, subtitle, value, parent=None):
        super().__init__(parent)
        self.setObjectName("NavRow")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_name = icon_name
        self.value = value
        self.tokens = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 7, 10, 7)
        lay.setSpacing(12)
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(20, 20)
        lay.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("NavTitle")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("NavSub")
        self.sub_lbl.setFont(scaled_font(self.sub_lbl, 0.88))
        text.addWidget(self.title_lbl)
        text.addWidget(self.sub_lbl)
        lay.addLayout(text, 1)
        for w in (self.icon_lbl, self.title_lbl, self.sub_lbl):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.toggled.connect(lambda _on: self.refresh())

    def sizeHint(self):
        h = self.title_lbl.sizeHint().height() + self.sub_lbl.sizeHint().height() + 16
        return QSize(200, max(44, h))

    def set_tokens(self, tokens):
        self.tokens = tokens
        self.refresh()

    def refresh(self):
        if self.tokens:
            color = self.tokens.accent if self.isChecked() else self.tokens.muted
            self.icon_lbl.setPixmap(icons.pixmap(self.icon_name, color, 20))


class ElidedLabel(QLabel):
    """QLabel that elides long text in the middle (for folder paths)."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text):
        self._full = text
        self._update()

    def fullText(self):
        return self._full

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update()

    def _update(self):
        fm = QFontMetrics(self.font())
        super().setText(fm.elidedText(self._full, Qt.TextElideMode.ElideMiddle, max(10, self.width())))


class FolderButton(QPushButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("FolderButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        self.icon_lbl = QLabel()
        self.icon_lbl.setFixedSize(20, 20)
        lay.addWidget(self.icon_lbl)
        text = QVBoxLayout()
        text.setSpacing(0)
        self.title = QLabel("Choose a folder…")
        self.title.setObjectName("NavTitle")
        self.path = ElidedLabel("or drop one onto the window")
        self.path.setObjectName("NavSub")
        self.path.setFont(scaled_font(self.path, 0.88))
        text.addWidget(self.title)
        text.addWidget(self.path)
        lay.addLayout(text, 1)
        for w in (self.icon_lbl, self.title, self.path):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setMinimumHeight(58)

    def set_folder(self, folder):
        import os
        name = os.path.basename(folder.rstrip("/\\")) or folder
        self.title.setText(name)
        self.path.setText(folder)
        self.setToolTip(folder)

    def set_tokens(self, tokens):
        self.icon_lbl.setPixmap(icons.pixmap("folder", tokens.accent, 20))


class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self.color = QColor("#888")

    def set_color(self, c):
        self.color = c
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(1, 1, 8, 8))
