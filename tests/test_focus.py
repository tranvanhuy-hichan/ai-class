"""Kiểm tra chỉ số tập trung:  python tests/test_focus.py"""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.focus import FocusTracker, instant, label  # noqa: E402

normal = {"active": {}, "signals": {}}
tentative = {"active": {}, "signals": {"head_down": True}}
alert = {"active": {"phone": 3.0}, "signals": {"phone": True}}


def test_instant():
    assert instant([]) is None
    assert instant([normal, normal]) == 100
    assert instant([normal, alert]) == 50
    assert instant([tentative]) == 50
    assert instant([alert, alert]) == 0
    assert instant([normal, normal, normal, alert]) == 75


def test_label():
    assert label(None) == "Chưa có dữ liệu"
    assert label(90) == "Tập trung tốt" and label(70) == "Trung bình" and label(20) == "Dễ mất tập trung"


def test_minutes_and_persistence():
    path = Path(tempfile.mkdtemp()) / "focus.csv"
    ft = FocusTracker(path)
    t0 = datetime(2026, 10, 23, 9, 0, 30)
    for i in range(4):
        ft.update([normal, normal], when=t0)                       # 09:00 -> 100
    for i in range(4):
        ft.update([normal, alert], when=t0 + timedelta(minutes=1))  # 09:01 -> 50
    ft.update([alert], when=t0 + timedelta(minutes=2))            # 09:02 -> 0, ghi 09:01 ra file
    s = ft.series(3, end=t0 + timedelta(minutes=2))
    assert [p["score"] for p in s] == [100.0, 50.0, 0.0], s
    assert [p["students"] for p in s][:2] == [2.0, 2.0]
    ft.close()
    again = FocusTracker(path)   # mở lại app: vẫn còn dữ liệu các phút đã ghi
    got = {p["label"]: p["score"] for p in again.series(3, end=t0 + timedelta(minutes=2))}
    assert got["09:00"] == 100.0 and got["09:01"] == 50.0


def test_no_students_is_none():
    ft = FocusTracker()
    ft.update([normal])
    assert ft.now == 100
    assert ft.series(2)[-1]["score"] == 100.0
    assert FocusTracker().series(5)[0]["score"] is None   # phút không có ai -> None, không phải 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
