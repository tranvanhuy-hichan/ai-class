"""Trang Lịch sử: tương đương #page-history của web/index.html.

Đọc events.csv của engine.logger.path với cùng logic route /api/history (lượt chạy cũ cách nhau >30 phút
được tách riêng), nên còn nguyên sau khi tắt/bật lại app."""
import csv
import shutil
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QMessageBox, QSizePolicy, QVBoxLayout,
                               QWidget)

from lophocai.desktop.ui import Button, Card, Tag, ThumbLabel, card_header, make_label, snapshot_path
from lophocai.detection.rules import BEHAVIOR_NAMES

from ._tables import GridTable

PAGE_SIZE = 50


def fmt_session(s):
    return f"{s[8:10]}/{s[5:7]} {s[11:16]}" if s else "Trước khi có mục này"


class HistoryPage(QWidget):
    def __init__(self, engine, image_dialog_cb=None, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.image_dialog_cb = image_dialog_cb
        self.offset = 0
        self._build_ui()

    # ------------------------------------------------------------ dựng giao diện
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        card = Card()
        root.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 16, 18, 0)
        hl.setSpacing(10)
        self.session_box, self.camera_box, self.behavior_box = QComboBox(), QComboBox(), QComboBox()
        self.behavior_box.addItem("Mọi hành vi", "")
        for key, name in BEHAVIOR_NAMES.items():
            self.behavior_box.addItem({"phone": "Điện thoại", "head_down": "Gục đầu", "sleeping": "Ngủ gục",
                                       "fighting": "Đánh nhau", "smoking": "Hút thuốc"}[key], key)
        for box in (self.session_box, self.camera_box, self.behavior_box):
            box.setMinimumWidth(180)
            box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
            box.currentIndexChanged.connect(self._on_filter_changed)
            hl.addWidget(box)
        hl.addStretch(1)
        export = Button("Tải Excel", "download")
        export.clicked.connect(self._export)
        hl.addWidget(export)
        lay.addWidget(head)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 16, 18, 18)
        bl.setSpacing(0)
        self.summary_label = make_label("", "hint")
        self.summary_label.setContentsMargins(0, 0, 0, 10)
        bl.addWidget(self.summary_label)
        self.table = GridTable([("Ảnh", 0, False, 72), ("Thời gian", 2, False, None), ("Camera", 2, False, None),
                                ("Học sinh", 1, False, None), ("Hành vi", 2, False, None), ("Kéo dài", 1, True, None)])
        bl.addWidget(self.table)
        bl.addStretch(1)

        pager = QHBoxLayout()
        pager.setContentsMargins(0, 14, 0, 0)
        pager.setSpacing(14)
        self.prev_btn = Button("‹ Trước")
        self.prev_btn.clicked.connect(self._prev_page)
        self.page_label = make_label("", "muted")
        self.page_label.setStyleSheet("font-size:13px;")
        self.next_btn = Button("Sau ›")
        self.next_btn.clicked.connect(self._next_page)
        pager.addStretch(1)
        pager.addWidget(self.prev_btn)
        pager.addWidget(self.page_label)
        pager.addWidget(self.next_btn)
        pager.addStretch(1)
        bl.addLayout(pager)
        lay.addWidget(body, 1)

    # ------------------------------------------------------------ dữ liệu
    def _read_rows(self):
        by_name = {v: k for k, v in BEHAVIOR_NAMES.items()}
        sessions, rows, legacy = {}, [], None
        try:
            with open(self.engine.logger.path, newline="", encoding="utf-8-sig") as f:
                for r in csv.reader(f):
                    if len(r) < 5 or r[2] not in by_name:
                        continue
                    sess = r[5] if len(r) > 5 else ""
                    if not sess:
                        try:
                            gap = (datetime.fromisoformat(r[0]) - datetime.fromisoformat(legacy[1])).total_seconds()
                        except (ValueError, TypeError):
                            gap = 0
                        legacy = (r[0] if legacy is None or gap > 1800 else legacy[0], r[0])
                        sess = legacy[0]
                    info = sessions.setdefault(sess, {"session": sess, "count": 0, "first": r[0]})
                    info["count"] += 1
                    rows.append({"time": r[0], "student": r[1], "behavior": by_name[r[2]],
                                 "duration": float(r[3] or 0), "snapshot": r[4], "session": sess,
                                 "camera": r[6] if len(r) > 6 else ""})
        except FileNotFoundError:
            pass
        return sessions, rows

    def on_show(self):
        self.refresh()

    def refresh(self):
        sessions, rows = self._read_rows()
        current = self.engine.logger.session

        keep = self.session_box.currentData() or "all"
        self.session_box.blockSignals(True)
        self.session_box.clear()
        self.session_box.addItem("Tất cả các lần chạy", "all")
        for s in sorted(sessions.values(), key=lambda x: x["first"], reverse=True):
            label = fmt_session(s["session"]) + (" (đang chạy)" if s["session"] == current else "")
            self.session_box.addItem(f"{label} · {s['count']} cảnh báo", s["session"])
        idx = self.session_box.findData(keep)
        self.session_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.session_box.blockSignals(False)

        session = self.session_box.currentData() or "all"
        behavior = self.behavior_box.currentData() or ""
        filtered = [r for r in rows if session in ("", "all") or r["session"] == session]
        if behavior:
            filtered = [r for r in filtered if r["behavior"] == behavior]
        cams = sorted({r["camera"] for r in filtered if r["camera"]})

        keep_cam = self.camera_box.currentData() or ""
        self.camera_box.blockSignals(True)
        self.camera_box.clear()
        self.camera_box.addItem("Mọi camera", "")
        for c in cams:
            self.camera_box.addItem(c, c)
        idx = self.camera_box.findData(keep_cam)
        self.camera_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.camera_box.blockSignals(False)

        camera = self.camera_box.currentData() or ""
        if camera:
            filtered = [r for r in filtered if r["camera"] == camera]
        filtered.reverse()

        total = len(filtered)
        self.offset = min(self.offset, max(0, (total - 1) // PAGE_SIZE * PAGE_SIZE))
        page = filtered[self.offset:self.offset + PAGE_SIZE]
        pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self.summary_label.setText(f"{total} cảnh báo, mới nhất ở trên")
        self.page_label.setText(f"Trang {self.offset // PAGE_SIZE + 1} / {pages}")
        self.prev_btn.setEnabled(self.offset > 0)
        self.next_btn.setEnabled(self.offset + PAGE_SIZE < total)

        table_rows = []
        for r in page:
            thumb = ThumbLabel(72, 44, 6)
            thumb.set_path(snapshot_path(self.engine, r["snapshot"]))
            thumb.clicked.connect(lambda path: self.image_dialog_cb and self.image_dialog_cb(path))
            t = r["time"]
            cam = make_label(r["camera"] or "-", "muted")
            who = make_label(f"#{r['student']}")
            who.setStyleSheet("font-weight:600;")
            table_rows.append([thumb, f"{t[8:10]}/{t[5:7]} {t[11:]}", cam, who, Tag(r["behavior"]),
                               f"{round(r['duration'])}s"])
        self.table.set_rows(table_rows)

    def _on_filter_changed(self, *_):
        self.offset = 0
        self.refresh()

    def _prev_page(self):
        self.offset = max(0, self.offset - PAGE_SIZE)
        self.refresh()

    def _next_page(self):
        self.offset += PAGE_SIZE
        self.refresh()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Tải Excel", "canh_bao.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            shutil.copyfile(self.engine.logger.path, path)
        except OSError as e:
            QMessageBox.warning(self, "Không lưu được", str(e))
