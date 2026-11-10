"""Trang Cài đặt (#page-settings của web/index.html): menu bên 210px + 6 tab dạng thẻ, tự động lưu.

Lỗi cũ: load() gọi setValue khi tín hiệu tự-lưu đang nối, nên mỗi ô vừa nạp lại kích hoạt save() ghi các
ô CHƯA nạp (đang ở mức tối thiểu) đè lên cấu hình thật. Nay mọi lần nạp đều chạy dưới cờ _loading.
"""
import json
import shutil
import threading
from datetime import datetime

import requests
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QSizePolicy, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from lophocai.application.settings import TUNABLE, apply_settings
from lophocai.integrations.audio import play_alert
from lophocai.storage import cleanup
from lophocai.application.settings import current_settings

from .. import theme
from ..ui import Button, Card, Chip, Notice, Switch, card_header, make_label, separator, repolish

TABS = [("detect", "Nhận diện", "gauge"), ("display", "Hiển thị", "video"), ("sound", "Âm thanh", "bell"),
        ("notify", "Thông báo", "send"), ("storage", "Lưu trữ", "download"), ("adv", "Nâng cao", "sliders")]
SAVE_DELAY_MS = 600


class NumSpin(QDoubleSpinBox):
    """Ô số bỏ đuôi ".0" như <input type=number> của web (2 chứ không phải 2.0)."""

    def __init__(self, lo, hi, step, parent=None):
        super().__init__(parent)
        self.setDecimals(2)
        self.setRange(lo, hi)
        self.setSingleStep(step)
        self.setFixedWidth(96)   # nút lên/xuống đã được theme.py ẩn; NoButtons làm QDoubleSpinBox mất chữ

    def textFromValue(self, v):
        return f"{v:g}"


class IntSpin(QSpinBox):
    def __init__(self, lo, hi, step, parent=None):
        super().__init__(parent)
        self.setRange(lo, hi)
        self.setSingleStep(step)
        self.setFixedWidth(96)


def apply_body(engine, body):
    """Áp dụng một nhóm cài đặt vào engine rồi lưu xuống settings.json."""
    for key in TUNABLE:
        if key in body:
            engine.settings[key] = float(body[key]) if key != "imgsz" else int(body[key])
    for key in ("telegram_token", "telegram_chat_id"):
        if key in body:
            engine.settings[key] = str(body[key]).strip()
    if "server_sound" in body:
        engine.settings["server_sound"] = bool(body["server_sound"])
    if "save_snapshots" in body:
        engine.settings["save_snapshots"] = engine.logger.save_snapshots = bool(body["save_snapshots"])
    if "keep_days" in body:
        engine.settings["keep_days"] = max(1, int(float(body["keep_days"])))
    if "max_storage_mb" in body:
        engine.settings["max_storage_mb"] = max(50, int(float(body["max_storage_mb"])))
    threading.Thread(target=engine.clean_storage, daemon=True).start()
    for key in ("show_skeleton", "head_down_pose", "autostart"):
        if key in body:
            engine.settings[key] = bool(body[key])
    for key, lo, hi in (("parallel", 1, 8), ("max_cameras", 1, 16), ("max_fps", 0, 30)):
        if key in body:
            engine.settings[key] = max(lo, min(hi, int(float(body[key] or 0))))
    if "multi_camera" in body:
        engine.settings["multi_camera"] = bool(body["multi_camera"])
        if not engine.multi():
            for extra in [c for c in engine.cameras.values() if c.running][1:]:
                extra.stop()
    engine.gate.set_limit(engine.parallel())
    apply_settings(engine.cfg, engine.settings)
    engine.settings_file.write_text(json.dumps(engine.settings, ensure_ascii=False, indent=2), encoding="utf-8")
    engine.save()


class _Bridge(QObject):
    """Đưa kết quả từ luồng nền (Telegram) về luồng giao diện."""
    result = Signal(str, str, bool)   # (nhãn đích, nội dung, thành công)
    chat_found = Signal(str)


class SettingsPage(QWidget):
    def __init__(self, engine, show_phone_qr_cb=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.show_phone_qr_cb = show_phone_qr_cb
        self._loading = False
        self._tab_index = 0
        self._bridge = _Bridge(self)
        self._bridge.result.connect(self._on_result)
        self._bridge.chat_found.connect(self._on_chat_found)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._save_now)
        self._build_ui()
        self.load()

    # ------------------------------------------------------------ khung trang
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        head = QHBoxLayout()
        head.addWidget(make_label("Mọi thay đổi được lưu và áp dụng ngay, không cần bấm lưu.", "hint"))
        head.addStretch(1)
        self.save_state = make_label("", "chipText")
        head.addWidget(self.save_state)
        root.addLayout(head)

        wrap = QHBoxLayout()
        wrap.setSpacing(22)
        nav = QWidget()
        nav.setFixedWidth(210)
        nl = QVBoxLayout(nav)
        nl.setContentsMargins(0, 0, 0, 0)
        nl.setSpacing(4)
        self.nav_buttons = []
        for i, (_key, label, icon) in enumerate(TABS):
            b = Button(label, icon, "setnav")
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.clicked.connect(lambda _=False, idx=i: self._select_tab(idx))
            nl.addWidget(b)
            self.nav_buttons.append(b)
        nl.addStretch(1)
        wrap.addWidget(nav, 0, Qt.AlignmentFlag.AlignTop)

        self.stack = QStackedWidget()
        for build in (self._tab_detect, self._tab_display, self._tab_sound, self._tab_notify,
                      self._tab_storage, self._tab_adv):
            self.stack.addWidget(build())
        wrap.addWidget(self.stack, 1)
        root.addLayout(wrap, 1)
        self._select_tab(0)

    def _select_tab(self, idx):
        self._tab_index = idx
        self.stack.setCurrentIndex(idx)
        for i, b in enumerate(self.nav_buttons):
            b.set_on(i == idx)

    def show_tab(self, name):
        for i, (key, *_r) in enumerate(TABS):
            if key == name:
                self._select_tab(i)
                return

    # ------------------------------------------------------------ dựng thẻ / dòng
    def _tab(self, *cards):
        """Một tab: các thẻ xếp dọc cách 18, thẻ cuối giãn hết chiều cao (như .tab.on > .card:last-child)."""
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        for i, c in enumerate(cards):
            lay.addWidget(c, 1 if i == len(cards) - 1 else 0)
        return page

    def _card(self, title, icon=None, trailing=None):
        card = Card()
        cl = QVBoxLayout(card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        cl.addWidget(card_header(title, icon, trailing))
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 16, 18, 18)
        bl.setSpacing(0)
        cl.addWidget(body)
        cl.addStretch(1)
        card.body = bl
        card._rows = 0
        return card

    def _field(self, card, label=None, small=None, *controls, column=False):
        """Dòng .field: nhãn + chú thích nhỏ bên trái, điều khiển căn phải; kẻ ngang mảnh phía trên (trừ dòng đầu)."""
        if card._rows:
            card.body.addWidget(separator())
        card._rows += 1
        row = QWidget()
        lay = QVBoxLayout(row) if column else QHBoxLayout(row)
        lay.setContentsMargins(0, 10, 0, 10)
        lay.setSpacing(12 if not column else 8)
        if label is not None:
            text = QVBoxLayout()
            text.setSpacing(0)
            lab = QLabel(label)
            lab.setWordWrap(True)
            text.addWidget(lab)
            if small:
                s = make_label(small, "small", wrap=True)
                text.addWidget(s)
            if column:
                lay.addLayout(text)
            else:
                lay.addLayout(text, 1)
        for c in controls:
            if isinstance(c, QHBoxLayout):
                lay.addLayout(c)
            else:
                lay.addWidget(c, 0, Qt.AlignmentFlag.AlignVCenter) if not column else lay.addWidget(c)
        card.body.addWidget(row)
        return row

    def _hint(self, card, text, top=8):
        lab = make_label(text, "hint", wrap=True, rich=True)
        lab.setContentsMargins(0, top, 0, 0)
        card.body.addWidget(lab)
        return lab

    def _msg(self, card):
        lab = make_label("", "ok", wrap=True)
        lab.setContentsMargins(0, 8, 0, 0)
        lab.setMinimumHeight(26)
        card.body.addWidget(lab)
        return lab

    def _set_msg(self, label, text, ok):
        label.setText(text)
        label.setProperty("role", "ok" if ok else "err")
        repolish(label)

    @staticmethod
    def _combo(items, width):
        box = QComboBox()
        for label, value in items:
            box.addItem(label, value)
        box.setFixedWidth(width)
        return box

    # ------------------------------------------------------------ các tab
    def _tab_detect(self):
        card = self._card("Độ nhạy nhận diện")
        self.head_down_pose = Switch()
        self._field(card, "Nhận biết gục đầu bằng khung xương",
                    "Bổ sung cho mô hình AI (hay sót bạn nằm gục ở xa). Chỉ báo khi đầu thấp và không thấy mặt, "
                    "nên bạn cúi viết bài không bị báo. Tắt nếu thấy báo nhầm", self.head_down_pose)
        self.head_down_ratio = QSlider(Qt.Orientation.Horizontal)
        self.head_down_ratio.setRange(-10, 40)          # x100: -0.1 .. 0.4, bước 0.01
        self.head_down_ratio.setFixedWidth(160)
        self.ratio_value = make_label("", "bold")
        self.ratio_value.setFixedWidth(40)
        self.ratio_value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.head_down_ratio.valueChanged.connect(lambda v: self.ratio_value.setText(f"{v / 100:g}"))
        self._field(card, "Mức coi là nằm gục xuống bàn (chỉ khi bật khung xương)",
                    "Chỉ khi đầu thấp ngang hoặc dưới vai mới tính (0 = ngang vai). Cúi đọc/viết bài không bị báo. "
                    "Tăng lên nếu muốn nhạy hơn", self.head_down_ratio, self.ratio_value)
        self.phone_seconds = NumSpin(0.5, 3600, 0.5)
        self._field(card, "Báo dùng điện thoại sau", "giây cầm điện thoại liên tục", self.phone_seconds)
        self.head_down_seconds = NumSpin(1, 3600, 0.5)
        self._field(card, "Báo nằm gục xuống bàn sau", "giây nằm gục liên tục", self.head_down_seconds)
        self.sleeping_seconds = NumSpin(4, 3600, 1)
        self._field(card, "Báo ngủ gật sau", "giây nằm gục liên tục (từ lúc bắt đầu gục)", self.sleeping_seconds)
        self.cooldown = NumSpin(0, 3600, 1)
        self._field(card, "Không báo lại cùng học sinh trong", "giây", self.cooldown)
        self.imgsz = self._combo([("Gần (1–5 học sinh)", 640), ("Vừa (nửa lớp)", 960), ("Cả lớp học", 1280)], 210)
        self._field(card, "Chế độ nhìn", "Cả lớp thì chậm hơn khoảng 3 lần so với chế độ gần", self.imgsz)
        self._autosave(self.head_down_pose, self.head_down_ratio, self.phone_seconds, self.head_down_seconds,
                       self.sleeping_seconds, self.cooldown, self.imgsz)
        return self._tab(card)

    def _tab_display(self):
        card = self._card("Hiển thị trên video")
        self.show_skeleton = Switch()
        self._field(card, "Hiện khung xương trên video",
                    "Vẽ các điểm khớp (vai, tay, đầu...) hệ thống dùng để nhận diện. Tắt khi lớp đông cho đỡ rối",
                    self.show_skeleton)
        self.theme_sel = self._combo([("Theo hệ thống", "system"), ("Tối", "dark"), ("Sáng", "light")], 180)
        self.theme_sel.currentIndexChanged.connect(self._on_theme_changed)
        self._field(card, "Giao diện", "Theo hệ thống, hoặc luôn sáng/luôn tối", self.theme_sel)
        self._hint(card, "Lật, xoay, độ sáng và phóng to chỉnh riêng cho từng camera ngay trên trang Trực tiếp "
                         "(nút thanh trượt ở góc video).", 6)
        self._autosave(self.show_skeleton)
        return self._tab(card)

    def _tab_sound(self):
        card = self._card("Âm thanh cảnh báo")
        self.server_sound = Switch()
        test = Button(icon="play", variant="ghost")
        test.setToolTip("Thử")
        test.clicked.connect(lambda: play_alert("phone"))
        self._field(card, "Loa của máy chạy hệ thống", "Máy tính đặt trong lớp", test, self.server_sound)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for key, icon, label in [("phone", "phone", "Điện thoại"), ("sleeping", "moon", "Ngủ gật"),
                                 ("smoking", "smoke", "Hút thuốc"), ("fighting", "fight", "Đánh nhau"),
                                 ("head_down", "down", "Gục xuống bàn")]:
            b = Button(label, icon)
            b.clicked.connect(lambda _=False, k=key: play_alert(k))
            buttons.addWidget(b)
        buttons.addStretch(1)
        row = self._field(card, "Nghe thử trên máy này", None, column=True)
        row.layout().addLayout(buttons)
        self._hint(card, "Giọng đọc là file có sẵn nên không cần Internet. Đổi giọng: "
                         "<code>python scripts/make_voices.py --voice vi-VN-NamMinhNeural</code>")
        self._autosave(self.server_sound)
        return self._tab(card)

    def _tab_notify(self):
        card = self._card("Thông báo Telegram", "send")
        steps = QLabel("<ol style='margin:0; padding-left:18px'>"
                       "<li>Trên Telegram, nhắn cho <b>@BotFather</b> lệnh <code>/newbot</code> và copy token.</li>"
                       "<li>Mở bot vừa tạo và bấm <b>Start</b>.</li>"
                       "<li>Dán token vào đây và bấm “Tìm chat ID”.</li></ol>")
        steps.setTextFormat(Qt.TextFormat.RichText)
        steps.setWordWrap(True)
        steps.setProperty("role", "chipText")
        steps.setContentsMargins(0, 0, 0, 10)
        card.body.addWidget(steps)
        card._rows = 1
        self.telegram_token = QLineEdit()
        self.telegram_token.setPlaceholderText("Token bot, ví dụ 123456:ABC...")
        self._field(card, None, None, self.telegram_token)
        self.telegram_chat_id = QLineEdit()
        self.telegram_chat_id.setPlaceholderText("Chat ID")
        find = Button("Tìm chat ID")
        find.clicked.connect(self._find_chat)
        self._field(card, None, None, self.telegram_chat_id, find)
        send = Button("Gửi thử", "send")
        send.clicked.connect(self._test_telegram)
        row = QHBoxLayout()
        row.addWidget(send)
        row.addStretch(1)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 8, 0, 0)
        card.body.addWidget(w)
        self.tg_msg = self._msg(card)
        self._hint(card, "Tin nhắn Telegram ghi rõ camera nào phát hiện, kèm ảnh chụp lúc cảnh báo.", 0)
        self._autosave(self.telegram_token, self.telegram_chat_id)
        return self._tab(card)

    def _tab_storage(self):
        self.usage_chip = Chip("-")
        card = self._card("Lưu trữ", None, [self.usage_chip])
        self.save_snapshots = Switch()
        self._field(card, "Lưu ảnh khi có cảnh báo", "Để xem lại trong lịch sử. Tắt thì không lưu ảnh nào",
                    self.save_snapshots)
        self.keep_days = IntSpin(1, 3650, 1)
        self._field(card, "Tự xoá ảnh cũ hơn", "ngày", self.keep_days)
        self.max_storage_mb = IntSpin(50, 1_000_000, 50)
        self._field(card, "Dung lượng tối đa", "MB. Vượt mức thì tự xoá ảnh cũ nhất trước", self.max_storage_mb)
        clear = Button("Xoá hết ảnh", "alert", "danger")
        clear.clicked.connect(self._clear_storage)
        export = Button("Tải nhật ký Excel", "download")
        export.clicked.connect(self._export_csv)
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.setContentsMargins(0, 8, 0, 0)
        btns.addWidget(clear)
        btns.addWidget(export)
        btns.addStretch(1)
        w = QWidget()
        w.setLayout(btns)
        card.body.addWidget(w)
        self._hint(card, "App tự dọn 30 phút một lần, gồm cả video demo đã tải lên. "
                         "Nhật ký Excel (.csv) không bị xoá.")
        self.store_msg = self._msg(card)
        self._autosave(self.save_snapshots, self.keep_days, self.max_storage_mb)
        return self._tab(card)

    def _tab_adv(self):
        speed = self._card("Tốc độ xử lý")
        self.max_fps = self._combo([("Không giới hạn", 0), ("1 hình/giây (tiết kiệm nhất)", 1),
                                    ("2 hình/giây (khuyến nghị)", 2), ("3 hình/giây", 3), ("5 hình/giây", 5),
                                    ("10 hình/giây", 10), ("15 hình/giây", 15)], 210)
        self._field(speed, "Số hình xử lý mỗi giây (mỗi camera)",
                    "Số khung hình AI xử lý mỗi giây cho mỗi camera. Điện thoại, nằm gục, ngủ gật, hút thuốc đều "
                    "kéo dài vài giây nên 1–5 hình/giây là đủ. Khi phát hiện người đứng sát nhau và hình chuyển "
                    "động mạnh, hệ thống tự tăng lên 8 hình/giây để bắt đánh nhau", self.max_fps)
        self._hint(speed, "Càng thấp càng nhẹ máy và chạy được nhiều camera, nhưng đánh nhau cần hình dày nên hệ "
                          "thống tự tăng lên 8 hình/giây khi thấy người đứng sát nhau và chuyển động mạnh.", 12)

        self.hw_chip = Chip("-")
        multi = self._card("Nhiều camera", None, [self.hw_chip])
        self.multi_camera = Switch()
        self.multi_camera.toggled.connect(self._on_multi_toggled)
        self._field(multi, "Chạy nhiều camera cùng lúc",
                    "Mặc định tắt: hệ thống chỉ chạy 1 camera. Mỗi camera thêm cần 1 bộ AI riêng nên rất tốn RAM và CPU",
                    self.multi_camera)
        warn = Notice("<b>Chỉ bật trên máy mạnh.</b> Máy yếu chạy nhiều camera sẽ bị chậm, giật hình và nóng. "
                      "Hãy xem mục khuyến nghị ở trang Camera trước khi bật.", "warn", "alert")
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 8, 0, 4)
        wl.addWidget(warn)
        multi.body.addWidget(wrap)
        self.multi_opts = QWidget()
        ol = QVBoxLayout(self.multi_opts)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)
        opts = Card()      # chỉ để tái dùng _field (đếm dòng); thẻ tạm không hiển thị
        opts.body, opts._rows = ol, 1
        self.autostart = Switch()
        self._field(opts, "Tự chạy các camera khi mở app",
                    "Camera nào bật “Tự chạy” trong trang Camera sẽ khởi động cùng app", self.autostart)
        self.max_cameras = IntSpin(1, 16, 1)
        self._field(opts, "Số camera chạy cùng lúc tối đa", "Mỗi camera chạy cần thêm khoảng 0,5–1 GB RAM",
                    self.max_cameras)
        self.parallel = self._combo([(str(n), n) for n in (1, 2, 3, 4)], 120)
        self._field(opts, "Số camera xử lý AI đồng thời",
                    "Máy chỉ có CPU nên để 1: các camera lần lượt chờ đến lượt, mỗi camera chậm hơn nhưng không giật "
                    "cả máy. Máy có card đồ họa rời có thể đặt 2–3", self.parallel)
        multi.body.addWidget(self.multi_opts)
        self._hint(multi, "Gợi ý: máy yếu chạy 2 camera thì đặt “Chế độ nhìn” ở mức Vừa, số hình xử lý mỗi giây là "
                          "1–2 và xử lý đồng thời là 1.")

        system = self._card("Hệ thống")
        qr = Button("Hiện mã QR", "qr")
        qr.clicked.connect(lambda: self.show_phone_qr_cb and self.show_phone_qr_cb())
        self._field(system, "Camera điện thoại", "Quét mã QR bằng điện thoại cùng Wi-Fi", qr)
        quit_btn = Button("Tắt ứng dụng", "power", "danger")
        quit_btn.clicked.connect(self._quit_app)
        self._field(system, "Tắt hẳn ứng dụng", "Hệ thống ngừng giám sát tất cả camera", quit_btn)
        self._autosave(self.max_fps, self.multi_camera, self.autostart, self.max_cameras, self.parallel)
        return self._tab(speed, multi, system)

    # ------------------------------------------------------------ nạp / lưu
    def _autosave(self, *widgets):
        for w in widgets:
            if isinstance(w, Switch):
                w.toggled.connect(self._changed)
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.valueChanged.connect(self._changed)
            elif isinstance(w, QSlider):
                w.valueChanged.connect(self._changed)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._changed)
            elif isinstance(w, QLineEdit):
                w.textEdited.connect(self._changed)

    def _changed(self, *_):
        if self._loading:
            return
        self._set_state("Đang lưu...", None)
        self._timer.start(SAVE_DELAY_MS)

    def _set_state(self, text, ok):
        self.save_state.setText(text)
        self.save_state.setProperty("role", "chipText" if ok is None else "ok" if ok else "err")
        repolish(self.save_state)

    def on_show(self):
        self.load()

    def load(self):
        """Nạp giá trị thật từ engine vào ô nhập. Chạy dưới cờ _loading để KHÔNG kích hoạt tự-lưu."""
        s = current_settings(self.engine)
        self._loading = True
        try:
            self.head_down_pose.setChecked(bool(s["head_down_pose"]))
            self.head_down_ratio.setValue(round(float(s["head_down_ratio"]) * 100))
            self.ratio_value.setText(f"{float(s['head_down_ratio']):g}")
            self.phone_seconds.setValue(float(s["phone_seconds"]))
            self.head_down_seconds.setValue(float(s["head_down_seconds"]))
            self.sleeping_seconds.setValue(float(s["sleeping_seconds"]))
            self.cooldown.setValue(float(s["cooldown"]))
            self._select_data(self.imgsz, int(s["imgsz"]))
            self.show_skeleton.setChecked(bool(s["show_skeleton"]))
            self._select_data(self.theme_sel, theme.manager.pref)
            self.server_sound.setChecked(bool(s["server_sound"]))
            self.telegram_token.setText(s["telegram_token"])
            self.telegram_chat_id.setText(s["telegram_chat_id"])
            self.save_snapshots.setChecked(bool(s["save_snapshots"]))
            self.keep_days.setValue(int(s["keep_days"]))
            self.max_storage_mb.setValue(int(s["max_storage_mb"]))
            self._select_data(self.max_fps, int(s["max_fps"]))
            self.multi_camera.setChecked(bool(s["multi_camera"]))
            self.autostart.setChecked(bool(s["autostart"]))
            self.max_cameras.setValue(int(s["max_cameras"]))
            self._select_data(self.parallel, int(s["parallel"]))
        finally:
            self._loading = False
        self.multi_opts.setVisible(self.multi_camera.isChecked())
        hw = s["hw"]
        self.hw_chip.set_text(f"{(hw['gpu'] or 'CPU').replace('NVIDIA GeForce ', '')} · {hw['ram_gb']} GB RAM")
        self._refresh_usage()

    @staticmethod
    def _select_data(box, value):
        idx = box.findData(value)
        box.setCurrentIndex(idx if idx >= 0 else 0)

    def _refresh_usage(self):
        files, mb = cleanup.usage([self.engine.logger.snap_dir, self.engine.uploads_dir])
        self.usage_chip.set_text(f"{files} file · {round(mb, 1)} MB")

    def _body(self):
        return {
            "head_down_ratio": self.head_down_ratio.value() / 100,
            "phone_seconds": self.phone_seconds.value(),
            "head_down_seconds": self.head_down_seconds.value(),
            "sleeping_seconds": self.sleeping_seconds.value(),
            "cooldown": self.cooldown.value(),
            "imgsz": self.imgsz.currentData(),
            "keep_days": self.keep_days.value(),
            "max_storage_mb": self.max_storage_mb.value(),
            "max_cameras": self.max_cameras.value(),
            "parallel": self.parallel.currentData(),
            "max_fps": self.max_fps.currentData(),
            "telegram_token": self.telegram_token.text(),
            "telegram_chat_id": self.telegram_chat_id.text(),
            "head_down_pose": self.head_down_pose.isChecked(),
            "show_skeleton": self.show_skeleton.isChecked(),
            "server_sound": self.server_sound.isChecked(),
            "save_snapshots": self.save_snapshots.isChecked(),
            "autostart": self.autostart.isChecked(),
            "multi_camera": self.multi_camera.isChecked(),
        }

    def _save_now(self):
        try:
            apply_body(self.engine, self._body())
            self._set_state(f"✔ Đã lưu lúc {datetime.now():%H:%M:%S}", True)
            self._refresh_usage()
        except Exception as e:  # noqa: BLE001 - hiện lỗi cho người dùng thay vì làm sập giao diện
            self._set_state(f"Lỗi: {e}", False)

    # ------------------------------------------------------------ hành động riêng từng ô
    def _on_theme_changed(self, _):
        if self._loading:
            return
        pref = self.theme_sel.currentData()
        theme.manager.set_pref(pref)
        self.engine.settings["theme"] = pref
        self.engine.save()

    def _on_multi_toggled(self, on):
        self.multi_opts.setVisible(on)
        if on and not self._loading:
            ans = QMessageBox.question(
                self, "Chạy nhiều camera",
                "Chạy nhiều camera chỉ phù hợp máy mạnh (nhiều RAM, nhiều nhân CPU hoặc có card đồ họa rời).\n"
                "Máy yếu sẽ bị chậm, giật hình và nóng.\n\nBật chế độ nhiều camera?")
            if ans != QMessageBox.StandardButton.Yes:
                self.multi_camera.setChecked(False)   # toggled(False) -> ẩn khối, tự-lưu giá trị cũ

    def _on_result(self, target, text, ok):
        label = self.tg_msg if target == "tg" else self.store_msg
        self._set_msg(label, text, ok)

    def _on_chat_found(self, chat_id):
        self.telegram_chat_id.setText(chat_id)
        self._changed()

    def _find_chat(self):
        token = self.telegram_token.text().strip()

        def work():
            try:
                r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
            except requests.RequestException as e:
                self._bridge.result.emit("tg", f"Không kết nối được Telegram: {e}", False)
                return
            if not r.get("ok"):
                self._bridge.result.emit("tg", "Token không đúng", False)
                return
            chats = [u["message"]["chat"] for u in r["result"] if "message" in u]
            if not chats:
                self._bridge.result.emit(
                    "tg", "Chưa thấy tin nhắn nào. Hãy mở bot trên Telegram, bấm Start rồi thử lại.", False)
                return
            chat = chats[-1]
            self._bridge.chat_found.emit(str(chat["id"]))
            self._bridge.result.emit("tg", f"✔ Tìm thấy: {chat.get('first_name') or chat.get('title', '')} ({chat['id']})", True)

        self._set_msg(self.tg_msg, "Đang tìm...", True)
        threading.Thread(target=work, daemon=True).start()

    def _test_telegram(self):
        self._timer.stop()
        self._save_now()
        self.engine._telegram({"text": "Thử thông báo từ hệ thống giám sát lớp học", "camera_name": "",
                               "time": datetime.now().isoformat(timespec="seconds")}, "")
        self._set_msg(self.tg_msg, "✔ Đã gửi, kiểm tra Telegram nhé", True)

    def _clear_storage(self):
        ans = QMessageBox.question(self, "Xoá hết ảnh", "Xoá hết ảnh cảnh báo đã lưu? Nhật ký Excel vẫn được giữ.")
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = self.engine.clean_storage(everything=True)
            self._set_msg(self.store_msg, f"✔ Đã xoá {removed} file", True)
            self._refresh_usage()
        except Exception as e:  # noqa: BLE001
            self._set_msg(self.store_msg, str(e), False)

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Tải nhật ký Excel", "canh_bao.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            shutil.copyfile(self.engine.logger.path, path)
            self._set_msg(self.store_msg, f"✔ Đã lưu {path}", True)
        except OSError as e:
            self._set_msg(self.store_msg, str(e), False)

    def _quit_app(self):
        ans = QMessageBox.question(self, "Tắt ứng dụng", "Tắt hẳn ứng dụng? Hệ thống sẽ ngừng giám sát.")
        if ans == QMessageBox.StandardButton.Yes:
            self.window().close()
