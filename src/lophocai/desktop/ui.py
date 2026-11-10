"""Widget dùng chung, vẽ tay để giống hệt giao diện web (web/index.html): nút, chip, tag màu,
công tắc, donut, vòng tập trung, biểu đồ cột, meter, thông báo, khung video...

Tất cả đọc màu qua lophocai.desktop.theme nên tự đổi theo giao diện sáng/tối.
"""
import math
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QToolTip, QVBoxLayout, QWidget)

from . import theme
from .icons import BEHAVIOR_ICON, IconLabel, icon_pixmap

OVERLAY_BG = QColor(11, 15, 23, 179)        # #0b0f17b3: nền chip/nút nổi trên video
OVERLAY_BORDER = QColor(255, 255, 255, 26)  # #ffffff1a
OVERLAY_TEXT = "#e8edf6"


# ---------------------------------------------------------------- tiện ích
def repolish(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


def make_label(text="", role=None, wrap=False, rich=False, parent=None):
    lab = QLabel(text, parent)
    if role:
        lab.setProperty("role", role)
    if wrap:
        lab.setWordWrap(True)
    if rich:
        lab.setTextFormat(Qt.TextFormat.RichText)
    return lab


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def hbox(*items, spacing=8, margins=(0, 0, 0, 0), parent=None):
    """HBox nhanh: phần tử là widget, "stretch" hoặc (widget, stretch)."""
    lay = QHBoxLayout(parent) if parent is not None else QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        if it == "stretch":
            lay.addStretch(1)
        elif isinstance(it, tuple):
            lay.addWidget(it[0], it[1])
        else:
            lay.addWidget(it)
    return lay


def vbox(*items, spacing=8, margins=(0, 0, 0, 0), parent=None):
    lay = QVBoxLayout(parent) if parent is not None else QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        if it == "stretch":
            lay.addStretch(1)
        elif isinstance(it, tuple):
            lay.addWidget(it[0], it[1])
        else:
            lay.addWidget(it)
    return lay


def snapshot_path(engine, snap):
    """Đường dẫn file ảnh chụp từ giá trị lưu trong sự kiện ("/snapshots/x.jpg") hoặc CSV (đường dẫn đầy đủ)."""
    if not snap:
        return None
    if snap.startswith("/snapshots/"):
        return Path(engine.logger.snap_dir) / Path(snap).name
    p = Path(snap)
    return p if p.is_absolute() else Path(engine.logger.snap_dir) / p.name


# ---------------------------------------------------------------- thẻ
class Card(QFrame):
    """Thẻ nền surface, viền mảnh, bo 16 (.card của web). alarm=True: viền đỏ (.kpi.alarm)."""

    def __init__(self, parent=None, alarm=False, dashed=False):
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setProperty("alarm", "true" if alarm else "false")
        if dashed:
            self.setProperty("dashed", "true")
        self.setFrameShape(QFrame.Shape.NoFrame)

    def set_alarm(self, on):
        on = "true" if on else "false"
        if self.property("alarm") != on:
            self.setProperty("alarm", on)
            repolish(self)


def card_header(title, icon=None, trailing=None, margins=(18, 16, 18, 0)):
    """Dòng tiêu đề của thẻ (.card-h): [icon] tiêu đề ... [các widget bên phải]."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(10)
    if icon:
        lay.addWidget(IconLabel(icon, 18, "text"))
    lay.addWidget(make_label(title, "h2"))
    lay.addStretch(1)
    for t in (trailing or []):
        lay.addWidget(t)
    return w


def separator():
    f = QFrame()
    f.setProperty("sep", "true")
    f.setFixedHeight(1)
    return f


# ---------------------------------------------------------------- chấm trạng thái / chip / tag
class Dot(QWidget):
    """Chấm tròn trạng thái: "" xám, "on" xanh lá có quầng, "alarm" đỏ nhấp nháy, "starting" cam nhấp nháy."""

    def __init__(self, state="", color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._state, self._color, self._phase = state, color, False
        self._timer = QTimer(self)
        self._timer.setInterval(550)
        self._timer.timeout.connect(self._blink)
        self.set_state(state)
        theme.manager.changed.connect(self.update)

    def set_state(self, state, color=None):
        if color is not None:
            self._color = color
        self._state = state
        if state in ("alarm", "starting", "blink"):
            self._timer.start()
        else:
            self._timer.stop()
            self._phase = False
        self.update()

    def _blink(self):
        self._phase = not self._phase
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._state
        base = {"on": "ok", "alarm": "bad", "starting": "head", "error": "bad"}.get(s, "faint")
        col = QColor(self._color) if self._color else theme.qcolor(base)
        center = QPointF(self.width() / 2, self.height() / 2)
        if s in ("on", "alarm") and not self._color:
            glow = theme.qcolor(base, 0x22 if s == "on" else 0x33)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(center, 6.5, 6.5)
        if self._phase:
            col.setAlphaF(0.35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawEllipse(center, 4, 4)


class Chip(QFrame):
    """Viên thuốc nhỏ (.chip): variant "default" | "overlay" (nổi trên video) | "live" | "badge"."""

    def __init__(self, text="", variant="default", dot=False, icon=None, icon_size=14, compact=False, parent=None):
        super().__init__(parent)
        self.variant = variant
        lay = QHBoxLayout(self)
        py, px = (3, 10) if compact else (6, 12)
        if variant == "badge":
            py, px = 0, 7
        lay.setContentsMargins(px, py, px, py)
        lay.setSpacing(7)
        self.dot = None
        if dot:
            self.dot = Dot("blink", "#ffffff") if variant == "live" else Dot()
            lay.addWidget(self.dot)
        self.icon = None
        if icon:
            self.icon = IconLabel(icon, icon_size, "muted" if variant == "default" else OVERLAY_TEXT)
            lay.addWidget(self.icon)
        self.label = QLabel(text)
        font_px = 12 if (compact or variant == "badge") else 13
        css = f"font-size:{font_px}px;"
        if variant == "overlay":
            css += f"color:{OVERLAY_TEXT};"
        elif variant == "live":
            css += "color:#ffffff; font-weight:700; letter-spacing:1px;"
        elif variant == "badge":
            css += "color:#ffffff; font-weight:700; font-size:11px;"
        else:
            self.label.setProperty("role", "chipText")
        if variant != "default":
            self.label.setStyleSheet(css)
        else:
            self.label.setStyleSheet(f"font-size:{font_px}px;")
        lay.addWidget(self.label)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        theme.manager.changed.connect(self.update)

    def set_text(self, text):
        self.label.setText(text)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = 4
        v = self.variant
        if v == "live" or v == "badge":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor("bad"))
        elif v == "overlay":
            p.setPen(QPen(OVERLAY_BORDER, 1))
            p.setBrush(OVERLAY_BG)
        else:
            p.setPen(QPen(theme.qcolor("border"), 1))
            p.setBrush(theme.qcolor("surface"))
        p.drawRoundedRect(r, rad, rad)


class Tag(QFrame):
    """Nhãn hành vi có màu (.tag): icon + tên, nền là màu hành vi ở 18%."""

    def __init__(self, behavior, text=None, icon=True, parent=None):
        super().__init__(parent)
        self._color = theme.behavior_color(behavior)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(9, 2, 9, 2)
        lay.setSpacing(5)
        if icon:
            lay.addWidget(IconLabel(BEHAVIOR_ICON.get(behavior, "alert"), 12, self._color))
        self.label = QLabel(text or theme.BEHAVIOR_SHORT.get(behavior, behavior))
        self.label.setStyleSheet(f"color:{self._color}; font-size:12px; font-weight:600;")
        lay.addWidget(self.label)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(self._color)
        col.setAlpha(46)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        r = QRectF(self.rect())
        p.drawRoundedRect(r, 4, 4)


# ---------------------------------------------------------------- nút
_BUTTON_PAD = {"default": (14, 8), "primary": (14, 8), "ghost": (14, 8), "danger": (14, 8), "icon": (8, 8),
               "overlay": (8, 8), "tab": (14, 7), "nav": (12, 10), "setnav": (12, 10), "seg": (8, 7)}


class Button(QPushButton):
    """Nút vẽ tay giống button của web. variant: default | primary | ghost | danger | overlay | seg | tab | nav | setnav.
    Chỉ có icon (không chữ) thì tự thành nút vuông (.icon)."""

    def __init__(self, text="", icon=None, variant="default", checkable=False, icon_size=18, font_px=14, parent=None):
        super().__init__(parent)
        self._text, self._icon, self.variant = text, icon, variant
        self._isz, self._font_px = icon_size, font_px
        self._on = False
        self._hover = False
        self._badge = None
        self._fg = None
        self.setCheckable(checkable)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        theme.manager.changed.connect(self.update)

    # --- API
    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        self.updateGeometry()
        self.update()

    def set_icon(self, name):
        self._icon = name
        self.updateGeometry()
        self.update()

    def set_variant(self, variant):
        self.variant = variant
        self.updateGeometry()
        self.update()

    def set_on(self, on):
        if self._on != bool(on):
            self._on = bool(on)
            self.update()

    def set_fg(self, token):
        self._fg = token
        self.update()

    def set_badge(self, text):
        self._badge = str(text) if text not in (None, "", 0) else None
        self.updateGeometry()
        self.update()

    # --- kích thước
    def _font(self):
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(self._font_px)
        f.setWeight(QFont.Weight.Medium)
        return f

    def _pad(self):
        return _BUTTON_PAD.get(self.variant, (14, 8))

    def _content_width(self, fm):
        w = 0
        if self._icon:
            w += self._isz
        if self._text:
            w += (8 if self._icon else 0) + fm.horizontalAdvance(self._text)
        if self._badge:
            w += 10 + max(20, fm.horizontalAdvance(self._badge) + 12)
        return w

    def sizeHint(self):
        fm = QFontMetrics(self._font())
        px, py = self._pad()
        h = max(self._isz if self._icon else 0, fm.height() + 1) + 2 * py + 2
        return QSize(self._content_width(fm) + 2 * px + 2, h)

    def minimumSizeHint(self):
        return self.sizeHint()

    # --- vẽ
    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def _colors(self):
        v, on = self.variant, self.isChecked() or self._on
        hover = self._hover and self.isEnabled()
        T = theme.qcolor
        transparent = QColor(0, 0, 0, 0)
        if v == "primary":
            bg = QColor(theme.lighten("accent")) if hover else T("accent")
            return bg, T("accent"), QColor("#ffffff"), QColor("#ffffff")
        if v == "ghost":
            fg = T(self._fg or "text")
            return (T("surface2") if hover else transparent), transparent, fg, fg
        if v == "danger":
            bg = T("bad", 26) if hover else T("surface2")
            return bg, (T("bad") if hover else T("border")), T("bad"), T("bad")
        if v == "overlay":
            if on:
                return T("accent"), T("accent"), QColor("#ffffff"), QColor("#ffffff")
            return OVERLAY_BG, OVERLAY_BORDER, QColor(OVERLAY_TEXT), QColor(OVERLAY_TEXT)
        if v == "seg":
            if on:
                return T("accent"), T("accent"), QColor("#ffffff"), QColor("#ffffff")
            return QColor(255, 255, 255, 30 if hover else 18), QColor(255, 255, 255, 31), QColor(OVERLAY_TEXT), QColor(OVERLAY_TEXT)
        if v == "tab":
            if on:
                return theme.accent_soft(), T("accent"), T("text"), T("text")
            return (T("surface3") if hover else T("surface")), T("border"), T("text"), T("text")
        if v in ("nav", "setnav"):
            fg = T(self._fg) if self._fg else (T("text") if (hover or on) else T("muted"))
            ic = T("accent") if on else fg
            bg = theme.accent_soft() if on else (T("surface2") if hover else transparent)
            return bg, transparent, fg, ic
        # default / icon
        if on:
            return T("accent"), T("accent"), QColor("#ffffff"), QColor("#ffffff")
        return (T("surface3") if hover else T("surface2")), T("border"), T("text"), T("text")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        if self.isDown():
            p.translate(0, 1)
        bg, border, fg, ic = self._colors()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = 6
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        fm = QFontMetrics(self._font())
        px, _ = self._pad()
        content_w = self._content_width(fm)
        left_align = self.variant in ("nav", "setnav")
        x = (px + 1) if left_align else (self.width() - content_w) / 2
        cy = self.height() / 2
        if self._icon:
            pm = icon_pixmap(self._icon, self._isz, ic.name())
            p.drawPixmap(QPointF(x, cy - self._isz / 2), pm)
            x += self._isz + (8 if self._text else 0)
        if self._text:
            p.setFont(self._font())
            p.setPen(fg)
            tw = fm.horizontalAdvance(self._text)
            p.drawText(QRectF(x, 0, tw + 2, self.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
            x += tw
        if self._badge:
            bw = max(20, fm.horizontalAdvance(self._badge) + 12)
            bx = self.width() - px - 1 - bw if left_align else x + 10
            br = QRectF(bx, cy - 9, bw, 18)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor("bad"))
            p.drawRoundedRect(br, 9, 9)
            bf = QFont(theme.FONT_FAMILY)
            bf.setPixelSize(11)
            bf.setWeight(QFont.Weight.Bold)
            p.setFont(bf)
            p.setPen(QColor("#ffffff"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, self._badge)


# ---------------------------------------------------------------- công tắc
class Switch(QAbstractButton):
    """Công tắc bật/tắt 42x24 (.switch của web)."""

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(42, 24)
        self._pos = 1.0 if checked else 0.0
        self.setChecked(checked)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self.toggled.connect(self._animate)
        theme.manager.changed.connect(self.update)

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def sizeHint(self):
        return QSize(42, 24)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._pos
        track = QColor(theme.mix("surface3", "accent", t))
        edge = QColor(theme.mix("border", "accent", t))
        r = QRectF(0.5, 0.5, 41, 23)
        p.setPen(QPen(edge, 1))
        p.setBrush(track)
        p.drawRoundedRect(r, 11.5, 11.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 50))
        p.drawEllipse(QPointF(3 + 18 * t + 9, 12.8), 9, 9)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QPointF(3 + 18 * t + 9, 12), 9, 9)


# ---------------------------------------------------------------- biểu đồ
def focus_color(v):
    return "ok" if v >= 80 else "head" if v >= 55 else "bad"


def focus_label(v):
    return "Chưa có dữ liệu" if v is None else "Tập trung tốt" if v >= 80 else "Trung bình" if v >= 55 else "Dễ mất tập trung"


class Donut(QWidget):
    """Biểu đồ tròn rỗng giữa (.donut): vòng dày 24, số tổng + chữ phụ ở giữa."""

    def __init__(self, size=170, ring=24, parent=None):
        super().__init__(parent)
        self._size, self._ring = size, ring
        self._segments, self._total, self._caption = [], 0, "cảnh báo"
        self.setFixedSize(size, size)
        theme.manager.changed.connect(self.update)

    def set_data(self, segments, total, caption="cảnh báo"):
        """segments: [(màu "#rrggbb", giá trị)]"""
        self._segments, self._total, self._caption = segments, total, caption
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = self._ring / 2
        rect = QRectF(half, half, self._size - self._ring, self._size - self._ring)
        total = sum(v for _, v in self._segments)
        if total <= 0:
            pen = QPen(theme.qcolor("surface3"), self._ring)
            p.setPen(pen)
            p.drawEllipse(rect)
        else:
            start = 90.0
            for color, val in self._segments:
                if val <= 0:
                    continue
                span = val / total * 360.0
                pen = QPen(QColor(color), self._ring)
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.drawArc(rect, int(start * 16), int(-span * 16))
                start -= span
        p.setPen(theme.qcolor("text"))
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(30)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.drawText(QRectF(0, self._size / 2 - 30, self._size, 32), Qt.AlignmentFlag.AlignCenter, str(self._total))
        f2 = QFont(theme.FONT_FAMILY)
        f2.setPixelSize(12)
        p.setFont(f2)
        p.setPen(theme.qcolor("muted"))
        p.drawText(QRectF(0, self._size / 2 + 2, self._size, 18), Qt.AlignmentFlag.AlignCenter, self._caption)


class FocusRing(QWidget):
    """Vòng tròn "Mức độ tập trung" (.fring): cung tiến độ + số lớn + nhãn."""

    def __init__(self, size=112, ring=11, parent=None):
        super().__init__(parent)
        self._size, self._ring = size, ring
        self._value = None
        self.setFixedSize(size, size)
        theme.manager.changed.connect(self.update)

    def set_value(self, v):
        self._value = None if v is None else float(v)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        half = self._ring / 2
        rect = QRectF(half, half, self._size - self._ring, self._size - self._ring)
        track = QPen(theme.qcolor("surface3"), self._ring)
        track.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(track)
        p.drawEllipse(rect)
        v = self._value
        col = theme.qcolor(focus_color(v)) if v is not None else theme.qcolor("surface3")
        if v:
            pen = QPen(col, self._ring)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, int(-min(v, 100) / 100 * 360 * 16))
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(30)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(col if v is not None else theme.qcolor("muted"))
        p.drawText(QRectF(0, self._size / 2 - 24, self._size, 34), Qt.AlignmentFlag.AlignCenter,
                   "–" if v is None else str(round(v)))
        f2 = QFont(theme.FONT_FAMILY)
        f2.setPixelSize(10)
        p.setFont(f2)
        p.setPen(theme.qcolor("muted"))
        p.drawText(QRectF(self._ring, self._size / 2 + 10, self._size - 2 * self._ring, 28),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   focus_label(v))


class BarChart(QWidget):
    """Biểu đồ cột xếp chồng (.chart): bars = [{"segments": [(màu, giá trị)], "tip": "..."}], ô rỗng là gạch mảnh."""

    def __init__(self, chart_height=240, gap=4, min_bar=4, radius=4, top_round_only=False, top_pad=10,
                 axis_font_px=12, parent=None):
        super().__init__(parent)
        self._h, self._gap, self._min_bar, self._radius = chart_height, gap, min_bar, radius
        self._top_only, self._top_pad, self._axis_px = top_round_only, top_pad, axis_font_px
        self._bars, self._max, self._axis = [], 1.0, []
        self.setMouseTracking(True)
        self.setMinimumHeight(chart_height + 26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.manager.changed.connect(self.update)

    def sizeHint(self):
        return QSize(300, self._h + 26)

    def set_data(self, bars, max_value=None, axis_labels=None):
        self._bars = bars
        if max_value is None:
            max_value = max([sum(v for _, v in b.get("segments", [])) for b in bars] + [1])
        self._max = float(max(max_value, 1e-9))
        self._axis = axis_labels or []
        self.update()

    def _geometry(self):
        n = max(1, len(self._bars))
        bw = max(self._min_bar, (self.width() - self._gap * (n - 1)) / n)
        return n, bw

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n, bw = self._geometry()
        base_y = self._h - 1
        area_h = base_y - self._top_pad
        for i, bar in enumerate(self._bars):
            x = i * (bw + self._gap)
            segs = [(c, v) for c, v in bar.get("segments", []) if v > 0]
            y = base_y
            if not segs:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.qcolor("surface3"))
                p.drawRect(QRectF(x, base_y - 2, bw, 2))
                continue
            for c, v in segs:
                h = max(1.0, v / self._max * area_h)
                rect = QRectF(x, y - h, bw, h)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c))
                if self._top_only:
                    path = QPainterPath()
                    r = min(self._radius, bw / 2, h)
                    path.moveTo(rect.left(), rect.bottom())
                    path.lineTo(rect.left(), rect.top() + r)
                    path.quadTo(rect.left(), rect.top(), rect.left() + r, rect.top())
                    path.lineTo(rect.right() - r, rect.top())
                    path.quadTo(rect.right(), rect.top(), rect.right(), rect.top() + r)
                    path.lineTo(rect.right(), rect.bottom())
                    path.closeSubpath()
                    p.drawPath(path)
                else:
                    p.drawRoundedRect(rect, self._radius, self._radius)
                y -= h + 2
        p.setPen(QPen(theme.qcolor("border"), 1))
        p.drawLine(0, int(base_y + 0.5), self.width(), int(base_y + 0.5))
        if self._axis:
            f = QFont(theme.FONT_FAMILY)
            f.setPixelSize(self._axis_px)
            p.setFont(f)
            p.setPen(theme.qcolor("muted"))
            fm = QFontMetrics(f)
            k = len(self._axis)
            for j, text in enumerate(self._axis):
                tw = fm.horizontalAdvance(text)
                if k == 1:
                    x = 0
                elif j == 0:
                    x = 0
                elif j == k - 1:
                    x = self.width() - tw
                else:
                    x = (self.width() - tw) * j / (k - 1)
                p.drawText(QPointF(x, self._h + 6 + fm.ascent()), text)

    def mouseMoveEvent(self, e):
        n, bw = self._geometry()
        i = int(e.position().x() // (bw + self._gap))
        if 0 <= i < len(self._bars) and self._bars[i].get("tip"):
            QToolTip.showText(e.globalPosition().toPoint(), self._bars[i]["tip"], self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(e)


class Meter(QWidget):
    """Thanh ngang xếp đoạn màu (.meter / .hwtrack): set_segments([(màu, giá trị)], total=None)."""

    def __init__(self, height=6, min_width=80, parent=None):
        super().__init__(parent)
        self._segs, self._total = [], None
        self.setFixedHeight(height)
        self.setMinimumWidth(min_width)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.manager.changed.connect(self.update)

    def set_segments(self, segments, total=None):
        self._segs, self._total = segments, total
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setClipPath(path)
        p.fillRect(r, theme.qcolor("surface3"))
        total = self._total if self._total else (sum(v for _, v in self._segs) or 1)
        x = 0.0
        for color, v in self._segs:
            w = r.width() * v / total
            p.fillRect(QRectF(x, 0, w, r.height()), QColor(color))
            x += w


# ---------------------------------------------------------------- thông báo / trạng thái rỗng
class Notice(QFrame):
    """Khung thông báo (.notice): variant "default" (tím nhạt) | "warn" (cam) | "ok" (xanh lá)."""

    linkActivated = Signal(str)

    def __init__(self, html="", variant="default", icon="gauge", parent=None):
        super().__init__(parent)
        self.variant = variant
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        self.icon = IconLabel(icon, 18, "head")
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        self.label = QLabel(html)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setOpenExternalLinks(False)
        self.label.setStyleSheet("font-size:13px;")
        self.label.linkActivated.connect(self.linkActivated.emit)
        lay.addWidget(self.label, 1)
        self.set_variant(variant)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        theme.manager.changed.connect(self.update)

    def set_variant(self, variant, icon=None):
        self.variant = variant
        self.icon.set_icon(icon, "ok" if variant == "ok" else "head")
        self.update()

    def set_html(self, html):
        self.label.setText(html)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.variant == "warn":
            bg, bd = theme.qcolor("head", 0x1f), theme.qcolor("head", 0x66)
        elif self.variant == "ok":
            bg, bd = theme.qcolor("ok", 0x14), theme.qcolor("ok", 0x55)
        else:
            bg, bd = theme.accent_soft(), theme.qcolor("accent", 0x59)
        p.setPen(QPen(bd, 1))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)


class EmptyState(QWidget):
    """Trạng thái rỗng giữa thẻ (.empty): ô icon + dòng chữ + gợi ý nhỏ."""

    def __init__(self, icon="check", text="", hint="", tone="ok", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)
        self._tone = tone
        self._box = QFrame()
        self._box.setFixedSize(54, 54)
        bl = QVBoxLayout(self._box)
        bl.setContentsMargins(0, 0, 0, 0)
        self._ic = IconLabel(icon, 26, tone)
        bl.addWidget(self._ic, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._box, 0, Qt.AlignmentFlag.AlignHCenter)
        t = make_label(text, "muted")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        if hint:
            h = make_label(hint, "hint")
            h.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(h)
        self._box.paintEvent = self._paint_box
        theme.manager.changed.connect(self._box.update)

    def _paint_box(self, _):
        p = QPainter(self._box)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(self._tone, 26))
        p.drawRoundedRect(QRectF(self._box.rect()), 16, 16)


# ---------------------------------------------------------------- video / ảnh
class VideoSurface(QWidget):
    """Vùng hiển thị video: ảnh co vừa khung (object-fit: contain) trên nền gần đen. Nhận QImage."""

    clicked = Signal()

    def __init__(self, bg="#05070b", radius=0, placeholder_icon=None, parent=None):
        super().__init__(parent)
        self._bg, self._radius = QColor(bg), radius
        self._image, self._text = None, ""
        self._ph_icon = placeholder_icon
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_image(self, image):
        self._image = image
        self.update()

    def clear(self, text=""):
        self._image, self._text = None, text
        self.update()

    def set_placeholder_icon(self, name):
        self._ph_icon = name
        self.update()

    def has_image(self):
        return self._image is not None

    def mousePressEvent(self, e):
        self.clicked.emit()
        super().mousePressEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._radius:
            path = QPainterPath()
            path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
            p.setClipPath(path)
        p.fillRect(self.rect(), self._bg)
        img = self._image
        if img is not None and not img.isNull():
            iw, ih = img.width(), img.height()
            scale = min(self.width() / iw, self.height() / ih)
            w, h = iw * scale, ih * scale
            p.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), img)
        elif self._ph_icon:
            pm = icon_pixmap(self._ph_icon, 34, "faint")
            p.drawPixmap(QPointF((self.width() - 34) / 2, (self.height() - 34) / 2), pm)
        elif self._text:
            p.setPen(theme.qcolor("faint"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._text)


class ThumbLabel(QWidget):
    """Ảnh nhỏ bo góc, cắt vừa khung (object-fit: cover), bấm để phóng to. Thiếu file thì ẩn ảnh."""

    clicked = Signal(str)

    def __init__(self, width=72, height=44, radius=6, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._radius, self._pix, self._path = radius, None, None

    def set_path(self, path):
        self._path = str(path) if path else None
        pix = QPixmap(self._path) if self._path and Path(self._path).exists() else QPixmap()
        self._pix = None if pix.isNull() else pix.scaled(
            self.size() * 2, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._pix else Qt.CursorShape.ArrowCursor)
        self.update()

    def mousePressEvent(self, e):
        if self._pix and self._path:
            self.clicked.emit(self._path)
        super().mousePressEvent(e)

    def paintEvent(self, _):
        if self._pix is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        p.setClipPath(path)
        w, h = self.width(), self.height()
        pw, ph = self._pix.width(), self._pix.height()
        sx, sy = (pw - w * 2) / 2, (ph - h * 2) / 2
        p.drawPixmap(QRectF(0, 0, w, h), self._pix, QRectF(max(0, sx), max(0, sy), w * 2, h * 2))
