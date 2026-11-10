"""Chỉnh hình camera: lật, xoay, zoom, độ sáng. Chạy trước khi đưa vào AI nên khung
nhận diện và hình hiển thị luôn khớp nhau."""
import cv2

DEFAULT_VIEW = {"flip_h": True, "flip_v": False, "rotate": 0, "brightness": 0, "zoom": 1.0}


def clean_view(v):
    """Ép giá trị về khoảng hợp lệ (dữ liệu từ web không đáng tin)."""
    out = dict(DEFAULT_VIEW)
    out["flip_h"], out["flip_v"] = bool(v.get("flip_h")), bool(v.get("flip_v"))
    out["rotate"] = int(v.get("rotate", 0) or 0) // 90 % 4 * 90
    out["brightness"] = max(-80, min(80, int(float(v.get("brightness", 0) or 0))))
    out["zoom"] = max(1.0, min(3.0, round(float(v.get("zoom", 1) or 1), 2)))
    return out


def adjust(frame, v):
    """Chỉnh hình trước khi đưa vào AI: xoay, lật, phóng to giữa khung, tăng/giảm sáng.
    Chỉnh trước nên khung nhận diện và hình hiển thị luôn khớp nhau."""
    if v["rotate"]:
        frame = cv2.rotate(frame, {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180,
                                   270: cv2.ROTATE_90_COUNTERCLOCKWISE}[v["rotate"]])
    if v["flip_h"]:
        frame = cv2.flip(frame, 1)
    if v["flip_v"]:
        frame = cv2.flip(frame, 0)
    if v["zoom"] > 1:
        h, w = frame.shape[:2]
        ch, cw = int(h / v["zoom"]), int(w / v["zoom"])
        y, x = (h - ch) // 2, (w - cw) // 2
        frame = cv2.resize(frame[y:y + ch, x:x + cw], (w, h), interpolation=cv2.INTER_LINEAR)
    if v["brightness"]:
        frame = cv2.convertScaleAbs(frame, alpha=1.0 + max(v["brightness"], 0) / 160, beta=v["brightness"])
    return frame
