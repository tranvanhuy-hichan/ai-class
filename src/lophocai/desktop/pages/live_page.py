"""Trang Trực tiếp (#page-live của web): camtabs, 7 thẻ KPI, sân khấu video / lưới camera, cột phải
(Mức độ tập trung + Cảnh báo gần đây).

Hợp đồng với MainWindow: on_show(), tick() mỗi giây, add_event(ev) cho mọi cảnh báo mới,
select_camera(cam_id), refresh_cameras(), close().
"""
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (QGridLayout, QHBoxLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget)

from lophocai.desktop import theme
from lophocai.desktop.bridge import bgr_to_qimage
from lophocai.desktop.icons import IconLabel
from lophocai.desktop.ui import Button, Card, Chip, make_label
from lophocai.desktop.widgets import CamTab, FullscreenWindow, KpiCard, Stage, TileGrid
from lophocai.desktop.widgets_feed import FeedCard, FocusCard

BEHAVIORS = ("phone", "head_down", "sleeping", "fighting", "smoking")
KPI_DEFS = [   # (khoá, icon, màu theme, nhãn)
    ("people", "users", "accent2", "Học sinh trong khung"),
    ("warning", "alert", "bad", "Đang cảnh báo"),
    ("phone", "phone", "phone", "Dùng điện thoại"),
    ("head_down", "down", "head", "Gục đầu xuống bàn"),
    ("sleeping", "moon", "sleep", "Ngủ gục / ngủ gật"),
    ("fighting", "fight", "fight", "Đánh nhau"),
    ("smoking", "smoke", "smoke", "Hút thuốc"),
]
STATE_TEXT = {"stopped": "Đã dừng", "starting": "Đang khởi động", "running": "Đang chạy", "error": "Lỗi"}
PUMP_MS = 66          # ~15 khung/giây cho khung xem
FOCUS_EVERY = 10      # làm tươi biểu đồ tập trung mỗi 10 giây
RIGHT_COL_W = 400


class _IconBox(QWidget):
    """Ô icon bo tròn nền nhạt (dùng cho thẻ "Chưa có camera nào")."""

    def __init__(self, icon, size=60, radius=10, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._r = radius
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(IconLabel(icon, 28, "accent"), 0, Qt.AlignmentFlag.AlignCenter)
        theme.manager.changed.connect(self.update)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.accent_soft())
        p.drawRoundedRect(QRectF(self.rect()), self._r, self._r)


class LivePage(QWidget):
    def __init__(self, engine, image_dialog_cb, on_add_camera=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.image_dialog_cb = image_dialog_cb
        self.on_add_camera = on_add_camera
        self.selected = "all"
        self.all_events = []
        self._seen_ids = set()
        self._sig = None
        self._kpi_visible = None
        self._kpi_cols = None
        self._stage_cam_id = None
        self._stage_last_id = -1
        self._tile_last = {}
        self._pump_n = 0
        self._focus_tick = 0
        self._fullscreen = None
        self._fs_last_id = -1
        self._build_ui()
        self._pump_timer = QTimer(self)
        self._pump_timer.timeout.connect(self._pump)
        self._pump_timer.start(PUMP_MS)

    # ------------------------------------------------------------ dựng giao diện
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tabs_host = QWidget()
        self.tabs_layout = QHBoxLayout(self.tabs_host)
        self.tabs_layout.setContentsMargins(0, 0, 0, 14)
        self.tabs_layout.setSpacing(8)
        self.tabs_layout.addStretch(1)
        self.tabs_host.hide()
        root.addWidget(self.tabs_host)

        self.kpi_host = QWidget()
        self.kpi_grid = QGridLayout(self.kpi_host)
        self.kpi_grid.setContentsMargins(0, 0, 0, 18)
        self.kpi_grid.setSpacing(12)
        self.kpis = {}
        for key, icon, tone, label in KPI_DEFS:
            self.kpis[key] = KpiCard(icon, tone, label, self.kpi_host)
        root.addWidget(self.kpi_host)

        live = QHBoxLayout()
        live.setSpacing(18)

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self._build_nocam())      # 0: chưa có camera
        self.stage = Stage()
        self.stage.flip_clicked.connect(lambda: self._set_view({"flip_h": not self._cam_view().get("flip_h", False)}))
        self.stage.panel_changed.connect(self._set_view)
        self.stage.fullscreen_clicked.connect(self._open_fullscreen)
        self.view_stack.addWidget(self.stage)               # 1: 1 camera
        self.grid = TileGrid()
        self.view_stack.addWidget(self.grid)                # 2: lưới
        live.addWidget(self.view_stack, 1)

        right = QWidget()
        right.setMaximumWidth(RIGHT_COL_W)
        right.setMinimumWidth(340)
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(14)
        self.focus = FocusCard()
        self.focus.range_changed.connect(self._load_focus)
        rl.addWidget(self.focus)
        self.feed = FeedCard(self.engine, lambda path: self.image_dialog_cb(path))
        self.feed.setMinimumHeight(220)
        rl.addWidget(self.feed, 1)
        live.addWidget(right)
        root.addLayout(live, 1)

        self._layout_kpis(force=True)

    def _build_nocam(self):
        card = Card()
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(card)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(8)
        lay.addWidget(_IconBox("cam"), 0, Qt.AlignmentFlag.AlignHCenter)
        title = make_label("Chưa có camera nào")
        title.setStyleSheet("font-size:21px; font-weight:700;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(title)
        hint = make_label("Thêm webcam, camera điện thoại, camera IP của lớp hoặc một video để bắt đầu giám sát.",
                          "hint", wrap=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hint)
        lay.addSpacing(8)
        btn = Button("Thêm camera", "plus", "primary")
        btn.clicked.connect(lambda: self.on_add_camera() if self.on_add_camera else None)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
        return card

    # ------------------------------------------------------------ KPI: dàn đều một hàng, hẹp thì 4 cột
    def _visible_kpis(self):
        info = self.engine.modes_info()
        cur = next((m for m in info["modes"] if m["id"] == info["mode"]), None)
        out = []
        for key, *_ in KPI_DEFS:
            if key in BEHAVIORS and cur and key not in cur["behaviors"]:
                continue
            out.append(key)
        return tuple(out)

    def _layout_kpis(self, force=False):
        keys = self._visible_kpis()
        cols = len(keys) if self.width() >= 1000 or self.width() == 0 else 4
        cols = max(1, cols)
        if not force and keys == self._kpi_visible and cols == self._kpi_cols:
            return
        self._kpi_visible, self._kpi_cols = keys, cols
        while self.kpi_grid.count():
            self.kpi_grid.takeAt(0)
        for c in range(8):
            self.kpi_grid.setColumnStretch(c, 0)
        for i, key in enumerate(keys):
            card = self.kpis[key]
            card.show()
            self.kpi_grid.addWidget(card, i // cols, i % cols)
        for key, card in self.kpis.items():
            if key not in keys:
                card.hide()
        for c in range(cols):
            self.kpi_grid.setColumnStretch(c, 1)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._layout_kpis()

    # ------------------------------------------------------------ chọn camera / danh sách camera
    def _cams(self):
        return list(self.engine.cameras.values())

    def _sel_cam(self):
        return self.engine.cameras.get(self.selected)

    def _cam_view(self):
        cam = self._sel_cam()
        return cam.view if cam else {}

    def select_camera(self, cam_id):
        self.selected = cam_id
        self.refresh_cameras()

    def on_show(self):
        self.refresh_cameras()
        self._load_focus()
        self._update_status()

    def _signature(self):
        return (tuple((c.id, c.name, c.state) for c in self._cams()), self.selected)

    def refresh_cameras(self):
        cams = self._cams()
        if len(cams) == 1:
            self.selected = cams[0].id
        if self.selected != "all" and self.selected not in self.engine.cameras:
            self.selected = "all"
        self._sig = self._signature()

        grid = len(cams) >= 2 and self.selected == "all"
        self.view_stack.setCurrentIndex(0 if not cams else 2 if grid else 1)
        self._rebuild_tabs(cams)
        if grid:
            self.grid.set_cameras(cams, self.select_camera)
            self._tile_last = {}
        self._stage_cam_id = None
        self._stage_last_id = -1
        self.stage.surface.clear("")
        self.stage.panel.hide()
        cam = self._sel_cam()
        if cam is not None:
            self.stage.panel.set_view(cam.view)
        self._rebuild_feed()
        self._load_focus()
        self._layout_kpis()
        self._update_status()

    def _rebuild_tabs(self, cams):
        while self.tabs_layout.count():
            item = self.tabs_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()
        self.tabs = {}
        if len(cams) < 2:
            self.tabs_host.hide()
            return
        self.tabs_host.show()
        entries = [("all", f"Tất cả ({len(cams)})", "grid")] + [(c.id, c.name, None) for c in cams]
        for cid, text, icon in entries:
            tab = CamTab(cid, text, icon)
            tab.set_on(cid == self.selected)
            tab.clicked.connect(self.select_camera)
            self.tabs_layout.addWidget(tab)
            self.tabs[cid] = tab
        self.tabs_layout.addStretch(1)

    # ------------------------------------------------------------ cảnh báo
    def _selected_events(self):
        return [e for e in self.all_events if self.selected == "all" or e["camera"] == self.selected]

    def _rebuild_feed(self):
        self.feed.set_events(self._selected_events(), len(self._cams()) > 1)

    def add_event(self, ev):
        if ev["id"] in self._seen_ids:
            return
        self._seen_ids.add(ev["id"])
        self.all_events.append(ev)
        if len(self.all_events) > 500:
            self.all_events = self.all_events[-500:]
        if self.selected != "all" and ev["camera"] != self.selected:
            return
        self.feed.prepend(ev, len(self._cams()) > 1, len(self._selected_events()))

    # ------------------------------------------------------------ chỉnh hình
    def _set_view(self, patch):
        cam = self._sel_cam()
        if cam is None:
            return
        try:
            self.stage.panel.set_view(cam.set_view(patch))
        except (ValueError, TypeError):
            pass
        self._update_status()

    # ------------------------------------------------------------ mức độ tập trung
    def _load_focus(self):
        try:
            d = self.engine.focus_summary(self.focus.range_minutes(), "" if self.selected == "all" else self.selected)
        except Exception:
            return
        self.focus.set_summary(d)

    # ------------------------------------------------------------ cập nhật mỗi giây
    def tick(self):
        if self._signature() != self._sig:
            self.refresh_cameras()
            return
        self._update_status()
        self._focus_tick += 1
        if self._focus_tick >= FOCUS_EVERY:
            self._focus_tick = 0
            self._load_focus()

    def _update_status(self):
        eng = self.engine
        self._layout_kpis()
        cams = self._cams()
        chosen = [c for c in cams if self.selected == "all" or c.id == self.selected]
        people = sum(c.status["people"] for c in chosen)
        warn = sum(c.status["warning"] for c in chosen)
        self.kpis["people"].set_value(people)
        self.kpis["warning"].set_value(warn)
        self.kpis["warning"].set_alarm(warn > 0)
        if self.selected == "all":
            counts = eng.logger.counts
        else:
            counts = {}
            for e in eng.events:
                if e["camera"] == self.selected:
                    counts[e["behavior"]] = counts.get(e["behavior"], 0) + 1
        for b in BEHAVIORS:
            self.kpis[b].set_value(counts.get(b, 0))

        # tab camera: chấm trạng thái + badge số cảnh báo
        for cid, tab in getattr(self, "tabs", {}).items():
            c = eng.cameras.get(cid)
            n = c.status["warning"] if c else sum(x.status["warning"] for x in cams)
            tab.set_warning(n)
            if tab.dot is not None and c is not None:
                tab.dot.set_state("alarm" if n else "on" if c.state == "running" else "")

        cam = self._sel_cam()
        if cam is not None:
            self.stage.update_status(cam.name, cam.status["people"], cam.status["fps"], cam.view,
                                     cam.status["warning"] > 0)
            if not self.stage.panel.br_slider.isSliderDown() and not self.stage.panel.zm_slider.isSliderDown():
                self.stage.panel.set_view(cam.view)
        for cid, tile in self.grid.tiles.items():
            c = eng.cameras.get(cid)
            if c is None:
                continue
            running = c.state == "running"
            info = f"{c.status['people']} HS · {c.status['fps']} FPS" if running else STATE_TEXT.get(c.state, c.state)
            tile.update_status(c.name, "alarm" if c.status["warning"] else "on" if running else "", info,
                               c.status["warning"] > 0)

        self.focus.set_now(cam.status["focus"] if cam is not None else eng.overview()["focus"])

    # ------------------------------------------------------------ khung hình: lấy theo nhịp cố định
    def _pump(self):
        if not self.isVisible():
            return
        self._pump_n += 1
        idx = self.view_stack.currentIndex()
        if idx == 1:
            cam = self._sel_cam()
            if cam is None:
                return
            if cam.id != self._stage_cam_id:
                self._stage_cam_id, self._stage_last_id = cam.id, -1
            cam.mark_watched()
            frame, fid = cam.latest_bgr()
            if fid != self._stage_last_id and frame is not None:
                self._stage_last_id = fid
                img = bgr_to_qimage(frame)
                self.stage.surface.set_image(img)
                if self._fullscreen is not None:
                    self._fullscreen.surface.set_image(img)
        elif idx == 2 and self._pump_n % 4 == 0:
            for cid, tile in self.grid.tiles.items():
                cam = self.engine.cameras.get(cid)
                if cam is None:
                    continue
                cam.mark_watched()
                frame, fid = cam.latest_bgr()
                if fid != self._tile_last.get(cid) and frame is not None:
                    self._tile_last[cid] = fid
                    tile.surface.set_image(bgr_to_qimage(frame))

    # ------------------------------------------------------------ toàn màn hình
    def _open_fullscreen(self):
        if self._fullscreen is not None:
            self._fullscreen.close()
            return
        self._fullscreen = FullscreenWindow()
        self._fullscreen.closed.connect(self._on_fullscreen_closed)
        if self.stage.surface.has_image():
            self._fullscreen.surface.set_image(self.stage.surface._image)
        self._fullscreen.showFullScreen()

    def _on_fullscreen_closed(self):
        self._fullscreen = None

    # ------------------------------------------------------------ đóng
    def close(self):
        self._pump_timer.stop()
        if self._fullscreen is not None:
            self._fullscreen.close()
        return super().close()
