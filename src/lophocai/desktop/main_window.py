"""Cửa sổ chính: khung sườn giống web/index.html — menu trái (logo, 5 mục, ghi chú, Tắt ứng dụng),
thanh trên (tiêu đề + đồng hồ, chip nguồn, chế độ, âm thanh, đổi sáng/tối) và các trang cuộn được.

Hợp đồng với các trang (pages/*.py):
  page.on_show()   gọi mỗi khi chuyển đến trang (nạp lại dữ liệu)
  page.tick()      gọi mỗi giây khi trang đang hiện (tuỳ chọn)
  live_page.add_event(ev)  gọi cho MỌI cảnh báo mới (kể cả khi trang đang ẩn)
  live_page.select_camera(cam_id), live_page.refresh_cameras(), settings_page.show_tab("adv")
"""
from datetime import datetime

from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import (QAction, QActionGroup, QColor, QIcon, QKeySequence, QLinearGradient, QPainter,
                           QPixmap)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu, QMessageBox,
                               QScrollArea, QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from . import theme, toast
from .dialogs.image_dialog import ImageDialog
from .dialogs.mode_dialog import ModeDialog
from .dialogs.phone_dialog import PhoneQRDialog
from .icons import icon_pixmap
from .pages.cameras_page import CamerasPage
from .pages.history_page import HistoryPage
from .pages.live_page import LivePage
from .pages.settings_page import SettingsPage
from .pages.stats_page import StatsPage
from .ui import Button, Chip, make_label

NAV_ITEMS = [
    ("live", "Trực tiếp", "video", "Giám sát trực tiếp"),
    ("cameras", "Camera", "cam", "Camera"),
    ("stats", "Thống kê", "chart", "Thống kê"),
    ("history", "Lịch sử", "clock", "Lịch sử"),
    ("settings", "Cài đặt", "sliders", "Cài đặt"),
]
WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]


class Logo(QWidget):
    """Ô logo 36x36 chuyển màu tím -> xanh ngọc (.logo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.qcolor("accent"))
        p.drawRoundedRect(QRectF(0, 0, 36, 36), 8, 8)
        p.drawPixmap(QPointF(8, 8), icon_pixmap("video", 20, "#ffffff"))


def make_app_icon():
    """Icon ứng dụng (thanh tác vụ, khay hệ thống): ô tím-xanh có biểu tượng camera."""
    icon = QIcon()
    for size in (32, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(QPointF(0, 0), QPointF(size, size))
        g.setColorAt(0, QColor(theme.DARK["accent"]))
        g.setColorAt(1, QColor(theme.DARK["accent2"]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        ic = int(size * 0.56)
        p.drawPixmap(QPointF((size - ic) / 2, (size - ic) / 2), icon_pixmap("video", ic, "#ffffff"))
        p.end()
        icon.addPixmap(pm)
    return icon


class PageScroll(QScrollArea):
    """Trang cuộn dọc được, có lề 22/28 như .page của web."""

    def __init__(self, page, parent=None):
        super().__init__(parent)
        self.page = page
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        host.setObjectName("pageHost")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(28, 22, 28, 40)
        lay.addWidget(page, 1)
        self.setWidget(host)


class MainWindow(QMainWindow):
    def __init__(self, engine, phone_url=""):
        super().__init__()
        self.engine = engine
        self.phone_url = phone_url
        self._camera_sig = tuple(engine.cameras)
        self._last_event_id = 0
        self._current = "live"
        self.setWindowTitle("Giám sát lớp học AI")
        self.setWindowIcon(make_app_icon())
        QApplication.setWindowIcon(self.windowIcon())
        self.resize(1360, 860)
        self.setMinimumSize(980, 640)
        self._prefs = QSettings("LopHocAI", "DesktopApp")
        geo = self._prefs.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._build_statusbar()
        self._build_ui()
        self._build_shortcuts()
        self._build_tray()
        self.toast = toast.install(self)
        theme.manager.changed.connect(self._refresh_theme_btn)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(1000)
        self._poll()
        QTimer.singleShot(0, self._maybe_ask_mode)

    # ------------------------------------------------------------ dựng giao diện
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(self._build_topbar())

        self.pages_stack = QStackedWidget()
        self.live_page = LivePage(self.engine, self._show_image_dialog, on_add_camera=self._add_camera_from_live)
        self.cameras_page = CamerasPage(self.engine, on_changed=self.live_page.refresh_cameras,
                                        on_view_camera=self._view_camera, on_open_advanced=self._open_advanced)
        self.stats_page = StatsPage(self.engine, self._show_image_dialog)
        self.history_page = HistoryPage(self.engine, self._show_image_dialog)
        self.settings_page = SettingsPage(self.engine, self._show_phone_qr)
        self.pages = {"live": self.live_page, "cameras": self.cameras_page, "stats": self.stats_page,
                      "history": self.history_page, "settings": self.settings_page}
        for key, *_ in NAV_ITEMS:
            self.pages_stack.addWidget(PageScroll(self.pages[key]))
        cl.addWidget(self.pages_stack, 1)
        outer.addWidget(content, 1)
        self.navigate("live")

    def _build_sidebar(self):
        side = QWidget()
        side.setObjectName("side")
        side.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        side.setFixedWidth(232)
        lay = QVBoxLayout(side)
        lay.setContentsMargins(14, 20, 14, 20)
        lay.setSpacing(4)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 4, 8, 22)
        brand.setSpacing(10)
        brand.addWidget(Logo())
        names = QVBoxLayout()
        names.setSpacing(0)
        title = make_label("Lớp học AI")
        title.setStyleSheet("font-size:15px; font-weight:700;")
        names.addWidget(title)
        names.addWidget(make_label("Cảnh báo hành vi", "small"))
        brand.addLayout(names)
        brand.addStretch(1)
        lay.addLayout(brand)

        self.nav_buttons = {}
        for key, label, icon, _title in NAV_ITEMS:
            b = Button(label, icon, "nav")
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _=False, k=key: self.navigate(k))
            lay.addWidget(b)
            self.nav_buttons[key] = b
        lay.addStretch(1)

        foot = QFrame()
        foot.setObjectName("foot")
        fl = QVBoxLayout(foot)
        fl.setContentsMargins(12, 12, 12, 12)
        fl.setSpacing(0)
        fl.addWidget(make_label("🔒 Chỉ xem được trên máy này", "small"))
        strong = make_label("Video không gửi đi đâu")
        strong.setStyleSheet("font-size:12px; font-weight:600;")
        fl.addWidget(strong)
        lay.addWidget(foot)
        lay.addSpacing(8)
        quit_btn = Button("Tắt ứng dụng", "power", "nav")
        quit_btn.set_fg("muted")
        quit_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        quit_btn.setToolTip("Tắt hẳn ứng dụng")
        quit_btn.clicked.connect(self._quit)
        lay.addWidget(quit_btn)
        return side

    def _build_topbar(self):
        top = QWidget()
        top.setObjectName("top")
        top.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(top)
        lay.setContentsMargins(28, 14, 28, 14)
        lay.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.title_label = make_label("Giám sát trực tiếp", "h1")
        titles.addWidget(self.title_label)
        lay.addLayout(titles)
        lay.addStretch(1)

        self.src_chip = Chip("Đang kết nối...", dot=True)
        lay.addWidget(self.src_chip)
        self.mode_btn = Button("Chọn chế độ", "grid")
        self.mode_btn.setToolTip("Đổi chế độ giám sát")
        self.mode_btn.clicked.connect(lambda: self._open_mode_dialog(allow_cancel=True))
        lay.addWidget(self.mode_btn)
        self.sound_btn = Button("Âm thanh bật", "bell")
        self.sound_btn.setToolTip("Âm thanh cảnh báo")
        self.sound_btn.clicked.connect(self._toggle_sound)
        lay.addWidget(self.sound_btn)
        self.theme_btn = Button(icon="sun")
        self.theme_btn.setToolTip("Đổi giao diện sáng/tối")
        self.theme_btn.clicked.connect(self._toggle_theme)
        lay.addWidget(self.theme_btn)
        self._refresh_theme_btn()
        return top

    # ------------------------------------------------------------ thanh menu, thanh trạng thái, khay hệ thống
    def _action(self, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_shortcuts(self):
        """Phím tắt toàn cửa sổ (không dùng thanh menu)."""
        acts = [("Ctrl+N", self._add_camera_from_live), ("Ctrl+M", lambda: self._open_mode_dialog(True)),
                ("F11", self._toggle_fullscreen), ("Ctrl+Q", self._quit)]
        acts += [(f"Ctrl+{i}", lambda k=key: self.navigate(k)) for i, (key, *_r) in enumerate(NAV_ITEMS, start=1)]
        for keys, slot in acts:
            a = QAction(self)
            a.setShortcut(QKeySequence(keys))
            a.triggered.connect(lambda _=False, f=slot: f())
            self.addAction(a)

    def _toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def _build_statusbar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(True)
        self.status_label = QLabel("")
        self.clock_label = QLabel("")
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.clock_label)

    def _build_tray(self):
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Giám sát lớp học AI")
        menu = QMenu()
        menu.addAction(self._action("Mở cửa sổ", self._show_from_tray))
        menu.addAction(self._action("Thoát", self._quit))
        self.tray.setContextMenu(menu)
        self._tray_menu = menu
        self.tray.activated.connect(
            lambda reason: self._show_from_tray() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def _show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------ điều hướng
    def navigate(self, key):
        if key not in self.pages:
            key = "live"
        self._current = key
        idx = [k for k, *_ in NAV_ITEMS].index(key)
        self.pages_stack.setCurrentIndex(idx)
        for k, b in self.nav_buttons.items():
            b.set_on(k == key)
        self.title_label.setText(NAV_ITEMS[idx][3])
        page = self.pages[key]
        if hasattr(page, "on_show"):
            page.on_show()

    def _view_camera(self, cam_id):
        self.live_page.select_camera(cam_id)
        self.navigate("live")

    def _add_camera_from_live(self):
        self.navigate("cameras")
        self.cameras_page._add_camera()

    def _open_advanced(self):
        self.navigate("settings")
        self.settings_page.show_tab("adv")

    # ------------------------------------------------------------ chế độ giám sát
    def _maybe_ask_mode(self):
        if self.engine.mode is None and self.engine.cfg.get("modes"):
            self._open_mode_dialog(allow_cancel=False)

    def _open_mode_dialog(self, allow_cancel):
        dialog = ModeDialog(self.engine, allow_cancel, parent=self)
        if not (dialog.exec() and dialog.chosen):
            return
        chosen = dialog.chosen
        if self.engine.mode and self.engine.mode != chosen:
            ans = QMessageBox.question(self, "Đổi chế độ",
                                       "Đổi chế độ sẽ dừng và nạp lại mô hình, mất vài giây. Tiếp tục?")
            if ans != QMessageBox.StandardButton.Yes:
                return
        toast.show_toast("Đang nạp mô hình...")
        try:
            self.engine.set_mode(chosen)
        except ValueError as e:
            toast.show_toast("Không đổi được chế độ: " + str(e))
        self._poll()

    # ------------------------------------------------------------ nút trên thanh trên
    def _sound_on(self):
        return bool(self.engine.settings.get("server_sound", self.engine.cfg["output"]["sound"]))

    def _toggle_sound(self):
        on = not self._sound_on()
        self.engine.settings["server_sound"] = on
        self.engine.save()
        if on:
            from lophocai.integrations.audio import play_alert
            play_alert("phone")
        self._refresh_sound_btn()

    def _refresh_sound_btn(self):
        on = self._sound_on()
        self.sound_btn.setText("Âm thanh bật" if on else "Tắt tiếng")
        self.sound_btn.set_icon("bell" if on else "bell-off")

    def _toggle_theme(self):
        theme.manager.toggle()
        self.engine.settings["theme"] = theme.manager.pref
        self.engine.save()
        self._refresh_theme_btn()

    def _refresh_theme_btn(self):
        self.theme_btn.set_icon("moon" if theme.manager.mode == "light" else "sun")

    # ------------------------------------------------------------ hộp thoại phụ
    def _show_image_dialog(self, path):
        ImageDialog(path, parent=self).exec()

    def _show_phone_qr(self):
        PhoneQRDialog(self.phone_url, parent=self).exec()

    def _quit(self):
        ans = QMessageBox.question(self, "Tắt ứng dụng", "Tắt hẳn ứng dụng? Hệ thống sẽ ngừng giám sát.")
        if ans == QMessageBox.StandardButton.Yes:
            self.close()

    # ------------------------------------------------------------ cập nhật mỗi giây
    def _poll(self):
        now = datetime.now()
        self.clock_label.setText(f"{now:%H:%M:%S} {WEEKDAYS[now.weekday()]}, {now:%d/%m}")

        new_events = [e for e in self.engine.events if e["id"] > self._last_event_id]
        if new_events:
            multi = len(self.engine.cameras) > 1
            texts = dict.fromkeys((e["camera_name"] + ": " if multi else "") + e["text"] for e in new_events)
            toast.show_toast(" · ".join(texts))
            if self.tray is not None and not self.isActiveWindow():
                self.tray.showMessage("Cảnh báo lớp học", " · ".join(texts),
                                      QSystemTrayIcon.MessageIcon.Warning, 6000)
            for e in new_events:
                self.live_page.add_event(e)
            self._last_event_id = new_events[-1]["id"]

        sig = tuple(self.engine.cameras)
        if sig != self._camera_sig:   # camera được thêm/xoá từ luồng khác (vd điện thoại tự tạo camera)
            self._camera_sig = sig
            self.live_page.refresh_cameras()
            if self._current == "cameras":
                self.cameras_page.on_show()
        cams = list(self.engine.cameras.values())
        running = sum(1 for c in cams if c.state == "running")
        warn = self.engine.overview()["warning"]
        if not cams:
            self.src_chip.set_text("Chưa có camera")
        elif len(cams) == 1:
            self.src_chip.set_text(cams[0].name)
        else:
            self.src_chip.set_text(f"{running}/{len(cams)} camera đang chạy")
        self.src_chip.dot.set_state("alarm" if warn else "on" if running else "")
        self.nav_buttons["live"].set_badge(warn)

        info = self.engine.modes_info()
        cur = next((m for m in info["modes"] if m["id"] == info["mode"]), None)
        self.mode_btn.setText(cur["ten"] if cur else "Chọn chế độ")
        ov = self.engine.overview()
        self.status_label.setText(
            f"Chế độ: {cur['ten'] if cur else 'chưa chọn'}  ·  {running}/{len(cams)} camera đang chạy  ·  "
            f"{ov['people']} học sinh  ·  {warn} cảnh báo")
        self._refresh_sound_btn()

        page = self.pages[self._current]
        if hasattr(page, "tick"):
            page.tick()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()

    # ------------------------------------------------------------ đóng ứng dụng
    def closeEvent(self, event):
        """Đóng cửa sổ = tắt app: dừng mọi camera, đóng file đang mở."""
        self._prefs.setValue("geometry", self.saveGeometry())
        if self.tray is not None:
            self.tray.hide()
        self._poll_timer.stop()
        self.live_page.close()
        self.engine.stop_all()
        for cam in self.engine.cameras.values():
            cam.focus.close()
        self.engine.logger.close()
        super().closeEvent(event)
