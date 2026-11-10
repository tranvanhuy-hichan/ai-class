"""Trang Camera (#page-cameras của web): tóm tắt + nút thêm, banner phần cứng, lưới thẻ camera
(ảnh xem trước 16:9, trạng thái, thống kê, Dừng/Xem/Chạy, Tự chạy) và thẻ nét đứt "Thêm camera".

Hợp đồng với main_window: CamerasPage(engine, on_changed, on_view_camera, on_open_advanced); on_show(); tick().
"""
import cv2
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPainterPath
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget)

from lophocai.application.hardware import hardware, recommended_cameras
from lophocai.desktop import theme, toast
from lophocai.desktop.dialogs.camera_dialog import CameraDialog
from lophocai.desktop.dialogs.common import BgTask, hw_text, icon_ghost
from lophocai.desktop.icons import IconLabel, icon_pixmap
from lophocai.desktop.ui import Button, Card, Chip, Meter, Notice, Switch, clear_layout, make_label
from lophocai.domain.models import mask_source, source_kind

STATE = {"stopped": "Đã dừng", "starting": "Đang khởi động", "running": "Đang chạy", "error": "Lỗi"}
KIND = {"webcam": ("video", "Webcam / USB"), "phone": ("phone", "Điện thoại"), "rtsp": ("link", "Camera IP (RTSP)"),
        "ip": ("link", "Camera IP"), "file": ("upload", "Video")}
CARD_MIN_W, GRID_GAP = 320, 16


def bgr_to_qimage(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


def _b(value, token="text"):
    return f'<span style="color:{theme.c(token)}; font-weight:700;">{value}</span>'


class ElidedLabel(QLabel):
    """Nhãn tự cắt bớt chữ bằng "…" khi hẹp (text-overflow: ellipsis)."""

    def __init__(self, text="", pad=0, mode=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._full, self._pad, self._mode = text, pad, mode
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._elide()

    def set_full_text(self, text):
        self._full = text
        self.setToolTip(text)
        self._elide()
        self.updateGeometry()

    def _elide(self):
        fm = QFontMetrics(self.font())
        QLabel.setText(self, fm.elidedText(self._full, self._mode, max(16, self.width() - self._pad)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        return QSize(fm.horizontalAdvance(self._full) + self._pad + 2, super().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(24, super().minimumSizeHint().height())


# ====================================================================== banner phần cứng
class HwCell(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(2)
        lay.addWidget(make_label(title, "small"))
        self.value = ElidedLabel()
        self.value.setStyleSheet("font-weight:600;")
        lay.addWidget(self.value)
        self.sub = ElidedLabel()
        self.sub.setProperty("role", "small")
        lay.addWidget(self.sub)
        theme.manager.changed.connect(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(theme.qcolor("border"))
        p.setBrush(theme.qcolor("surface2"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)


class HwBar(QWidget):
    """Thanh dùng RAM / VRAM (.hwbar): nhãn + "x / y GB đang dùng" + "còn z GB" + thanh 8px."""

    def __init__(self, label, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.name = QLabel(label)
        self.name.setStyleSheet("font-size:12.5px;")
        self.used = QLabel()
        self.used.setStyleSheet("font-size:12.5px; font-weight:700;")
        self.free = make_label("", "muted")
        self.free.setStyleSheet("font-size:12.5px;")
        row.addWidget(self.name)
        row.addWidget(self.used)
        row.addStretch(1)
        row.addWidget(self.free)
        lay.addLayout(row)
        self.meter = Meter(height=8, min_width=40)
        lay.addWidget(self.meter)

    def set_usage(self, used, total):
        ratio = used / total if total else 0
        token = "bad" if ratio > 0.85 else "head" if ratio > 0.65 else "ok"
        self.used.setText(f"{used} / {total} GB đang dùng")
        self.free.setText(f"còn {max(0, total - used):.1f} GB")
        self.meter.set_segments([(theme.c(token), min(1.0, ratio))], total=1.0)


class HwBanner(Notice):
    """Banner khuyến nghị số camera (#capBanner): chữ + 3 ô phần cứng + thanh RAM (+ VRAM)."""

    def __init__(self, parent=None):
        super().__init__("", "default", "gauge", parent)
        lay = self.layout()
        lay.removeWidget(self.label)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(self.label)
        grid = QHBoxLayout()
        grid.setContentsMargins(0, 12, 0, 0)
        grid.setSpacing(10)
        self.cells = [HwCell("Bộ xử lý"), HwCell("Card đồ họa"), HwCell("Khuyến nghị")]
        for c in self.cells:
            grid.addWidget(c, 1)
        col.addLayout(grid)
        self.ram = HwBar("RAM")
        self.vram = HwBar("Bộ nhớ card đồ họa")
        col.addWidget(self.ram)
        col.addWidget(self.vram)
        lay.addLayout(col, 1)

    def update_from(self, engine):
        hw = hardware()
        rec = recommended_cameras(hw, engine.has_gpu())
        cams = list(engine.cameras.values())
        running = sum(1 for c in cams if c.state in ("running", "starting"))
        fps_list = [c.status["fps"] for c in cams if c.state == "running"]
        avg = sum(fps_list) / len(fps_list) if fps_list else None
        slow = running > 1 and avg is not None and avg < 3
        over = running > rec or slow
        multi = engine.multi()

        self.set_variant("warn" if over else ("default" if not multi else "ok"), "alert" if over else "gauge")
        title = ""
        if not multi:
            title = ("<b>Đang ở chế độ 1 camera</b> (mặc định, phù hợp mọi máy). Muốn chạy nhiều camera cùng lúc, "
                     "bật “Chạy nhiều camera” ở <a href=\"adv\">Cài đặt → Nâng cao</a>. ")
        self.set_html(title + "<b>Chạy nhiều camera chỉ phù hợp máy mạnh</b>: mỗi camera cần thêm bộ nhớ và sức xử lý, "
                              "máy yếu sẽ chậm, giật hình và nóng.")

        cpu = hw["cpu"].replace("(R)", "").replace("(TM)", "")
        self.cells[0].value.set_full_text(cpu)
        self.cells[0].sub.set_full_text(f"{hw['cores']} luồng")
        self.cells[1].value.set_full_text(hw["gpu"] if hw["gpu"] else "Không có (chạy bằng CPU)")
        self.cells[1].sub.set_full_text(f"{hw['vram_gb']} GB bộ nhớ riêng" if hw["gpu"]
                                        else "chậm hơn nhiều khi chạy nhiều camera")
        self.cells[2].value.set_full_text(f"Tối đa {rec} camera")
        if over:
            sub = f"Bạn đang chạy {running}"
            if slow:
                sub += f", tốc độ trung bình chỉ {avg:.1f} hình/giây: máy đang quá tải"
        else:
            sub = f"Đang chạy {running}" + (f" · trung bình {avg:.1f} hình/giây" if avg is not None else "")
        self.cells[2].sub.set_full_text(sub)
        self.ram.set_usage(hw["ram_used_gb"], hw["ram_gb"])
        self.vram.setVisible(bool(hw["gpu"]))
        if hw["gpu"]:
            self.vram.set_usage(round(hw["vram_gb"] - hw["vram_free_gb"], 1), hw["vram_gb"])


# ====================================================================== thẻ camera
class Thumb(QWidget):
    """Ảnh xem trước 16:9 của thẻ camera: khung hình (khi chạy) hoặc icon giữ chỗ, pill trạng thái góc trái-trên."""

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self._icon, self._image = icon, None
        self.chip = Chip("", "overlay", dot=True, compact=True, parent=self)
        self.chip.label.setStyleSheet(self.chip.label.styleSheet() + " font-weight:600;")
        self.chip.move(10, 10)
        self.chip.raise_()

    def set_state(self, state):
        token = {"running": "ok", "starting": "head", "error": "bad"}.get(state, "faint")
        self.chip.set_text(STATE.get(state, state))
        self.chip.dot.set_state("blink" if state == "starting" else "", theme.c(token))
        self.chip.adjustSize()

    def set_image(self, image):
        self._image = image
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r, w, h = 15.0, self.width(), self.height()
        path = QPainterPath()
        path.moveTo(0, h)
        path.lineTo(0, r)
        path.quadTo(0, 0, r, 0)
        path.lineTo(w - r, 0)
        path.quadTo(w, 0, w, r)
        path.lineTo(w, h)
        path.closeSubpath()
        p.setClipPath(path)
        p.fillRect(self.rect(), QColor("#05070b"))
        img = self._image
        if img is not None and not img.isNull():
            s = min(w / img.width(), h / img.height())
            iw, ih = img.width() * s, img.height() * s
            p.drawImage(QRectF((w - iw) / 2, (h - ih) / 2, iw, ih), img)
        else:
            p.drawPixmap(QPointF((w - 34) / 2, (h - 34) / 2), icon_pixmap(self._icon, 34, "faint"))


class CamCard(Card):
    def __init__(self, cam, on_edit, on_toggle, on_view, on_auto, parent=None):
        super().__init__(parent)
        self.cam = cam
        self._last_bgr_id = -1
        self._on = False
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        icon, kind = KIND.get(source_kind(cam.source), KIND["ip"])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.thumb = Thumb(icon)
        lay.addWidget(self.thumb)

        body = QVBoxLayout()
        body.setContentsMargins(16, 14, 16, 16)
        body.setSpacing(8)
        lay.addLayout(body)

        ct = QHBoxLayout()
        ct.setSpacing(8)
        self.name = ElidedLabel(cam.name)
        self.name.setStyleSheet("font-size:15px; font-weight:700;")
        self.name.set_full_text(cam.name)
        ct.addWidget(self.name, 1)
        edit = icon_ghost("edit", "Chỉnh sửa")
        edit.clicked.connect(lambda: on_edit(cam))
        ct.addWidget(edit)
        body.addLayout(ct)

        cs = QHBoxLayout()
        cs.setSpacing(6)
        cs.addWidget(IconLabel(icon, 14, "muted"))
        k = make_label(kind, "muted")
        k.setStyleSheet("font-size:12.5px;")
        cs.addWidget(k)
        if source_kind(cam.source) != "phone":
            cs.addWidget(make_label("·", "muted"))
            code = ElidedLabel(pad=12)
            code.setProperty("role", "code")
            code.set_full_text(mask_source(cam.source))
            cs.addWidget(code, 0)
        cs.addStretch(1)
        body.addLayout(cs)

        self.err = make_label("", wrap=True)
        self.err.setStyleSheet(f"color:{theme.c('bad')}; font-size:12.5px;")
        self.err.setVisible(False)
        body.addWidget(self.err)

        st = QHBoxLayout()
        st.setSpacing(14)
        a = QHBoxLayout()
        a.setSpacing(6)
        a.addWidget(IconLabel("users", 14, "muted"))
        self.people = make_label("", "muted")
        a.addWidget(self.people)
        st.addLayout(a)
        self.fps = make_label("", "muted")
        st.addWidget(self.fps)
        w = QHBoxLayout()
        w.setSpacing(6)
        self.warn_icon = IconLabel("alert", 14, "muted")
        w.addWidget(self.warn_icon)
        self.warn = make_label("", "muted")
        w.addWidget(self.warn)
        st.addLayout(w)
        st.addStretch(1)
        body.addLayout(st)

        self.btns = QHBoxLayout()
        self.btns.setSpacing(8)
        self.btns.setContentsMargins(0, 2, 0, 0)
        self.stop_btn = Button("Dừng", "stop")
        self.stop_btn.clicked.connect(lambda: on_toggle(cam, self.stop_btn))
        self.view_btn = Button("Xem", "video", "primary")
        self.view_btn.clicked.connect(lambda: on_view(cam))
        self.run_btn = Button("Chạy", "play", "primary")
        self.run_btn.clicked.connect(lambda: on_toggle(cam, self.run_btn))
        for b in (self.stop_btn, self.view_btn, self.run_btn):
            self.btns.addWidget(b)
        self.btns.addStretch(1)
        auto_l = make_label("Tự chạy", "muted")
        auto_l.setStyleSheet("font-size:12.5px;")
        auto_l.setToolTip("Tự chạy camera này khi mở app")
        self.btns.addWidget(auto_l)
        self.auto = Switch(cam.enabled)
        self.auto.toggled.connect(lambda v: on_auto(cam, v))
        self.btns.addWidget(self.auto)
        body.addLayout(self.btns)
        body.addStretch(1)
        self.refresh()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.thumb.setFixedHeight(round((self.width() - 2) * 9 / 16))

    def refresh(self):
        c = self.cam
        on = c.state in ("running", "starting")
        self._on = on
        self.thumb.set_state(c.state)
        self.stop_btn.setVisible(on)
        self.view_btn.setVisible(on)
        self.run_btn.setVisible(not on)
        self.err.setText(c.error or "")
        self.err.setVisible(bool(c.error))
        s = c.status
        self.people.setText(f"{_b(s['people'])} HS")
        self.fps.setText(f"{_b(s['fps'])} FPS")
        self.warn.setText(_b(s["warning"], "bad" if s["warning"] > 0 else "text"))
        if on:
            c.mark_watched()
            frame, fid = c.latest_bgr()
            if frame is not None and fid != self._last_bgr_id:
                self._last_bgr_id = fid
                self.thumb.set_image(bgr_to_qimage(frame))
        elif self.thumb._image is not None:
            self._last_bgr_id = -1
            self.thumb.set_image(None)


class AddCard(Card):
    def __init__(self, text, on_click, parent=None):
        super().__init__(parent, dashed=True)
        self._click = on_click
        self.setMinimumHeight(220)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(6)
        self.icon = IconLabel("plus", 28, "muted")
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        self.label = make_label(text, "muted")
        lay.addWidget(self.label, 0, Qt.AlignmentFlag.AlignHCenter)

    def enterEvent(self, e):
        self.icon.set_icon(color="text")
        self.label.setProperty("role", "")
        self.label.setStyleSheet(f"color:{theme.c('text')};")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.icon.set_icon(color="muted")
        self.label.setStyleSheet(f"color:{theme.c('muted')};")
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self._click()
        super().mouseReleaseEvent(e)


# ====================================================================== trang
class CamerasPage(QWidget):
    def __init__(self, engine, on_changed=None, on_view_camera=None, on_open_advanced=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.on_changed = on_changed
        self.on_view_camera = on_view_camera
        self.on_open_advanced = on_open_advanced
        self._sig = None
        self._items = []
        self._cols = 0
        self._tasks = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 16)
        head.setSpacing(12)
        self.summary = make_label("", "hint")
        head.addWidget(self.summary)
        head.addStretch(1)
        self.add_btn = Button("Thêm camera", "plus", "primary")
        self.add_btn.clicked.connect(self._add_camera)
        head.addWidget(self.add_btn)
        root.addLayout(head)

        self.banner = HwBanner()
        self.banner.linkActivated.connect(lambda _l: self.on_open_advanced and self.on_open_advanced())
        root.addWidget(self.banner)
        root.addSpacing(16)

        self.host = QWidget()
        self.grid = QGridLayout(self.host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(GRID_GAP)
        self.grid.setVerticalSpacing(GRID_GAP)
        root.addWidget(self.host, 1)
        root.addStretch(1)

    # ------------------------------------------------------------ vòng đời trang
    def on_show(self):
        self._update_head()
        self.banner.update_from(self.engine)
        self.rebuild(force=True)

    def tick(self):
        self._update_head()
        self.banner.update_from(self.engine)
        self.rebuild()
        for it in self._items:
            if isinstance(it, CamCard):
                it.refresh()

    def _swap_mode(self):
        return bool(self.engine.cameras) and not self.engine.multi()

    def _update_head(self):
        cams = list(self.engine.cameras.values())
        running = sum(1 for c in cams if c.state == "running")
        self.summary.setText(f"{len(cams)} camera · {running} đang chạy" if cams else "Chưa có camera nào")
        self.add_btn.setText("Đổi camera" if self._swap_mode() else "Thêm camera")

    # ------------------------------------------------------------ lưới thẻ
    def rebuild(self, force=False):
        cams = list(self.engine.cameras.values())
        sig = tuple((c.id, c.name, c.source, c.state, c.enabled, c.error) for c in cams) + (self._swap_mode(),)
        if sig == self._sig and not force:
            return
        self._sig = sig
        for it in self._items:
            self.grid.removeWidget(it)
            it.setParent(None)
            it.deleteLater()
        self._items = []
        for c in cams:
            self._items.append(CamCard(c, self._edit_camera, self._toggle_camera, self._view_camera, self._set_auto))
        self._items.append(AddCard("Đổi camera" if self._swap_mode() else "Thêm camera", self._add_camera))
        self._cols = 0
        self._place()

    def _place(self):
        w = max(self.host.width(), self.width())
        cols = max(1, int((w + GRID_GAP) // (CARD_MIN_W + GRID_GAP)))
        if cols == self._cols and all(self.grid.indexOf(i) >= 0 for i in self._items):
            return
        self._cols = cols
        while self.grid.count():
            self.grid.takeAt(0)
        for i, it in enumerate(self._items):
            self.grid.addWidget(it, i // cols, i % cols)
            it.show()
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)
        for c in range(cols, 8):
            self.grid.setColumnStretch(c, 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place()

    # ------------------------------------------------------------ hành động
    def _notify(self):
        self._update_head()
        self.rebuild(force=True)
        if self.on_changed:
            self.on_changed()

    def _phone_url(self):
        return getattr(self.window(), "phone_url", "")

    def _add_camera(self):
        CameraDialog(self.engine, None, self.window(), phone_url=self._phone_url()).exec()
        self._notify()

    def _edit_camera(self, cam):
        CameraDialog(self.engine, cam, self.window(), phone_url=self._phone_url()).exec()
        self._notify()

    def _view_camera(self, cam):
        if self.on_view_camera:
            self.on_view_camera(cam.id)

    def _set_auto(self, cam, value):
        try:
            self.engine.update_camera(cam, {"enabled": value})
        except RuntimeError as e:
            toast.show_toast(str(e))

    def _toggle_camera(self, cam, button):
        stop = cam.state in ("running", "starting")
        button.setEnabled(False)

        def work():
            if stop:
                cam.stop()
            else:
                try:
                    cam.start()
                except RuntimeError as e:
                    cam.error, cam.state = str(e), "error"
                    raise

        def done(_result, error):
            button.setEnabled(True)
            if error:
                toast.show_toast(str(error))
            self._notify()
        task = BgTask(work, self)
        task.done.connect(done)
        self._tasks.append(task)
        task.start()
