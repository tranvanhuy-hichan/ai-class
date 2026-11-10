"""Thông báo nổi đỏ giữa-trên cửa sổ, tự ẩn sau 4 giây (.toast của web/index.html).

  show_toast("Có học sinh nằm gục xuống bàn")   gọi được từ mọi trang
"""
from PySide6.QtCore import QPropertyAnimation, QRectF, QTimer, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel

from . import theme
from .icons import IconLabel

LIFETIME_MS = 4000
_instance = None


class Toast(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 18, 12)
        lay.setSpacing(10)
        lay.addWidget(IconLabel("alert", 18, "#ffffff"))
        self.label = QLabel("")
        self.label.setStyleSheet("color:#ffffff; font-weight:600; font-size:14px;")
        lay.addWidget(self.label)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(300)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide)
        self.hide()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("bad"))
        p.drawRoundedRect(QRectF(self.rect()), 6, 6)

    def show_text(self, text):
        parent = self.parentWidget()
        maxw = max(200, parent.width() - 32 - 76)
        fm = self.label.fontMetrics()
        self.label.setText(fm.elidedText(text, Qt.TextElideMode.ElideRight, maxw))
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2, 18)
        self.raise_()
        self.show()
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity() if self.isVisible() else 0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._timer.start(LIFETIME_MS)

    def reposition(self):
        if self.isVisible():
            self.move((self.parentWidget().width() - self.width()) // 2, 18)

    def _hide(self):
        self._fade.stop()
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._after_fade)
        self._fade.start()

    def _after_fade(self):
        try:
            self._fade.finished.disconnect(self._after_fade)
        except (RuntimeError, TypeError):
            pass
        if self._effect.opacity() <= 0.01:
            self.hide()


def install(parent):
    global _instance
    _instance = Toast(parent)
    return _instance


def show_toast(text):
    if _instance is not None:
        _instance.show_text(text)
