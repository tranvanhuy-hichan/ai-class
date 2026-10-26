"""Kiểm tra bộ phát hiện đánh nhau bằng khung xương dựng sẵn (không cần camera)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import signals as sg
from core.fight import FightDetector
from core.rules import BehaviorRules

TIMING = {"phone": 2, "head_down": 3, "sleeping": 8, "eyes_closed": 3, "grace": 1.2, "cooldown": 15,
          "fighting": 1.0}


def person(pid, cx, wrist_l=None, wrist_r=None, width=100):
    """Học sinh ngồi tâm cx; vai rộng `width` px, khung cao 300 px. Cổ tay mặc định để dọc thân."""
    kp = np.zeros((17, 3))
    kp[sg.L_SHOULDER] = [cx - width / 2, 120, 0.9]
    kp[sg.R_SHOULDER] = [cx + width / 2, 120, 0.9]
    kp[sg.L_WRIST] = [*(wrist_l or (cx - width / 2, 260)), 0.9]
    kp[sg.R_WRIST] = [*(wrist_r or (cx + width / 2, 260)), 0.9]
    box = np.array([cx - width * 0.8, 50, cx + width * 0.8, 350.0])
    return {"id": pid, "box": box, "kpts": kp, "signals": {}}


def run(frames, fps, det=None):
    """frames: hàm (i, t) -> list people. Trả về thời điểm đầu tiên có cảnh báo (hoặc None)."""
    det, rules = det or FightDetector(), BehaviorRules(TIMING)
    for i in range(int(6 * fps)):
        t = i / fps
        people = frames(i, t)
        det.update(people, t)
        for p in people:
            active, _ = rules.update(p["id"], p["signals"], t)
            if "fighting" in active:
                return t
    return None


def punching(i, t):
    """B ngồi sát A; A liên tục vung nắm đấm qua lại vào ngực B (tay đi 1 vòng 0.3 s)."""
    tt = t + 0.04 * np.sin(t * 7)               # nhịp vung không đều như thật (tránh trùng nhịp lấy mẫu)
    phase = (tt % 0.37) / 0.37
    x = 150 + 110 * (phase * 2 if phase < 0.5 else 2 - phase * 2)   # từ vai A vào ngực B và về
    return [person(1, 100, wrist_r=(x, 200)), person(2, 230)]


def waving(i, t):
    """A vẫy tay trên cao rất nhanh nhưng không chạm ai."""
    x = 100 + 60 * np.sin(t * 12)
    return [person(1, 100, wrist_r=(x, 40)), person(2, 400)]


def passing_pen(i, t):
    """A đưa tay sang B đúng một lần rồi rút về (đưa bút)."""
    x = 100 + (130 if 2.0 < t < 2.4 else 0)
    return [person(1, 100, wrist_r=(x, 200)), person(2, 230)]


def solo_flailing(i, t):
    """Chỉ MỘT học sinh vung tay rất mạnh, người bên cạnh ngồi yên và không bị chạm: không phải đánh nhau."""
    tt = t + 0.04 * np.sin(t * 7)
    phase = (tt % 0.37) / 0.37
    x = 150 + 110 * (phase * 2 if phase < 0.5 else 2 - phase * 2)
    return [person(1, 100, wrist_r=(x, 40)), person(2, 230)]


def chatting_close(i, t):
    """Hai bạn ngồi sát nhau vừa nói chuyện vừa múa tay nhanh trên bàn, tay lướt qua người bạn bên cạnh."""
    xa = 100 + 70 * np.sin(t * 9)
    xb = 230 - 70 * np.sin(t * 8 + 1)
    return [person(1, 100, wrist_r=(xa, 220)), person(2, 190, wrist_l=(xb, 220))]


def idle(i, t):
    return [person(1, 100), person(2, 230)]


def test_punching_detected_at_various_fps():
    for fps in (5, 8, 10, 25):
        assert run(punching, fps) is not None, f"fps={fps}: phải phát hiện đánh nhau"
    print("OK test_punching_detected_at_various_fps")


def test_waving_not_fight():
    for fps in (5, 10, 25):
        assert run(waving, fps) is None, f"fps={fps}: vẫy tay không phải đánh nhau"
    print("OK test_waving_not_fight")


def test_solo_flailing_not_fight():
    for fps in (5, 10, 25):
        assert run(solo_flailing, fps) is None, f"fps={fps}: một người vung tay không phải đánh nhau"
    print("OK test_solo_flailing_not_fight")


def test_passing_pen_and_idle_not_fight():
    for fps in (5, 10, 25):
        assert run(passing_pen, fps) is None, "đưa bút 1 lần không phải đánh nhau"
        assert run(idle, fps) is None
    print("OK test_passing_pen_and_idle_not_fight")


def test_scale_invariant_far_students():
    """Học sinh ở xa (nhỏ gấp 3) vẫn bắt được vì tốc độ tính theo độ rộng vai."""
    def far(i, t):
        tt = t + 0.04 * np.sin(t * 7)
        phase = (tt % 0.37) / 0.37
        x = (150 + 110 * (phase * 2 if phase < 0.5 else 2 - phase * 2)) / 3
        a, b = person(1, 100 / 3, width=33), person(2, 230 / 3, width=33)
        a["kpts"][sg.R_WRIST] = [x, 200 / 3 + 20, 0.9]
        for p in (a, b):
            p["box"][[1, 3]] /= 3   # person() đã thu nhỏ theo chiều ngang, chỉ còn chiều cao
        return [a, b]
    assert run(far, 10) is not None
    print("OK test_scale_invariant_far_students")


def test_chatting_close_not_fight():
    for fps in (5, 8, 10, 25):
        assert run(chatting_close, fps) is None, f"fps={fps}: ngồi sát múa tay trò chuyện không phải đánh nhau"
    print("OK test_chatting_close_not_fight")


def test_keypoint_glitch_ignored():
    """Khung xương nhảy 1 khung hình rất xa (nhiễu) không được coi là cú đánh."""
    def glitch(i, t):
        x = 3000 if i == 20 else 100
        return [person(1, 100, wrist_r=(x, 200)), person(2, 230)]
    assert run(glitch, 10) is None
    print("OK test_keypoint_glitch_ignored")


def test_fight_marks_both_and_resets():
    det = FightDetector()
    for i in range(30):
        t = i * 0.1
        people = punching(i, t)
        pairs = det.update(people, t)
    assert pairs == [(1, 2)]
    assert people[0]["signals"]["fighting"] and people[1]["signals"]["fighting"]
    assert people[0]["fight_with"] == 2 and people[1]["fight_with"] == 1
    det.reset()
    assert det.update(idle(0, 0.0), 0.0) == []
    print("OK test_fight_marks_both_and_resets")


if __name__ == "__main__":
    test_punching_detected_at_various_fps()
    test_waving_not_fight()
    test_solo_flailing_not_fight()
    test_passing_pen_and_idle_not_fight()
    test_scale_invariant_far_students()
    test_chatting_close_not_fight()
    test_keypoint_glitch_ignored()
    test_fight_marks_both_and_resets()
    print("TẤT CẢ TEST ĐÁNH NHAU ĐÃ VƯỢT QUA!")
