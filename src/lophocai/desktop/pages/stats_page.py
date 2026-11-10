"""Trang Thống kê: tương đương #page-stats của web/index.html (cùng cách tính với route /api/stats)."""
import shutil
from datetime import datetime, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFileDialog, QGridLayout, QHBoxLayout, QMessageBox, QSizePolicy, QVBoxLayout,
                               QWidget)

from lophocai.desktop import theme
from lophocai.desktop.ui import (BarChart, Button, Card, Donut, Meter, Tag, ThumbLabel, card_header, make_label,
                                 snapshot_path)

from ._tables import GridTable, LegendItem, WrapPair

KEYS = ["phone", "head_down", "sleeping", "fighting", "smoking"]
MINUTES = 30
REFRESH_SECONDS = 10


def compute_stats(engine, minutes=MINUTES):
    """Giống route /api/stats: cột theo phút, top học sinh, tổng theo hành vi."""
    now = datetime.now()
    events = list(engine.events)
    buckets = [{"label": (now - timedelta(minutes=i)).strftime("%H:%M"), **{b: 0 for b in KEYS}}
               for i in reversed(range(minutes))]
    index = {b["label"]: b for b in buckets}
    for e in events:
        label = e["time"][11:16]
        if label in index and e["behavior"] in KEYS:
            index[label][e["behavior"]] += 1
    students = {}
    for e in events:
        key = (e["camera"], e["student"])
        students.setdefault(key, {b: 0 for b in KEYS})[e["behavior"]] += 1
    top = sorted(students.items(), key=lambda kv: -sum(kv[1].values()))[:10]
    totals = {k: sum(1 for e in events if e["behavior"] == k) for k in KEYS}
    return {"timeline": buckets, "students": [{"student": k[1], **v} for k, v in top],
            "totals": totals, "recent": list(reversed(events[-50:]))}


class StatsPage(QWidget):
    def __init__(self, engine, image_dialog_cb=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.image_dialog_cb = image_dialog_cb
        self._sig = None
        self._ticks = 0
        self._last_event_id = -1
        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------ dựng giao diện
    def _card(self, title, trailing=None):
        card = Card()
        card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(card_header(title, trailing=trailing))
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 16, 18, 18)
        lay.addWidget(body, 1)
        return card, bl

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        row1 = QGridLayout()
        row1.setHorizontalSpacing(18)
        row1.setColumnStretch(0, 2)
        row1.setColumnStretch(1, 1)

        legend = QWidget()
        ll = QHBoxLayout(legend)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(16)
        for k in KEYS:
            ll.addWidget(LegendItem(theme.behavior_color(k), theme.BEHAVIOR_SHORT[k]))
        card, bl = self._card("Cảnh báo theo phút", [legend])
        self.chart = BarChart(240)
        bl.addWidget(self.chart)
        row1.addWidget(card, 0, 0)

        card, bl = self._card("Tỉ lệ hành vi")
        self.donut = Donut(170, 24)
        self.rows_box = QWidget()
        self.rows_lay = QVBoxLayout(self.rows_box)
        self.rows_lay.setContentsMargins(0, 0, 0, 0)
        self.rows_lay.setSpacing(12)
        self.rows_box.setMinimumWidth(170)
        bl.addWidget(WrapPair(self.donut, self.rows_box))
        bl.addStretch(1)
        row1.addWidget(card, 0, 1)
        root.addLayout(row1)

        row2 = QGridLayout()
        row2.setHorizontalSpacing(18)
        row2.setColumnStretch(0, 2)
        row2.setColumnStretch(1, 1)

        export = Button("Tải nhật ký Excel", "download")
        export.clicked.connect(self._export)
        card, bl = self._card("Lịch sử cảnh báo", [export])
        self.history_table = GridTable([("Ảnh", 0, False, 72), ("Thời gian", 2, False, None),
                                        ("Học sinh", 2, False, None), ("Hành vi", 3, False, None),
                                        ("Kéo dài", 2, True, None)])
        bl.addWidget(self.history_table)
        bl.addStretch(1)
        row2.addWidget(card, 0, 0)

        card, bl = self._card("Học sinh cần chú ý")
        self.top_table = GridTable([("Học sinh", 1, False, None), ("Phân bố", 3, False, None),
                                    ("Tổng", 1, True, None)])
        bl.addWidget(self.top_table)
        bl.addStretch(1)
        row2.addWidget(card, 0, 1)
        root.addLayout(row2, 1)

    # ------------------------------------------------------------ dữ liệu
    def on_show(self):
        self._ticks = 0
        self.refresh()

    def tick(self):
        self._ticks += 1
        last = self.engine.events[-1]["id"] if self.engine.events else 0
        if last != self._last_event_id or self._ticks >= REFRESH_SECONDS:
            self._ticks = 0
            self.refresh()

    def refresh(self):
        s = compute_stats(self.engine)
        self._last_event_id = self.engine.events[-1]["id"] if self.engine.events else 0
        tl = s["timeline"]
        bars = []
        for b in tl:
            bars.append({"segments": [(theme.behavior_color(k), b[k]) for k in KEYS if b[k]],
                         "tip": f"{b['label']} · {b['phone']} điện thoại · {b['head_down']} gục đầu · "
                                f"{b['sleeping']} ngủ · {b['fighting']} đánh nhau · {b['smoking']} hút thuốc"})
        n = len(tl)
        axis = [tl[min(n - 1, round(f * (n - 1)))]["label"] for f in (0, .25, .5, .75, 1)]
        mx = max([sum(b[k] for k in KEYS) for b in tl] + [1])
        self.chart.set_data(bars, max_value=mx, axis_labels=axis)

        totals = s["totals"]
        total = sum(totals.values())
        self.donut.set_data([(theme.behavior_color(k), totals[k]) for k in KEYS], total)
        while self.rows_lay.count():
            w = self.rows_lay.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for k in KEYS:
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(10)
            rl.addWidget(Tag(k))
            rl.addStretch(1)
            num = make_label(str(totals[k]), "bold")
            num.setStyleSheet("font-weight:700;")
            rl.addWidget(num)
            pct = make_label(f"{round(totals[k] / total * 100) if total else 0}%", "muted")
            pct.setFixedWidth(44)
            pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            rl.addWidget(pct)
            self.rows_lay.addWidget(row)

        sig = (tuple(e["id"] for e in s["recent"]), tuple((r["student"], sum(r[k] for k in KEYS)) for r in s["students"]),
               theme.manager.mode)
        if sig == self._sig:
            return
        self._sig = sig
        rows = []
        for e in s["recent"]:
            thumb = ThumbLabel(72, 44, 6)
            thumb.set_path(snapshot_path(self.engine, e.get("snapshot", "")))
            thumb.clicked.connect(lambda path: self.image_dialog_cb and self.image_dialog_cb(path))
            dur = make_label(f"{round(e['duration'])}s")
            rows.append([thumb, e["time"][11:], _bold(f"#{e['student']}"), Tag(e["behavior"]), dur])
        self.history_table.set_rows(rows)

        rows = []
        for r in s["students"]:
            t = sum(r[k] for k in KEYS)
            meter = Meter(6, 80)
            meter.set_segments([(theme.behavior_color(k), r[k]) for k in KEYS if r[k]], total=t)
            tot = _bold(str(t))
            rows.append([_bold(f"#{r['student']}"), meter, tot])
        self.top_table.set_rows(rows)

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Tải nhật ký Excel", "canh_bao.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            shutil.copyfile(self.engine.logger.path, path)
        except OSError as e:
            QMessageBox.warning(self, "Không lưu được", str(e))


def _bold(text):
    lab = make_label(text)
    lab.setStyleSheet("font-weight:600;")
    return lab
