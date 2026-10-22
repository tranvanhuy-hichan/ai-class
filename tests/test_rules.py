"""Kiểm tra luật không cần camera:  python -m pytest tests  (hoặc python tests/test_rules.py)"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import signals as sg  # noqa: E402
from core.rules import BehaviorRules  # noqa: E402

TIMING = {"phone": 2, "head_down": 3, "sleeping": 10, "eyes_closed": 3, "grace": 0.8, "cooldown": 15}


def skeleton(head_y, shoulder_y=200, face=True):
    k = np.zeros((17, 3))
    k[5] = [100, shoulder_y, 0.9]
    k[6] = [200, shoulder_y, 0.9]
    k[9] = [120, 300, 0.9]
    k[10] = [180, 300, 0.9]
    if face:
        for i, x in zip(range(5), (150, 140, 160, 125, 175)):
            k[i] = [x, head_y, 0.9]
    return k


def run(rules, signals, seconds, fps=10, start=0.0):
    alerts = []
    for i in range(int(seconds * fps)):
        _, new = rules.update(1, signals, start + i / fps)
        alerts += new
    return alerts


def test_head_ratio():
    assert sg.head_ratio(skeleton(120), 0.5) > 0.5      # ngồi thẳng
    assert sg.head_ratio(skeleton(205), 0.5) < 0.15     # đầu ngang/thấp hơn vai
    assert sg.head_ratio(skeleton(0, face=False), 0.5) == -1.0  # úp mặt


def test_short_head_down_ignored():
    assert run(BehaviorRules(TIMING), {"head_down": True}, 2) == []


def test_head_down_then_sleeping():
    alerts = run(BehaviorRules(TIMING), {"head_down": True}, 12)
    assert alerts == ["head_down", "sleeping"]


def test_phone_with_flicker():
    rules = BehaviorRules(TIMING)
    alerts = []
    for i in range(40):  # 4 giây, cứ 3 khung thì mất 1 khung
        _, new = rules.update(1, {"phone": i % 3 != 0}, i / 10)
        alerts += new
    assert alerts == ["phone"]


def test_slow_computer():
    # Máy yếu: chỉ 1 khung hình/giây vẫn phải cảnh báo
    assert run(BehaviorRules(TIMING), {"head_down": True}, 5, fps=1) == ["head_down"]


def test_cooldown():
    alerts = run(BehaviorRules(TIMING), {"phone": True}, 20)
    assert alerts == ["phone", "phone"]  # lần 2 sau 15 giây


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("OK", name)
