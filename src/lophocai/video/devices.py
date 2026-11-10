"""Dò các webcam đang cắm vào máy."""
import cv2

_cache = None


def list_cameras(engine=None, max_index=4):
    """Số thứ tự các webcam đang cắm (chỉ dò 1 lần vì mở camera khá chậm)."""
    global _cache
    if _cache is None:
        found = []
        for i in range(max_index):
            if engine and any(c.running and c.source == str(i) for c in engine.cameras.values()):
                found.append(i)  # đang dùng thì không mở lại được, nhưng chắc chắn có
                continue
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                found.append(i)
            cap.release()
        _cache = found
    return _cache
