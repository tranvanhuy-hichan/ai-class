"""Chọn chế độ giám sát (#modeModal): lớp phủ gần đặc, tiêu đề giữa và các thẻ chế độ (Lớp học / Hành lang).
Hiện khi mở app lần đầu (không huỷ được) và khi bấm nút "Đổi chế độ" (có nút Hủy)."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from lophocai.desktop import theme
from lophocai.desktop.ui import Button, make_label

from .common import OverlayDialog


class ModeCard(QFrame):
    clicked = Signal()

    def __init__(self, name, desc, note="", highlight=False, parent=None):
        super().__init__(parent)
        self._highlight, self._hover = highlight, False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(240)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 22, 22, 22)
        lay.setSpacing(6)
        title = QLabel(name)
        title.setStyleSheet("font-size:20px; font-weight:700;")
        lay.addWidget(title)
        d = make_label(desc, "muted", wrap=True)
        d.setStyleSheet("font-size:13px;")
        self.desc = d
        lay.addWidget(d)
        if note:
            n = QLabel(note)
            n.setStyleSheet(f"font-size:12px; color:{theme.c('accent')};")
            lay.addSpacing(2)
            lay.addWidget(n)
        lay.addStretch(1)
        for child in self.findChildren(QLabel):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        theme.manager.changed.connect(self.update)

    def fit_text(self, text_width):
        """Chừa đủ chỗ cho mô tả xuống dòng (QLabel tự xuống dòng không báo chiều cao trong lưới)."""
        self.desc.setMinimumHeight(self.desc.heightForWidth(text_width))

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if self.rect().contains(e.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hot = self._highlight or self._hover
        if self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.qcolor("accent", 0x14))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0, 3, 0, 5), 8, 8)
        p.setPen(QPen(theme.qcolor("accent" if hot else "border"), 1))
        p.setBrush(theme.qcolor("surface"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)


class ModeDialog(OverlayDialog):
    def __init__(self, engine, allow_cancel, parent=None):
        super().__init__(parent, backdrop=theme.qcolor("bg", 235), close_on_backdrop=False, with_box=False)
        self.engine = engine
        self.chosen = None
        self._allow_cancel = allow_cancel
        self.setWindowTitle("Chọn chế độ giám sát")

        col = QWidget()
        col.setFixedWidth(min(720, max(300, self.size().width() - 32)))
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        title = make_label("Chọn chế độ giám sát")
        title.setStyleSheet("font-size:24px; font-weight:700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(6)
        sub = make_label("Chỉ chạy các mô hình cần cho nơi đặt camera, nên nhẹ và nhanh hơn.", "muted")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(sub)
        lay.addSpacing(22)

        info = engine.modes_info()
        cur, last = info.get("mode"), info.get("last")
        cards = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        for i, m in enumerate(info["modes"]):
            note = "Đang chạy" if m["id"] == cur else "Lần trước bạn chọn" if m["id"] == last else ""
            card = ModeCard(m["ten"], m.get("mo_ta", ""), note, highlight=(m["id"] == (cur or last)))
            card.clicked.connect(lambda mid=m["id"]: self._choose(mid))
            grid.addWidget(card, i // 2, i % 2)
            grid.setColumnStretch(i % 2, 1)
            cards.append(card)
        lay.addLayout(grid)
        cols = 2 if len(cards) > 1 else 1
        text_w = (col.width() - 14 * (cols - 1)) // cols - 44
        for c in cards:
            c.fit_text(text_w)
        tallest = max((c.sizeHint().height() for c in cards), default=0)
        for c in cards:
            c.setMinimumHeight(tallest)

        if allow_cancel:
            lay.addSpacing(18)
            cancel = Button("Hủy", variant="ghost")
            cancel.clicked.connect(self.reject)
            lay.addWidget(cancel, 0, Qt.AlignmentFlag.AlignHCenter)
        self.root_layout.addStretch(1)
        self.root_layout.addWidget(col, 0, Qt.AlignmentFlag.AlignHCenter)
        self.root_layout.addStretch(1)

    def _choose(self, mode_id):
        self.chosen = mode_id
        self.accept()

    def reject(self):
        if self._allow_cancel:
            super().reject()
