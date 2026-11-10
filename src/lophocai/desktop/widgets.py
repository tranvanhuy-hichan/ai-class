"""Widget của trang Trực tiếp: thẻ KPI, tab camera, sân khấu video (.stage), ô lưới (.tile), toàn màn hình."""
from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget)

from . import theme
from .icons import IconLabel
from .ui import Button, Card, Chip, Dot, VideoSurface, make_label, repolish
from .widgets_view_panel import ViewPanel

STAGE_BG = "#05070b"


class KpiCard(Card):
    """Thẻ số liệu (.kpi): ô icon màu + số lớn + nhãn. tone: tên màu trong theme (accent2, bad, phone, head...)."""

    def __init__(self, icon, tone, label, parent=None):
        super().__init__(parent)
        self._tone = tone
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(96)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 14, 12, 14)
        lay.setSpacing(10)
        self._box = QFrame()
        self._box.setFixedSize(38, 38)
        bl = QVBoxLayout(self._box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(IconLabel(icon, 22, tone), 0, Qt.AlignmentFlag.AlignCenter)
        self._box.paintEvent = self._paint_box
        lay.addWidget(self._box)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.value_label = make_label("0", "kpiValue")
        self.value_label.setProperty("alarm", "false")
        self.caption = make_label(label, "kpiLabel")
        self.caption.setWordWrap(True)
        col.addWidget(self.value_label)
        col.addWidget(self.caption)
        lay.addLayout(col, 1)
        theme.manager.changed.connect(self._box.update)

    def _paint_box(self, _):
        p = QPainter(self._box)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor(self._tone, 0x1f))
        p.drawRoundedRect(QRectF(self._box.rect()), 6, 6)

    def set_value(self, value):
        self.value_label.setText(str(value))

    def set_alarm(self, on):
        super().set_alarm(on)
        flag = "true" if on else "false"
        if self.value_label.property("alarm") != flag:
            self.value_label.setProperty("alarm", flag)
            repolish(self.value_label)


class CamTab(QFrame):
    """Viên chọn camera (.camtabs button): chấm trạng thái + tên + badge số cảnh báo."""

    clicked = Signal(str)

    def __init__(self, cam_id, text, icon=None, parent=None):
        super().__init__(parent)
        self.cam_id, self._on = cam_id, False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 7, 14, 7)
        lay.setSpacing(8)
        self.dot = None
        if icon:
            lay.addWidget(IconLabel(icon, 15, "text"))
        else:
            self.dot = Dot()
            lay.addWidget(self.dot)
        self.label = QLabel(text)
        lay.addWidget(self.label)
        self.badge = Chip("0", "badge")
        self.badge.hide()
        lay.addWidget(self.badge)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        theme.manager.changed.connect(self.update)

    def set_on(self, on):
        self._on = on
        self.update()

    def set_warning(self, n):
        self.badge.setVisible(n > 0)
        self.badge.set_text(str(n))

    def mousePressEvent(self, e):
        self.clicked.emit(self.cam_id)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._on:
            p.setPen(QPen(theme.qcolor("accent"), 1))
            p.setBrush(theme.accent_soft())
        else:
            p.setPen(QPen(theme.qcolor("border"), 1))
            p.setBrush(theme.qcolor("surface"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)


class _Framed(QFrame):
    """Khung video bo góc: viền mảnh, hoặc viền đỏ có quầng sáng khi camera đang cảnh báo (.stage.alarm / .tile.alarm)."""

    MARGIN = 3

    def __init__(self, radius=8, parent=None):
        super().__init__(parent)
        self._radius, self._alarm, self._phase = radius, False, False
        self._glow = QTimer(self)
        self._glow.setInterval(800)
        self._glow.timeout.connect(self._toggle_glow)
        self.surface = VideoSurface(STAGE_BG, radius=radius - 3, parent=self)
        theme.manager.changed.connect(self.update)

    def set_alarm(self, on):
        if on != self._alarm:
            self._alarm = on
            if on:
                self._glow.start()
            else:
                self._glow.stop()
                self._phase = False
            self.update()

    def _toggle_glow(self):
        self._phase = not self._phase
        self.update()

    def layout_children(self):
        m = self.MARGIN
        self.surface.setGeometry(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.layout_children()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(Qt.GlobalColor.black)
        p.drawRoundedRect(r, self._radius, self._radius)
        if self._alarm:
            ring = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            p.setPen(QPen(theme.qcolor("bad", 0x22 if self._phase else 0x55), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(ring, self._radius - 1, self._radius - 1)
            p.setPen(QPen(theme.qcolor("bad"), 1))
        else:
            p.setPen(QPen(theme.qcolor("border"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, self._radius, self._radius)


class Stage(_Framed):
    """Sân khấu xem 1 camera: video + overlay (LIVE, tên, số người, FPS, nút) + bảng chỉnh hình."""

    flip_clicked = Signal()
    fullscreen_clicked = Signal()
    panel_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(16, parent)
        self.setMinimumHeight(320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.tl = QWidget(self)
        tl = QHBoxLayout(self.tl)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(8)
        tl.addWidget(Chip("LIVE", "live", dot=True))
        self.src_chip = Chip("-", "overlay")
        tl.addWidget(self.src_chip)

        self.tr = QWidget(self)
        tr = QHBoxLayout(self.tr)
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(8)
        self.people_chip = Chip("0", "overlay", icon="users", icon_size=14)
        self.people_chip.setToolTip("Số học sinh trong khung hình")
        self.fps_chip = Chip("0 FPS", "overlay")
        self.flip_btn = Button(icon="flip", variant="overlay")
        self.flip_btn.setToolTip("Lật ngang hình (khi hình bị ngược trái-phải)")
        self.view_btn = Button(icon="sliders", variant="overlay")
        self.view_btn.setToolTip("Chỉnh hình: xoay, lật, độ sáng, phóng to")
        self.full_btn = Button(icon="max", variant="overlay")
        self.full_btn.setToolTip("Toàn màn hình (chiếu lên máy chiếu)")
        for w in (self.people_chip, self.fps_chip, self.flip_btn, self.view_btn, self.full_btn):
            tr.addWidget(w)
        self.flip_btn.clicked.connect(self.flip_clicked)
        self.view_btn.clicked.connect(self._toggle_panel)
        self.full_btn.clicked.connect(self.fullscreen_clicked)

        self.panel = ViewPanel(self)
        self.panel.hide()
        self.panel.changed.connect(self.panel_changed)

    def _toggle_panel(self):
        self.panel.setVisible(not self.panel.isVisible())
        self.panel.adjustSize()
        self.layout_children()

    def layout_children(self):
        super().layout_children()
        self.tl.layout().activate()
        self.tl.adjustSize()
        self.tl.move(17, 17)
        self.tr.layout().activate()
        self.tr.adjustSize()
        self.tr.move(self.width() - self.tr.width() - 17, 17)
        self.panel.move(self.width() - self.panel.width() - 14, 58)
        self.tl.raise_()
        self.tr.raise_()
        self.panel.raise_()

    def update_status(self, name, people, fps, view, alarm):
        for chip, text in ((self.src_chip, name), (self.people_chip, str(people)), (self.fps_chip, f"{fps} FPS")):
            chip.set_text(text)
            chip.adjustSize()
        self.flip_btn.set_on(view["flip_h"])
        self.view_btn.set_on(bool(view["rotate"] or view["flip_v"] or view["brightness"] or view["zoom"] > 1))
        self.set_alarm(alarm)
        self.layout_children()


class CameraTile(_Framed):
    """Ô xem nhỏ 16:9 trong lưới nhiều camera (.tile): bấm để chọn camera."""

    clicked = Signal(str)

    def __init__(self, cam_id, name, parent=None):
        super().__init__(16, parent)
        self.cam_id = cam_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.surface.clicked.connect(lambda: self.clicked.emit(self.cam_id))
        self.tl = QWidget(self)
        tl = QHBoxLayout(self.tl)
        tl.setContentsMargins(0, 0, 0, 0)
        self.name_chip = Chip(name, "overlay", dot=True, compact=True)
        tl.addWidget(self.name_chip)
        self.tr = QWidget(self)
        tr = QHBoxLayout(self.tr)
        tr.setContentsMargins(0, 0, 0, 0)
        self.info_chip = Chip("-", "overlay", compact=True)
        tr.addWidget(self.info_chip)

    def layout_children(self):
        super().layout_children()
        self.tl.layout().activate()
        self.tl.adjustSize()
        self.tl.move(13, 13)
        self.tr.layout().activate()
        self.tr.adjustSize()
        self.tr.move(self.width() - self.tr.width() - 13, 13)
        self.tl.raise_()
        self.tr.raise_()

    def update_status(self, name, state_dot, info, alarm):
        self.name_chip.dot.set_state(state_dot)
        for chip, text in ((self.name_chip, name), (self.info_chip, info)):
            chip.set_text(text)
            chip.adjustSize()
        self.set_alarm(alarm)
        self.layout_children()


class TileGrid(QWidget):
    """Lưới ô camera tự dàn cột (>= 340px/ô, khoảng cách 14px), ô tỉ lệ 16:9."""

    MIN_W, GAP = 340, 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tiles = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

    def sizeHint(self):
        return QSize(self.MIN_W, 200)

    def set_cameras(self, cams, on_click):
        for t in self.tiles.values():
            t.setParent(None)
            t.deleteLater()
        self.tiles = {}
        for c in cams:
            tile = CameraTile(c.id, c.name, self)
            tile.clicked.connect(on_click)
            tile.show()
            self.tiles[c.id] = tile
        self.relayout()

    def relayout(self):
        n = len(self.tiles)
        if not n:
            return
        w = max(self.width(), self.MIN_W)
        cols = max(1, min(n, (w + self.GAP) // (self.MIN_W + self.GAP)))
        tw = (w - self.GAP * (cols - 1)) / cols
        th = tw * 9 / 16
        for i, tile in enumerate(self.tiles.values()):
            r, c = divmod(i, cols)
            tile.setGeometry(int(c * (tw + self.GAP)), int(r * (th + self.GAP)), int(tw), int(th))
        rows = (n + cols - 1) // cols
        self.setMinimumHeight(int(rows * th + (rows - 1) * self.GAP))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()


class FullscreenWindow(QWidget):
    """Cửa sổ video toàn màn hình (chiếu máy chiếu). Esc hoặc bấm để thoát."""

    closed = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Giám sát lớp học AI")
        self.setStyleSheet("background:#000;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.surface = VideoSurface("#000000")
        self.surface.clicked.connect(self.close)
        lay.addWidget(self.surface)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)
