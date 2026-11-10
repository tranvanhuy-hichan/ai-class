"""Phóng to ảnh chụp lúc cảnh báo (#imgModal): ảnh bo 12 trên nền phủ mờ, bấm bất kỳ đâu hoặc Esc để đóng."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from lophocai.desktop import theme

from .common import OverlayDialog


class _RoundedImage(QWidget):
    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._pix = pixmap
        self.setFixedSize(int(pixmap.width() / pixmap.devicePixelRatio()),
                          int(pixmap.height() / pixmap.devicePixelRatio()))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 6, 6)
        p.setClipPath(path)
        p.drawPixmap(self.rect(), self._pix)


class ImageDialog(OverlayDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent, with_box=False)
        self.setWindowTitle("Ảnh chụp lúc cảnh báo")
        pix = QPixmap(str(path)) if path else QPixmap()
        if pix.isNull():
            from lophocai.desktop.ui import make_label
            lab = make_label("Không mở được ảnh", "muted")
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.root_layout.addWidget(lab, 1)
            return
        avail_w, avail_h = self.size().width(), self.size().height()
        max_w, max_h = int(avail_w * 0.94), int(avail_h * 0.88)
        scaled = pix.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.root_layout.addWidget(_RoundedImage(scaled), 0, Qt.AlignmentFlag.AlignCenter)

    def mousePressEvent(self, e):
        self.reject()
