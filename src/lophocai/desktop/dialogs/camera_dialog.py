"""Hộp thoại thêm / sửa camera (#camModal): 4 loại nguồn (Webcam / USB, Điện thoại, Camera IP, Video).

cam=None: thêm mới (hoặc "Đổi camera" khi đang ở chế độ 1 camera và đã có camera).
cam=Camera: chỉnh sửa (ẩn phần chọn loại), có nút Xoá camera.
Việc chậm (dò webcam, thử kết nối, chép video, khởi chạy/dừng camera) chạy ở luồng nền.
"""
import shutil
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from lophocai.application.hardware import hardware, recommended_cameras
from lophocai.desktop import theme, toast
from lophocai.desktop.icons import icon_pixmap
from lophocai.desktop.ui import Button, Notice, Switch, make_label, repolish, separator
from lophocai.domain.models import mask_source, source_kind
from lophocai.video.sources import VideoSource
from lophocai.video.devices import list_cameras

from .common import BgTask, OverlayDialog, QrWidget, field_label, hw_text, icon_ghost

TYPES = [("webcam", "video", "Webcam / USB"), ("phone", "phone", "Điện thoại"),
         ("ip", "link", "Camera IP"), ("file", "upload", "Video")]
BOX_WIDTH = 560

PHONE_HINT = ("Dùng điện thoại <b>cùng Wi-Fi</b> quét mã rồi bấm <b>Bắt đầu</b>. Không cần cài app.<br>"
              "Trình duyệt báo “không an toàn” thì chọn <i>Nâng cao → Tiếp tục</i>, vì đây là chứng chỉ tự tạo "
              "trong mạng nội bộ.<br>")


class TypeButton(QAbstractButton):
    """Nút chọn loại nguồn: icon ở trên, chữ ở dưới (.mtypes button)."""

    def __init__(self, icon, text, parent=None):
        super().__init__(parent)
        self._icon = icon
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        theme.manager.changed.connect(self.update)

    def sizeHint(self):
        return QSize(80, 72)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        on = self.isChecked()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(theme.qcolor("accent" if on else "border"), 1))
        p.setBrush(theme.accent_soft() if on else theme.qcolor("surface3" if self._hover and self.isEnabled() else "surface2"))
        p.drawRoundedRect(r, 5, 5)
        p.drawPixmap(int((self.width() - 18) / 2), 12, icon_pixmap(self._icon, 18, "text"))
        f = QFont(theme.FONT_FAMILY)
        f.setPixelSize(12)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(theme.qcolor("text"))
        p.drawText(QRectF(0, 36, self.width(), 24), Qt.AlignmentFlag.AlignCenter, self.text())


class Collapsible(QWidget):
    """<details class="hint"><summary>…</summary>…</details>."""

    def __init__(self, title, html, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._title = title
        self.head = QLabel()
        self.head.setCursor(Qt.CursorShape.PointingHandCursor)
        self.head.setStyleSheet(f"color:{theme.c('accent')}; font-size:13px;")
        self.head.mousePressEvent = lambda e: self.set_open(not self.body.isVisible())
        self.body = make_label(html, "hint", wrap=True, rich=True)
        self.body.setStyleSheet("font-size:12.5px;")
        lay.addWidget(self.head)
        lay.addWidget(self.body)
        self.set_open(False)

    def set_open(self, on):
        self.body.setVisible(on)
        self.head.setText(("▾ " if on else "▸ ") + self._title)
        w = self.window()
        if hasattr(w, "refit"):
            QTimer.singleShot(0, w.refit)


def _code(text):
    return (f'<span style="background-color:{theme.c("surface3")}; font-family:monospace; '
            f'font-size:12px;">&nbsp;{text}&nbsp;</span>')


def _samples_html():
    return ("App <b>IP Webcam</b> (Android): " + _code("http://IP:8080/video") + "<br>"
            "App <b>DroidCam</b>: " + _code("http://IP:4747/video") + "<br>"
            "<b>Hikvision</b>: " + _code("rtsp://admin:matkhau@IP:554/Streaming/Channels/101") + "<br>"
            "<b>Dahua / KBVision</b>: " + _code("rtsp://admin:matkhau@IP:554/cam/realmonitor?channel=1&amp;subtype=0") + "<br>"
            "<b>Imou / Ezviz</b>: bật RTSP trong app, mật khẩu là mã xác minh in dưới camera.")


class CameraDialog(OverlayDialog):
    def __init__(self, engine, cam=None, parent=None, phone_url=""):
        super().__init__(parent, box_width=BOX_WIDTH)
        self.engine, self.cam, self.phone_url = engine, cam, phone_url
        self._cams = list(engine.cameras.values())
        self.swap = cam is None and bool(self._cams) and not engine.multi()
        self._type = "webcam"
        self._tasks = []
        self.setWindowTitle("Chỉnh sửa camera" if cam else "Thêm camera")
        self._max_h = int(self.size().height() * 0.92)
        self.box.setFixedWidth(min(BOX_WIDTH, max(320, self.size().width() - 32)))
        self._build()
        if cam is None:
            self._setup_add()
        else:
            self._setup_edit()
        QTimer.singleShot(0, self.refit)

    # ------------------------------------------------------------ dựng giao diện
    def _build(self):
        lay = self.box_layout
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(22, 18, 22, 8)
        self.title = make_label("", "h3")
        head.addWidget(self.title, 1)
        close = icon_ghost("x", "Đóng")
        close.clicked.connect(self.reject)
        head.addWidget(close)
        self.head_w = QWidget()
        self.head_w.setLayout(head)
        lay.addWidget(self.head_w)

        self.types_w = QWidget()
        tl = QGridLayout(self.types_w)
        tl.setContentsMargins(22, 8, 22, 8)
        tl.setHorizontalSpacing(8)
        self.type_btns = {}
        for i, (key, icon, label) in enumerate(TYPES):
            b = TypeButton(icon, label)
            b.clicked.connect(lambda _=False, k=key: self.set_type(k))
            tl.addWidget(b, 0, i)
            self.type_btns[key] = b
        lay.addWidget(self.types_w)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("pageHost")
        self.body_l = QVBoxLayout(self.body)
        self.body_l.setContentsMargins(22, 8, 22, 12)
        self.body_l.setSpacing(0)
        self.scroll.setWidget(self.body)
        lay.addWidget(self.scroll)

        # cảnh báo vượt khuyến nghị phần cứng
        self.warn_wrap = QWidget()
        wl = QVBoxLayout(self.warn_wrap)
        wl.setContentsMargins(0, 0, 0, 16)
        self.warn = Notice("", "warn", "alert")
        wl.addWidget(self.warn)
        self.body_l.addWidget(self.warn_wrap)

        # tên camera
        self.name_edit = QLineEdit()
        self.name_edit.setMaxLength(60)
        self.body_l.addWidget(self._field_col(field_label("Tên camera", "Ví dụ: Lớp 10A1, Hành lang tầng 2"), self.name_edit))

        # tự chạy
        self.enabled_row = QWidget()
        er = QVBoxLayout(self.enabled_row)
        er.setContentsMargins(0, 0, 0, 0)
        er.setSpacing(0)
        er.addWidget(separator())
        row = QHBoxLayout()
        row.setContentsMargins(0, 10, 0, 10)
        row.addWidget(field_label("Tự chạy khi mở app", "Camera này khởi động cùng ứng dụng"), 1)
        self.enabled_sw = Switch(True)
        row.addWidget(self.enabled_sw)
        er.addLayout(row)
        self.body_l.addWidget(self.enabled_row)

        # từng loại nguồn
        self.type_w = {}
        self.webcam_combo = QComboBox()
        self.type_w["webcam"] = self._field_col(
            field_label("Chọn webcam", "Camera laptop hoặc camera cắm cổng USB"), self.webcam_combo)

        phone = QWidget()
        pl = QHBoxLayout(phone)
        pl.setContentsMargins(0, 10, 0, 10)
        pl.setSpacing(14)
        self.phone_qr = QrWidget(self.phone_url, 132)
        pl.addWidget(self.phone_qr, 0, Qt.AlignmentFlag.AlignTop)
        self.phone_hint = make_label(PHONE_HINT, "hint", wrap=True, rich=True)
        self.phone_hint.setStyleSheet("font-size:12.5px;")
        pl.addWidget(self.phone_hint, 1)
        self.type_w["phone"] = phone

        self.url_label = field_label("Địa chỉ camera")
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("rtsp://admin:matkhau@192.168.1.64:554/...")
        ip = QWidget()
        il = QVBoxLayout(ip)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)
        il.addWidget(self._field_col(self.url_label, self.url_edit))
        il.addWidget(Collapsible("Địa chỉ mẫu theo hãng", _samples_html()))
        self.type_w["ip"] = ip

        self.file_path = ""
        self.file_name = make_label("Chưa chọn file", "muted")
        pick = Button("Chọn file video...", "upload")
        pick.clicked.connect(self._pick_file)
        frow = QHBoxLayout()
        frow.setSpacing(10)
        frow.addWidget(pick)
        frow.addWidget(self.file_name, 1)
        fw = QWidget()
        fw.setLayout(frow)
        frow.setContentsMargins(0, 0, 0, 0)
        self.type_w["file"] = self._field_col(
            field_label("Chọn file video", "Dùng để demo, video tự phát lặp lại"), fw)
        for w in self.type_w.values():
            self.body_l.addWidget(w)
            w.hide()

        self.msg = QLabel("")
        self.msg.setWordWrap(True)
        self.msg.setMinimumHeight(18)
        self.body_l.addSpacing(8)
        self.body_l.addWidget(self.msg)
        self.body_l.addStretch(1)

        lay.addWidget(separator())
        foot = QHBoxLayout()
        foot.setContentsMargins(22, 14, 22, 18)
        foot.setSpacing(8)
        self.delete_btn = Button("Xoá camera", "trash", "danger")
        self.delete_btn.clicked.connect(self._delete)
        foot.addWidget(self.delete_btn)
        foot.addStretch(1)
        self.test_btn = Button("Thử kết nối", "check")
        self.test_btn.clicked.connect(self._test)
        foot.addWidget(self.test_btn)
        self.save_btn = Button("Thêm & chạy", None, "primary")
        self.save_btn.clicked.connect(self._save)
        foot.addWidget(self.save_btn)
        self.foot_w = QWidget()
        self.foot_w.setLayout(foot)
        lay.addWidget(self.foot_w)

    @staticmethod
    def _field_col(label_w, input_w):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(6)
        lay.addWidget(label_w)
        lay.addWidget(input_w)
        return w

    # ------------------------------------------------------------ chế độ thêm / sửa
    def _running_count(self):
        return sum(1 for c in self._cams if c.state in ("running", "starting"))

    def _setup_add(self):
        n = len(self._cams)
        self.title.setText("Đổi camera" if self.swap else "Thêm camera")
        self.save_btn.setText("Đổi & chạy" if self.swap else "Thêm & chạy")
        self.delete_btn.hide()
        self.types_w.show()
        self.name_edit.setPlaceholderText("Camera 1")
        self.name_edit.setText(self._cams[0].name if self.swap else f"Camera {n + 1}")
        self.enabled_row.setVisible(not self.swap)
        self.enabled_sw.setChecked(True)

        has_phone = (not self.swap) and any(c.source == "phone" for c in self._cams)
        phone_btn = self.type_btns["phone"]
        phone_btn.setEnabled(not has_phone and bool(self.phone_url))
        self.phone_hint.setText(PHONE_HINT + ("<b>Đã có một camera điện thoại.</b> Chỉ dùng được một điện thoại "
                                              "cùng lúc." if has_phone else ""))

        hw = hardware()
        rec = recommended_cameras(hw, self.engine.has_gpu())
        over = (not self.swap) and self._running_count() + 1 > rec
        self.warn_wrap.setVisible(over)
        if over:
            self.warn.set_html(f"<b>Máy này chỉ nên chạy tối đa {rec} camera cùng lúc</b> ({hw_text(hw)}). Thêm camera "
                               "nữa có thể làm hệ thống chậm và giật hình. Bạn vẫn có thể thêm rồi để camera ở "
                               "trạng thái dừng.")

        self.webcam_combo.addItem("Đang dò webcam...")
        self.webcam_combo.setEnabled(False)
        task = BgTask(lambda: list_cameras(self.engine), self)
        task.done.connect(self._on_webcams)
        self._tasks.append(task)
        task.start()
        self.set_type("webcam")

    def _on_webcams(self, result, error):
        listing = list(result) if result else [0]
        self.webcam_combo.clear()
        first = -1
        for i in listing:
            used = (not self.swap) and any(c.source == str(i) and c.state in ("running", "starting") for c in self._cams)
            self.webcam_combo.addItem(f"Webcam {i}" + (" (đang dùng)" if used else ""), str(i))
            idx = self.webcam_combo.count() - 1
            if used:
                self.webcam_combo.model().item(idx).setEnabled(False)
            elif first < 0:
                first = idx
        self.webcam_combo.setEnabled(True)
        self.webcam_combo.setCurrentIndex(max(first, 0))

    def _setup_edit(self):
        c = self.cam
        self.title.setText("Chỉnh sửa camera")
        self.save_btn.setText("Lưu")
        self.types_w.hide()
        self.warn_wrap.hide()
        self.delete_btn.show()
        self.name_edit.setText(c.name)
        self.enabled_sw.setChecked(c.enabled)
        self.enabled_row.show()
        kind = source_kind(c.source)
        for w in self.type_w.values():
            w.hide()
        if kind != "phone":
            self.type_w["ip"].show()
            self.url_edit.setText(mask_source(c.source))
            self.url_edit.setCursorPosition(0)
        self.url_label.title_label.setText({"webcam": "Số thứ tự webcam", "file": "Đường dẫn file video"}.get(kind, "Địa chỉ camera"))
        self.test_btn.setVisible(kind not in ("phone", "file"))
        self._type = "edit"

    def set_type(self, t):
        self._type = t
        for k, b in self.type_btns.items():
            b.setChecked(k == t)
        for k, w in self.type_w.items():
            w.setVisible(k == t)
        self.test_btn.setVisible(t not in ("phone", "file"))
        self._set_msg("")
        QTimer.singleShot(0, self.refit)

    def refit(self):
        """Co giãn vùng nội dung vừa đủ (tối đa 92% chiều cao cửa sổ), dư thì cuộn."""
        w = self.box.width()
        lay = self.body_l
        self.body.setFixedWidth(w - 2)
        h = lay.totalHeightForWidth(w - 2) if lay.hasHeightForWidth() else lay.sizeHint().height()
        others = (self.head_w.sizeHint().height() + (self.types_w.sizeHint().height() if self.types_w.isVisible() else 0)
                  + self.foot_w.sizeHint().height() + 2)
        self.scroll.setFixedHeight(max(60, min(h + 2, self._max_h - others)))
        self.body.setMinimumWidth(0)
        self.body.setMaximumWidth(16777215)
        self.box.adjustSize()

    # ------------------------------------------------------------ thông báo ngắn trong hộp
    def _set_msg(self, text, ok=False):
        self.msg.setText(text)
        self.msg.setProperty("role", ("ok" if ok else "err") if text else "")
        repolish(self.msg)

    def _busy(self, on):
        for b in (self.test_btn, self.save_btn, self.delete_btn):
            b.setEnabled(not on)

    def _run(self, fn, done):
        task = BgTask(fn, self)
        task.done.connect(done)
        self._tasks.append(task)
        task.start()

    # ------------------------------------------------------------ chọn file
    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file video", "",
                                              "Video (*.mp4 *.avi *.mov *.mkv *.webm *.m4v);;Tất cả (*)")
        if path:
            self.file_path = path
            fm = QFontMetrics(self.file_name.font())
            self.file_name.setText(fm.elidedText(Path(path).name, Qt.TextElideMode.ElideMiddle, 260))

    # ------------------------------------------------------------ nguồn đang chọn
    def _source(self):
        t = self._type
        if t == "webcam":
            return self.webcam_combo.currentData() or ""
        if t == "phone":
            return "phone"
        if t == "edit":
            text = self.url_edit.text().strip()
            if self.cam is not None and text == mask_source(self.cam.source):
                return self.cam.source
            return text
        return self.url_edit.text().strip()

    # ------------------------------------------------------------ thử kết nối
    def _test(self):
        source = self._source()
        if not source:
            self._set_msg("Hãy nhập nguồn camera")
            return
        self._set_msg("Đang thử kết nối (tối đa vài giây)...", True)
        self._busy(True)
        engine = self.engine

        def work():
            if source == "phone":
                raise ValueError("Chưa nhập nguồn camera")
            for c in engine.cameras.values():
                if c.running and c.source == source:
                    return f"Đang chạy trong camera “{c.name}”"
            src = VideoSource(source)
            frame = src.read(timeout=8.0) if src.live else src.read()
            h, w = (frame.shape[:2] if frame is not None else (0, 0))
            src.release()
            if frame is None:
                raise ValueError("Mở được nhưng không nhận được hình. Kiểm tra lại địa chỉ hoặc mật khẩu.")
            return f"Kết nối tốt, hình {w}×{h}"

        def done(result, error):
            self._busy(False)
            if error:
                self._set_msg(str(error))
            else:
                self._set_msg("✔ " + result, True)
        self._run(work, done)

    # ------------------------------------------------------------ lưu
    def _save(self):
        name = self.name_edit.text().strip()
        enabled = self.enabled_sw.isChecked()
        engine = self.engine
        if self.cam is not None:
            body = {"name": name, "enabled": enabled}
            if source_kind(self.cam.source) != "phone":
                body["source"] = self.url_edit.text().strip()
            cam = self.cam
            self._busy(True)

            def work():
                try:
                    engine.update_camera(cam, body)
                except RuntimeError:
                    engine.save()
                    raise

            def done(_result, error):
                self._busy(False)
                if error:
                    self._set_msg(str(error))
                else:
                    self.accept()
            self._run(work, done)
            return

        source = self._source()
        file_src = self.file_path if self._type == "file" else ""
        if self._type == "file" and not file_src:
            self._set_msg("Hãy chọn 1 file video")
            return
        if not source and not file_src:
            self._set_msg("Hãy nhập nguồn camera")
            return
        self._set_msg("Đang tải video lên..." if file_src else "Đang thêm camera...", True)
        self._busy(True)

        def work():
            src = source
            if file_src:
                engine.uploads_dir.mkdir(parents=True, exist_ok=True)
                dst = engine.uploads_dir / Path(file_src).name
                if Path(file_src).resolve() != dst.resolve():
                    shutil.copyfile(file_src, dst)
                src = str(dst)
            cam = engine.add_camera(name, src, enabled)
            try:
                cam.start()
            except RuntimeError as e:
                cam.error, cam.state = str(e), "error"
                return str(e)
            return ""

        def done(warn, error):
            self._busy(False)
            if error:
                self._set_msg(str(error))
                return
            if warn:
                toast.show_toast("Đã thêm nhưng chưa chạy được: " + warn)
            self.accept()
        self._run(work, done)

    def _delete(self):
        c = self.cam
        ans = QMessageBox.question(self, "Xoá camera",
                                   f"Xoá camera “{c.name}”? Lịch sử cảnh báo của camera này vẫn được giữ.")
        if ans != QMessageBox.StandardButton.Yes:
            return
        self._busy(True)

        def done(_result, error):
            self._busy(False)
            if error:
                self._set_msg(str(error))
            else:
                self.accept()
        self._run(lambda: self.engine.remove_camera(c), done)
