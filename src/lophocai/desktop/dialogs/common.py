"""Nền chung cho các hộp thoại: lớp phủ mờ phủ kín cửa sổ cha + hộp bo góc ở giữa (.modal / .box của web),
mã QR vẽ tay, và tác vụ chạy luồng nền (không treo giao diện)."""
import threading

from PySide6.QtCore import QObject, QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QDialog, QFrame, QLabel, QVBoxLayout, QWidget

from lophocai.desktop import theme
from lophocai.desktop.ui import make_label


class Box(QFrame):
    """Hộp hộp thoại: nền surface, viền mảnh, bo 20 (.modal .box)."""

    def __init__(self, parent=None, radius=10):
        super().__init__(parent)
        self._radius = radius
        theme.manager.changed.connect(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(theme.qcolor("border"))
        p.setBrush(theme.qcolor("surface"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self._radius, self._radius)


class OverlayDialog(QDialog):
    """Hộp thoại không viền phủ kín cửa sổ cha bằng nền mờ; bấm ra ngoài hộp (.box) thì đóng.
    Nội dung đặt vào self.box_layout (nếu with_box) hoặc self.root_layout."""

    def __init__(self, parent=None, backdrop=None, close_on_backdrop=True, with_box=True, box_width=None):
        super().__init__(parent)
        self.setObjectName("overlayDlg")
        self.setStyleSheet("QDialog#overlayDlg { background: transparent; }")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(True)
        self._backdrop = backdrop if backdrop is not None else QColor(0, 0, 0, 153)   # #0009
        self._close_on_backdrop = close_on_backdrop
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(16, 16, 16, 16)
        self.box = None
        self.box_layout = None
        if with_box:
            self.box = Box()
            if box_width:
                self.box.setFixedWidth(box_width)
            self.box_layout = QVBoxLayout(self.box)
            self.root_layout.addWidget(self.box, 0, Qt.AlignmentFlag.AlignCenter)
        self._cover_parent()

    def _cover_parent(self):
        par = self.parentWidget().window() if self.parentWidget() else None
        if par is not None:
            self.setGeometry(QRect(par.mapToGlobal(QPoint(0, 0)), par.size()))
        else:
            self.resize(1000, 700)

    def available_size(self):
        return self.size().width() - 32, self.size().height() - 32

    def showEvent(self, e):
        self._cover_parent()
        super().showEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), self._backdrop)

    def mousePressEvent(self, e):
        if self._close_on_backdrop and self._outside_content(e.position().toPoint()):
            self.reject()
            return
        super().mousePressEvent(e)

    def _outside_content(self, pos):
        if self.box is not None:
            return not self.box.geometry().contains(pos)
        return True


class QrWidget(QWidget):
    """Mã QR vẽ tay trên nền trắng bo 10 (.qr: nền trắng, đệm 8)."""

    def __init__(self, url="", size=220, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._matrix = None
        self.set_url(url)

    def set_url(self, url):
        self._matrix = None
        if url:
            try:
                import qrcode
                qr = qrcode.QRCode(border=0, box_size=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
                qr.add_data(url)
                qr.make(fit=True)
                self._matrix = qr.get_matrix()
            except Exception:
                self._matrix = None
        self.update()

    def has_qr(self):
        return self._matrix is not None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 5, 5)
        p.fillPath(path, QColor("#ffffff"))
        m = self._matrix
        if not m:
            p.setPen(QColor("#98a2b3"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Không tạo được mã QR")
            return
        n = len(m)
        area = self.width() - 16
        cell = area / n
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#000000"))
        for y, row in enumerate(m):
            for x, v in enumerate(row):
                if v:
                    p.drawRect(QRectF(8 + x * cell, 8 + y * cell, cell + 0.4, cell + 0.4))


class BgTask(QObject):
    """Chạy fn() ở luồng nền, báo kết quả (result, error) về luồng giao diện qua tín hiệu done."""

    done = Signal(object, object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            result, error = self._fn(), None
        except Exception as e:   # noqa: BLE001 - báo mọi lỗi lên giao diện
            result, error = None, e
        try:
            self.done.emit(result, error)
        except RuntimeError:
            pass   # hộp thoại đã đóng


def field_label(title, small=None, parent=None):
    """Nhãn trường nhập: dòng chữ thường + dòng nhỏ mờ bên dưới (label > small của web)."""
    w = QWidget(parent)
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    t = QLabel(title)
    lay.addWidget(t)
    if small:
        s = make_label(small, "small")
        s.setWordWrap(True)
        lay.addWidget(s)
    w.title_label = t
    return w


def icon_ghost(icon, tooltip=""):
    """Nút chỉ có icon, nền trong suốt, vuông (button.ghost.icon của web)."""
    from lophocai.desktop.ui import Button
    b = Button(icon=icon, variant="ghost")
    b._pad = lambda: (8, 8)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def hw_text(h):
    """Mô tả phần cứng một dòng (hwText trong index.html)."""
    cpu = h["cpu"].replace("(R)", "").replace("(TM)", "").replace("CPU ", "").strip()
    gpu = (" · " + h["gpu"].replace("NVIDIA GeForce ", "") + f" {h['vram_gb']} GB") if h["gpu"] \
        else " · không có card đồ họa rời"
    return f"{cpu} ({h['cores']} luồng) · {h['ram_gb']} GB RAM{gpu}"
