"""Bảng "Chỉnh hình" nổi trên video (.vpanel của web): lật, xoay, độ sáng, phóng to, đặt lại."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QSlider, QVBoxLayout

from .ui import Button, Chip

PANEL_TEXT = "#e8edf6"
PANEL_MUTED = "#8592a8"


class ViewPanel(QFrame):
    changed = Signal(dict)   # {khoá: giá trị} giống setView(patch) của web

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(290)
        self._view = {"flip_h": False, "flip_v": False, "rotate": 0, "brightness": 0, "zoom": 1.0}
        self._updating = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Chỉnh hình")
        title.setStyleSheet(f"color:{PANEL_TEXT}; font-weight:600; font-size:14px;")
        note = QLabel("nhớ riêng cho từng camera")
        note.setStyleSheet(f"color:{PANEL_MUTED}; font-size:11.5px;")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(note)
        lay.addLayout(head)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.flip_h_btn = Button("Lật ngang", "flip", "seg", icon_size=16, font_px=13)
        self.flip_v_btn = Button("Lật dọc", "flip", "seg", icon_size=16, font_px=13)
        for b in (self.flip_h_btn, self.flip_v_btn):
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row1.addWidget(b, 1)
        self.flip_h_btn.clicked.connect(lambda: self._emit({"flip_h": not self._view["flip_h"]}))
        self.flip_v_btn.clicked.connect(lambda: self._emit({"flip_v": not self._view["flip_v"]}))
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        left = Button("Xoay trái", "rotate", "seg", icon_size=16, font_px=13)
        right = Button("Xoay phải", "rotate", "seg", icon_size=16, font_px=13)
        for b in (left, right):
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        left.clicked.connect(lambda: self._emit({"rotate": (self._view["rotate"] + 270) % 360}))
        right.clicked.connect(lambda: self._emit({"rotate": (self._view["rotate"] + 90) % 360}))
        self.rot_chip = Chip("0°", "overlay", compact=True)
        row2.addWidget(left, 1)
        row2.addWidget(right, 1)
        row2.addWidget(self.rot_chip)
        lay.addLayout(row2)

        self.br_value = QLabel("0")
        self.br_slider = self._slider(-80, 80, 5)
        self.br_slider.valueChanged.connect(lambda v: self._emit({"brightness": v}))
        lay.addLayout(self._slider_block("Độ sáng", self.br_value, self.br_slider))

        self.zm_value = QLabel("1.0×")
        self.zm_slider = self._slider(10, 30, 1)   # 1.0x .. 3.0x, bước 0.1
        self.zm_slider.valueChanged.connect(lambda v: self._emit({"zoom": v / 10}))
        lay.addLayout(self._slider_block("Phóng to giữa khung", self.zm_value, self.zm_slider))

        reset = Button("Đặt lại", None, "ghost", font_px=13)
        reset.set_fg(PANEL_TEXT)
        reset.clicked.connect(lambda: self._emit({"flip_h": False, "flip_v": False, "rotate": 0,
                                                  "brightness": 0, "zoom": 1.0}))
        lay.addWidget(reset, 0, Qt.AlignmentFlag.AlignLeft)

    @staticmethod
    def _slider(lo, hi, step):
        s = QSlider(Qt.Orientation.Horizontal)
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setPageStep(step)
        s.setProperty("onDark", "true")
        return s

    @staticmethod
    def _slider_block(text, value_label, slider):
        box = QVBoxLayout()
        box.setSpacing(4)
        row = QHBoxLayout()
        name = QLabel(text)
        name.setStyleSheet(f"color:{PANEL_TEXT}; font-size:13px;")
        value_label.setStyleSheet(f"color:{PANEL_TEXT}; font-size:13px; font-weight:700;")
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(value_label)
        box.addLayout(row)
        box.addWidget(slider)
        return box

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 31), 1))
        p.setBrush(QColor(11, 15, 23, 230))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

    def _emit(self, patch):
        if self._updating:
            return
        self.changed.emit(patch)

    def set_view(self, view):
        """Cập nhật hiển thị theo giá trị thật của camera, không phát lại tín hiệu."""
        self._updating = True
        self._view = dict(view)
        self.flip_h_btn.set_on(view["flip_h"])
        self.flip_v_btn.set_on(view["flip_v"])
        self.rot_chip.set_text(f"{view['rotate']}°")
        if not self.br_slider.isSliderDown():
            self.br_slider.setValue(int(view["brightness"]))
        if not self.zm_slider.isSliderDown():
            self.zm_slider.setValue(round(float(view["zoom"]) * 10))
        b = int(view["brightness"])
        self.br_value.setText(("+" if b > 0 else "") + str(b))
        self.zm_value.setText(f"{float(view['zoom']):.1f}×")
        self._updating = False
