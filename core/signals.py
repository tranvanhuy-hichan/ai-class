"""Tính các tín hiệu tức thời từ khung xương (keypoints) của 1 người.

Thứ tự 17 điểm khung xương chuẩn COCO mà YOLO-pose trả về:
  0 mũi, 1 mắt trái, 2 mắt phải, 3 tai trái, 4 tai phải,
  5 vai trái, 6 vai phải, 7 khuỷu trái, 8 khuỷu phải, 9 cổ tay trái, 10 cổ tay phải,
  11 hông trái, 12 hông phải, ...
"""
import numpy as np

NOSE, L_EYE, R_EYE, L_EAR, R_EAR = 0, 1, 2, 3, 4
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
HEAD_POINTS = (NOSE, L_EYE, R_EYE, L_EAR, R_EAR)


def shoulders(kpts, thr, box=None):
    """Trả về (y trung bình của vai, độ rộng vai) hoặc None nếu không đủ thông tin.

    Hỗ trợ lớp học đông người:
    - Tính khoảng cách Euclidean chuẩn giữa 2 vai (không bị lỗi khi ngồi nghiêng).
    - Ngưỡng mềm cho học sinh ngồi xa/bàn cuối.
    - Dự phòng khi 1 bên vai bị che khuất (dùng vai còn lại + bounding box).
    """
    ls, rs = kpts[L_SHOULDER], kpts[R_SHOULDER]
    soft_thr = max(0.18, thr * 0.6)

    # 1. Cả 2 vai đều nhìn thấy với độ tin cậy tốt
    if ls[2] >= thr and rs[2] >= thr:
        w = float(np.hypot(ls[0] - rs[0], ls[1] - rs[1]))
        if w >= 5:
            return float((ls[1] + rs[1]) / 2), w
        if box is not None:
            return float((ls[1] + rs[1]) / 2), float(max(10.0, (box[2] - box[0]) * 0.55))

    # 2. Cả 2 vai nhìn thấy ở ngưỡng mềm (học sinh ở xa trong lớp học đông)
    if ls[2] >= soft_thr and rs[2] >= soft_thr:
        w = float(np.hypot(ls[0] - rs[0], ls[1] - rs[1]))
        if w >= 5:
            return float((ls[1] + rs[1]) / 2), w
        if box is not None:
            return float((ls[1] + rs[1]) / 2), float(max(10.0, (box[2] - box[0]) * 0.55))

    # 3. Một bên vai bị bàn ghế / tư thế gục đè lên che khuất
    if box is not None:
        bw = float(max(10.0, (box[2] - box[0]) * 0.55))
        if ls[2] >= soft_thr and rs[2] < soft_thr:
            return float(ls[1]), bw
        if rs[2] >= soft_thr and ls[2] < soft_thr:
            return float(rs[1]), bw
        # Cả 2 vai đều bị khuất sâu khi gục úp xuống bàn: ước tính vị trí vai từ box
        est_y = float(box[1] + 0.25 * (box[3] - box[1]))
        return est_y, bw

    return None


def face_visible(kpts, conf=0.6, min_points=4):
    """Mặt đang quay về phía camera và thấy rõ: ít nhất `min_points` trong 5 điểm (mũi, 2 mắt, 2 tai) có độ tin cậy cao.
    Người nằm gục úp mặt xuống bàn thì các điểm này bị che nên không đạt."""
    return sum(1 for i in HEAD_POINTS if kpts[i][2] >= conf) >= min_points


def head_ratio(kpts, thr, box=None):
    """Đầu cao hơn vai bao nhiêu, tính theo đơn vị "độ rộng vai".

    Ngồi thẳng: ~0.5-1.0. Cúi đọc/viết bài: vẫn dương (đầu còn cao hơn vai). Nằm gục xuống bàn: <= 0 (đầu ngang hoặc thấp hơn vai).
    Thấy vai mà không thấy điểm nào trên mặt -> mặt đang úp xuống bàn -> trả về -1.0.
    Nếu học sinh gục thấp trong khung người -> trả về <= 0.
    """
    sh = shoulders(kpts, thr, box)
    if sh is None:
        if box is not None:
            # Dự phòng theo bounding box nếu mất cả 2 vai
            head = [kpts[i] for i in HEAD_POINTS if kpts[i][2] >= max(0.18, thr * 0.6)]
            if not head:
                return -1.0
            head_y = float(np.mean([p[1] for p in head]))
            box_h = max(1.0, box[3] - box[1])
            if (head_y - box[1]) / box_h > 0.45:
                return 0.0
        return None

    shoulder_y, width = sh
    head = [kpts[i] for i in HEAD_POINTS if kpts[i][2] >= thr]
    if not head:
        head = [kpts[i] for i in HEAD_POINTS if kpts[i][2] >= max(0.18, thr * 0.6)]

    if not head:
        return -1.0

    head_y = float(np.mean([p[1] for p in head]))
    ratio = float((shoulder_y - head_y) / max(width, 1.0))

    # Kiểm tra vị trí đầu so với bounding box:
    # Nếu đầu chìm xuống quá nửa thân trên -> tư thế gục sâu
    if box is not None:
        box_h = max(1.0, box[3] - box[1])
        head_rel_y = (head_y - box[1]) / box_h
        if head_rel_y > 0.45:
            return min(ratio, 0.0)

    return ratio


def wrist_distance(kpts, point, thr, box=None):
    """Khoảng cách từ point tới cổ tay gần nhất, chia cho độ rộng vai.

    Trả về None nếu không thấy cổ tay hoặc không đủ thông tin độ rộng.
    """
    sh = shoulders(kpts, thr, box)
    soft_thr = max(0.18, thr * 0.6)
    wrists = [kpts[i] for i in (L_WRIST, R_WRIST) if kpts[i][2] >= soft_thr]
    if sh is None or not wrists:
        return None
    d = min(np.hypot(w[0] - point[0], w[1] - point[1]) for w in wrists)
    return float(d / max(sh[1], 1.0))


def person_phone_distance(kpts, box, phone_point, thr, wrist_factor=0.8):
    """Đo khoảng cách liên kết tối ưu giữa điện thoại và học sinh.

    Trả về khoảng cách chuẩn hóa (càng nhỏ càng gần tay/bàn học sinh) hoặc None
    nếu nằm ngoài vùng tương tác cho phép.
    """
    sh = shoulders(kpts, thr, box)
    w_box = max(15.0, (box[2] - box[0]) * 0.55)
    scale = sh[1] if (sh is not None and sh[1] >= 10) else w_box

    soft_thr = max(0.18, thr * 0.6)
    px, py = phone_point

    # 1. Cổ tay (ưu tiên cao nhất)
    wrists = [kpts[i] for i in (L_WRIST, R_WRIST) if kpts[i][2] >= soft_thr]
    if wrists:
        d_wrist = min(np.hypot(w[0] - px, w[1] - py) for w in wrists) / scale
        if d_wrist <= wrist_factor:
            return float(d_wrist)

    # 2. Khuỷu tay (khi cổ tay bị mép bàn che khuất)
    elbows = [kpts[i] for i in (L_ELBOW, R_ELBOW) if kpts[i][2] >= soft_thr]
    if elbows:
        d_elbow = min(np.hypot(e[0] - px, e[1] - py) for e in elbows) / scale
        if d_elbow <= wrist_factor * 1.3:
            return float(d_elbow + 0.15)

    # 3. Vùng tay/lòng bàn học (nửa dưới của box người)
    lap_x = (box[0] + box[2]) / 2
    lap_y = box[1] + 0.75 * (box[3] - box[1])
    d_lap = np.hypot(lap_x - px, lap_y - py) / scale
    if d_lap <= wrist_factor * 1.4:
        return float(d_lap + 0.30)

    return None


def eye_crops(frame, kpts, thr, min_dist):
    """Cắt ảnh 2 mắt quanh điểm mắt trái/phải. Trả về [] nếu mặt quá nhỏ."""
    soft_thr = max(0.18, thr * 0.6)
    le, re = kpts[L_EYE], kpts[R_EYE]
    if le[2] < soft_thr or re[2] < soft_thr:
        return []
    d = np.hypot(le[0] - re[0], le[1] - re[1])
    if d < min_dist:
        return []
    half = int(0.5 * d)
    h, w = frame.shape[:2]
    crops = []
    for x, y in ((le[0], le[1] - 0.1 * d), (re[0], re[1] - 0.1 * d)):
        x0, y0 = max(int(x) - half, 0), max(int(y) - half, 0)
        x1, y1 = min(int(x) + half, w), min(int(y) + half, h)
        if x1 - x0 > 4 and y1 - y0 > 4:
            crops.append(frame[y0:y1, x0:x1])
    return crops


def head_box(frame, kpts, thr, min_dist):
    """Vùng vuông quanh đầu. Hỗ trợ cả khi một bên mắt bị khuất hoặc mặt nghiêng."""
    soft_thr = max(0.18, thr * 0.6)
    le, re = kpts[L_EYE], kpts[R_EYE]

    # Cả 2 mắt đều thấy
    if le[2] >= soft_thr and re[2] >= soft_thr:
        d = np.hypot(le[0] - re[0], le[1] - re[1])
        if d >= min_dist:
            cx, cy = (le[0] + re[0]) / 2, (le[1] + re[1]) / 2 + 0.3 * d
            half = 2.0 * d
            h, w = frame.shape[:2]
            x0, y0 = int(max(cx - half, 0)), int(max(cy - half, 0))
            x1, y1 = int(min(cx + half, w)), int(min(cy + half, h))
            if x1 - x0 >= 20 and y1 - y0 >= 20:
                return x0, y0, x1, y1

    # Mặt nghiêng: thấy mũi và 1 mắt
    nose = kpts[NOSE]
    if nose[2] >= soft_thr:
        eye = le if le[2] >= soft_thr else re if re[2] >= soft_thr else None
        if eye is not None:
            d = max(min_dist, np.hypot(nose[0] - eye[0], nose[1] - eye[1]) * 1.8)
            cx, cy = nose[0], nose[1]
            half = 1.8 * d
            h, w = frame.shape[:2]
            x0, y0 = int(max(cx - half, 0)), int(max(cy - half, 0))
            x1, y1 = int(min(cx + half, w)), int(min(cy + half, h))
            if x1 - x0 >= 20 and y1 - y0 >= 20:
                return x0, y0, x1, y1

    return None


def contains(box, point, pad=0.1):
    """Điểm có nằm trong khung (mở rộng thêm pad %) không."""
    x0, y0, x1, y1 = box
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    return x0 - px <= point[0] <= x1 + px and y0 - py <= point[1] <= y1 + py


def interaction_box(box, pad_x=0.55, pad_top=0.10, pad_bottom=0.65):
    """Vùng tương tác mở rộng quanh học sinh (bao gồm hai bên tay, mặt bàn và lòng đùi)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    return [x0 - pad_x * w, y0 - pad_top * h, x1 + pad_x * w, y1 + pad_bottom * h]


def center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def box_iou(b1, b2):
    """Tính Intersection over Union giữa 2 bounding box [x0, y0, x1, y1]."""
    ix0 = max(b1[0], b2[0])
    iy0 = max(b1[1], b2[1])
    ix1 = min(b1[2], b2[2])
    iy1 = min(b1[3], b2[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    if inter == 0.0:
        return 0.0
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0
