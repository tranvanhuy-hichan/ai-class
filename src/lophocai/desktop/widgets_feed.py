"""Cột phải trang Trực tiếp: thẻ "Mức độ tập trung" (.focus-card) và "Cảnh báo gần đây" (.feed-card)."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import theme
from .icons import IconLabel
from .ui import (BarChart, Card, Chip, EmptyState, FocusRing, Tag, ThumbLabel, card_header, clear_layout,
                 focus_color, make_label, snapshot_path)

FOCUS_TIP = ("Chỉ số tham khảo: mỗi học sinh được chấm 100% khi bình thường, 50% khi có dấu hiệu chưa đủ lâu để "
             "cảnh báo, 0% khi đang bị cảnh báo. Điểm của lớp là trung bình các bạn nhìn thấy. Nhiều camera thì "
             "tính trung bình theo số học sinh.")
RANGES = [("30 phút", 30), ("1 giờ", 60), ("3 giờ", 180), ("8 giờ", 480), ("Cả ngày", 1440)]


class InfoDot(QWidget):
    """Dấu ⓘ nhỏ có tooltip (.info)."""

    def __init__(self, tip, parent=None):
        super().__init__(parent)
        self.setFixedSize(18, 18)
        self.setToolTip(tip)
        self.setCursor(Qt.CursorShape.WhatsThisCursor)
        theme.manager.changed.connect(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme.qcolor("border"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(0.5, 0.5, 17, 17))
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(11)
        f.setWeight(QFont.Weight.Bold)
        p.setFont(f)
        p.setPen(theme.qcolor("muted"))
        p.drawText(QRectF(0, 0, 18, 18), Qt.AlignmentFlag.AlignCenter, "i")


class FocusCard(Card):
    range_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(18, 16, 18, 0)
        head.setSpacing(10)
        head.addWidget(IconLabel("gauge", 18, "text"))
        head.addWidget(make_label("Mức độ tập trung", "h2"))
        head.addWidget(InfoDot(FOCUS_TIP))
        head.addStretch(1)
        self.range_box = QComboBox()
        self.range_box.setStyleSheet("padding: 4px 8px; font-size: 12.5px;")
        for label, minutes in RANGES:
            self.range_box.addItem(label, minutes)
        self.range_box.setCurrentIndex(1)
        self.range_box.currentIndexChanged.connect(lambda _: self.range_changed.emit())
        head.addWidget(self.range_box)
        lay.addLayout(head)

        body = QGridLayout()
        body.setContentsMargins(18, 10, 18, 18)
        body.setHorizontalSpacing(18)
        body.setVerticalSpacing(8)
        self.ring = FocusRing()
        body.addWidget(self.ring, 0, 0)
        stats = QVBoxLayout()
        stats.setSpacing(10)
        stats.addStretch(1)
        self.avg_value = self._stat_value()
        self.low_value = self._stat_value()
        self.low_caption = make_label("Thấp nhất", "small")
        stats.addWidget(self.avg_value)
        stats.addWidget(make_label("Trung bình", "small"))
        stats.addSpacing(0)
        stats.addWidget(self.low_value)
        stats.addWidget(self.low_caption)
        stats.addStretch(1)
        body.addLayout(stats, 0, 1)
        self.chart = BarChart(64, gap=1, min_bar=0, radius=2, top_round_only=True, top_pad=0, axis_font_px=11)
        body.addWidget(self.chart, 1, 0, 1, 2)
        body.setColumnStretch(1, 1)
        lay.addLayout(body)

    @staticmethod
    def _stat_value():
        lab = QLabel("–")
        lab.setStyleSheet("font-size:20px; font-weight:700;")
        return lab

    def range_minutes(self):
        return self.range_box.currentData()

    def set_now(self, v):
        self.ring.set_value(v)

    def set_summary(self, d):
        avg, low = d.get("avg"), d.get("low")
        self.avg_value.setText("–" if avg is None else f"{avg}%")
        self.low_value.setText("–" if not low else f"{round(low['score'])}%")
        self.low_caption.setText("Thấp nhất lúc " + low["label"] if low else "Thấp nhất")
        points = d.get("points", [])
        bars = []
        for p in points:
            if p["score"] is None:
                bars.append({"segments": [], "tip": f"{p['label']}: không có học sinh"})
            else:
                col = theme.c(focus_color(p["score"]))
                bars.append({"segments": [(col, max(p["score"], 3))],
                             "tip": f"{p['label']}: {round(p['score'])}% ({p['students']} học sinh)"})
        n = len(points)
        axis = [points[min(n - 1, round(f * (n - 1)))]["label"] for f in (0, .25, .5, .75, 1)] if n else []
        self.chart.set_data(bars, max_value=100, axis_labels=axis)


class EventItem(QFrame):
    """Một cảnh báo trong danh sách (.ev): ảnh nhỏ + nhãn hành vi + học sinh + giờ; viền trái màu hành vi."""

    def __init__(self, engine, ev, multi, image_cb, parent=None):
        super().__init__(parent)
        self._color = theme.behavior_color(ev["behavior"])
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(13, 10, 10, 10)
        lay.setSpacing(12)
        if ev.get("snapshot"):
            thumb = ThumbLabel(104, 64, 8)
            thumb.set_path(snapshot_path(engine, ev["snapshot"]))
            thumb.clicked.connect(image_cb)
            lay.addWidget(thumb, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(0)
        tag_row = QHBoxLayout()
        tag_row.addWidget(Tag(ev["behavior"], ev.get("name")))
        tag_row.addStretch(1)
        col.addLayout(tag_row)
        col.addSpacing(6)
        who = QLabel(f"Học sinh #{ev['student']} <span style='color:{theme.c('muted')}; font-size:12px; "
                     f"font-weight:400'>· {round(ev['duration'])} giây</span>")
        who.setTextFormat(Qt.TextFormat.RichText)
        who.setStyleSheet("font-weight:600;")
        col.addWidget(who)
        t = ev["time"]
        meta = (f"{ev['camera_name']} · " if multi and ev.get("camera_name") else "") + f"{t[11:]} · {t[8:10]}/{t[5:7]}"
        col.addWidget(make_label(meta, "small"))
        col.addStretch(1)
        lay.addLayout(col, 1)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.qcolor("border"), 1))
        p.setBrush(theme.qcolor("surface2"))
        p.drawRoundedRect(r, 6, 6)
        path = QPainterPath()
        path.addRoundedRect(r, 6, 6)
        p.setClipPath(path)
        p.fillRect(QRectF(0, 0, 3, self.height()), self._color)


class FeedCard(Card):
    """Danh sách cảnh báo gần đây, mới nhất ở trên, tối đa 100."""

    MAX = 100

    def __init__(self, engine, image_cb, parent=None):
        super().__init__(parent)
        self.engine, self.image_cb = engine, image_cb
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.count_chip = Chip("0")
        lay.addWidget(card_header("Cảnh báo gần đây", trailing=[self.count_chip]))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.host = QWidget()
        self.host.setObjectName("pageHost")
        self.list = QVBoxLayout(self.host)
        self.list.setContentsMargins(12, 12, 12, 14)
        self.list.setSpacing(8)
        self.scroll.setWidget(self.host)
        lay.addWidget(self.scroll, 1)
        self.empty = EmptyState("check", "Chưa có cảnh báo nào", "Lớp học đang trật tự")
        self._items = 0
        self._show_empty()

    def _show_empty(self):
        clear_layout(self.list)
        self._items = 0
        self.empty = EmptyState("check", "Chưa có cảnh báo nào", "Lớp học đang trật tự")
        self.list.addStretch(1)
        self.list.addWidget(self.empty)
        self.list.addStretch(1)

    def set_events(self, events, multi):
        """Dựng lại toàn bộ danh sách (events theo thứ tự cũ -> mới)."""
        self.count_chip.set_text(str(len(events)))
        if not events:
            self._show_empty()
            return
        clear_layout(self.list)
        for ev in reversed(events[-self.MAX:]):
            self.list.addWidget(EventItem(self.engine, ev, multi, self.image_cb))
        self.list.addStretch(1)
        self._items = min(len(events), self.MAX)

    def prepend(self, ev, multi, total):
        if self._items == 0:
            clear_layout(self.list)
            self.list.addStretch(1)
        self.list.insertWidget(0, EventItem(self.engine, ev, multi, self.image_cb))
        self._items += 1
        while self._items > self.MAX:
            w = self.list.itemAt(self.list.count() - 2).widget()
            self.list.removeWidget(w)
            w.deleteLater()
            self._items -= 1
        self.count_chip.set_text(str(total))
        self.scroll.verticalScrollBar().setValue(0)
