"""Bảng dạng lưới widget (giống <table> của web) và chú giải màu, dùng cho trang Thống kê/Lịch sử."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QBoxLayout, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget

from lophocai.desktop import theme
from lophocai.desktop.ui import Meter, make_label, separator


class GridTable(QWidget):
    """columns = [(tiêu đề, stretch, căn_phải, độ_rộng_cố_định|None)]. Hàng là list widget hoặc chuỗi."""

    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self._cols = columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(0)
        for i, (_, stretch, _r, fixed) in enumerate(columns):
            self._grid.setColumnStretch(i, 0 if fixed else stretch)
            if fixed:
                self._grid.setColumnMinimumWidth(i, fixed + 20)
        self._row_widgets = []
        self._build_header()

    def _wrap(self, w, right, margins=(10, 10, 10, 10)):
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(*margins)
        if isinstance(w, Meter):   # thanh phân bố dãn hết bề ngang ô
            lay.addWidget(w, 1, Qt.AlignmentFlag.AlignVCenter)
        else:
            lay.addWidget(w, 0, (Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft)
                          | Qt.AlignmentFlag.AlignVCenter)
        return box

    def _build_header(self):
        for i, (title, _s, right, _f) in enumerate(self._cols):
            lab = make_label(title.upper(), "th")
            lab.setStyleSheet("letter-spacing:0.5px;")
            self._grid.addWidget(self._wrap(lab, right, (10, 8, 10, 8)), 0, i)

    def clear_rows(self):
        for w in self._row_widgets:
            self._grid.removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self._row_widgets = []

    def set_rows(self, rows, empty_text="Chưa có cảnh báo"):
        self.clear_rows()
        n = len(self._cols)
        r = 1
        if not rows:
            sep = separator()
            self._grid.addWidget(sep, r, 0, 1, n)
            lab = make_label(empty_text, "muted")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setContentsMargins(0, 30, 0, 30)
            self._grid.addWidget(lab, r + 1, 0, 1, n)
            self._row_widgets += [sep, lab]
            return
        for row in rows:
            sep = separator()
            self._grid.addWidget(sep, r, 0, 1, n)
            self._row_widgets.append(sep)
            for i, cell in enumerate(row):
                right = self._cols[i][2]
                if isinstance(cell, str):
                    cell = QLabel(cell)
                box = self._wrap(cell, right)
                self._grid.addWidget(box, r + 1, i)
                self._row_widgets.append(box)
            r += 2


class LegendItem(QWidget):
    """Ô vuông màu 10px + chữ (chú giải biểu đồ)."""

    def __init__(self, color, text, parent=None):
        super().__init__(parent)
        self._color = color
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 0, 0)   # 10px ô màu + 6px cách chữ
        lay.setSpacing(0)
        lab = make_label(text, "muted")
        lab.setStyleSheet("font-size:13px;")
        lay.addWidget(lab)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        from PySide6.QtGui import QColor
        p.setBrush(QColor(self._color))
        h = self.height()
        p.drawRoundedRect(QRectF(0, h / 2 - 5, 10, 10), 3, 3)


class WrapPair(QWidget):
    """Hai khối cạnh nhau, tự xếp dọc khi hẹp (flex-wrap của .donut-wrap)."""

    def __init__(self, first, second, threshold=380, parent=None):
        super().__init__(parent)
        self._threshold = threshold
        self._lay = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(24)
        self._lay.addWidget(first, 0, Qt.AlignmentFlag.AlignCenter)
        self._lay.addWidget(second, 1)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        d = (QBoxLayout.Direction.LeftToRight if self.width() >= self._threshold
             else QBoxLayout.Direction.TopToBottom)
        if self._lay.direction() != d:
            self._lay.setDirection(d)
