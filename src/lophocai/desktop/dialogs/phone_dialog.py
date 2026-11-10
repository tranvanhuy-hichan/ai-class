"""Hộp thoại QR cho camera điện thoại (#qrModal): "Điện thoại làm camera" + mã QR 220px + hướng dẫn + nút Đóng."""
from PySide6.QtCore import Qt

from lophocai.desktop.ui import Button, make_label

from .common import OverlayDialog, QrWidget

HINT = ("Điện thoại dùng <b>cùng Wi-Fi</b> với máy này quét mã, bấm <b>Bắt đầu</b>.<br>"
        "Trình duyệt báo “không an toàn” thì chọn <i>Nâng cao → Tiếp tục</i>.<br>"
        "Điện thoại chỉ gửi hình, không xem được gì. Mã đổi mỗi lần mở app.<br>"
        "Không kết nối được? Trên Windows, khi có hộp thoại tường lửa hãy chọn <b>Allow</b>.")


class PhoneQRDialog(OverlayDialog):
    def __init__(self, url, parent=None):
        super().__init__(parent, box_width=380)
        self.setWindowTitle("Điện thoại làm camera")
        lay = self.box_layout
        lay.setContentsMargins(26, 26, 26, 26)
        lay.setSpacing(0)

        title = make_label("Điện thoại làm camera")
        title.setStyleSheet("font-size:21px; font-weight:700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        lay.addSpacing(14)

        if url:
            self.qr = QrWidget(url, 220)
            lay.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)
            lay.addSpacing(14)
            hint = make_label(HINT, "hint", wrap=True, rich=True)
        else:
            hint = make_label("Chưa bật HTTPS nên chưa dùng được camera điện thoại.", "hint", wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size:12.5px;")
        lay.addWidget(hint)
        lay.addSpacing(14)

        close = Button("Đóng")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignHCenter)
