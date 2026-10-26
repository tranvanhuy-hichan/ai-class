"""Kiểm tra các tình huống tối ưu hóa cho lớp học đông người."""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core import signals as sg
from core.pipeline import SpatialTracker, Pipeline, load_config
from core.rules import BehaviorRules
TIMING = {"phone": 2, "head_down": 3, "sleeping": 8, "eyes_closed": 3, "grace": 1.2, "cooldown": 15}


def test_one_shoulder_occluded_head_down():
    """Học sinh gục đầu đè lên 1 vai (vai trái bị che khuất)."""
    kpts = np.zeros((17, 3))
    # Vai trái bị khuất hoàn toàn (conf = 0.05)
    kpts[sg.L_SHOULDER] = [100, 200, 0.05]
    # Vai phải nhìn thấy (conf = 0.85)
    kpts[sg.R_SHOULDER] = [200, 200, 0.85]
    # Đầu gục thấp bằng hoặc dưới vai (y = 210)
    for i in sg.HEAD_POINTS:
        kpts[i] = [150, 210, 0.8]

    box = [80, 150, 220, 350]
    ratio = sg.head_ratio(kpts, 0.35, box)
    assert ratio is not None
    assert ratio < 0.18, f"Tỉ lệ {ratio} phải nhỏ hơn 0.18 để nhận là gục đầu"


def test_face_down_face_invisible():
    """Học sinh úp mặt hoàn toàn xuống bàn (không thấy điểm mặt nào)."""
    kpts = np.zeros((17, 3))
    kpts[sg.L_SHOULDER] = [100, 200, 0.85]
    kpts[sg.R_SHOULDER] = [200, 200, 0.85]
    # Tất cả điểm mặt conf = 0.0
    box = [80, 150, 220, 350]
    ratio = sg.head_ratio(kpts, 0.35, box)
    assert ratio == -1.0, f"Úp mặt không thấy điểm mặt nào phải trả về -1.0, nhận được: {ratio}"


def test_webcam_head_only_not_head_down():
    """Webcam cận chỉ thấy đầu (không thấy vai), mặt thấy rõ: không được suy ra là đang gục xuống bàn."""
    kpts = np.zeros((17, 3))
    kpts[sg.NOSE] = [150, 120, 0.95]
    kpts[sg.L_EYE] = [130, 100, 0.95]
    kpts[sg.R_EYE] = [170, 100, 0.95]
    kpts[sg.L_EAR] = [110, 110, 0.9]
    kpts[sg.R_EAR] = [190, 110, 0.9]
    box = [60, 40, 240, 300]
    ratio = sg.head_ratio(kpts, 0.30, box)
    assert ratio is None, f"Thấy rõ mặt mà không thấy vai thì không kết luận gục, nhận được: {ratio}"
    assert sg.face_visible(kpts)
    kpts[:5, 2] = 0.0   # úp mặt: các điểm mặt bị che
    assert sg.head_ratio(kpts, 0.30, box) == -1.0


def test_dedupe_people_merges_same_person_only():
    """Hai khung lệch nhau của CÙNG một người bị gộp, hai học sinh KHÁC nhau ngồi sát nhau thì giữ cả hai."""
    def person(cx, shift=0.0):
        k = np.zeros((17, 3))
        for i, (dx, dy) in {sg.NOSE: (0, 0), sg.L_EYE: (-15, -12), sg.R_EYE: (15, -12), sg.L_SHOULDER: (-70, 150), sg.R_SHOULDER: (70, 150),
                            sg.L_WRIST: (-90, 300), sg.R_WRIST: (90, 300)}.items():
            k[i] = [cx + dx + shift, 100 + dy, 0.9]
        return k
    box = lambda cx, w=240: np.array([cx - w / 2, 20, cx + w / 2, 400.0])
    # cùng một người: khung thứ 2 lệch 60 px, khung xương lệch 6 px
    boxes = np.array([box(300), box(360)]); kpts = np.stack([person(300), person(300, 6)])
    assert sg.dedupe_people(boxes, kpts, np.array([0.9, 0.7])) == [0]
    # hai học sinh khác nhau, khung chồng nhau ~30%, khung xương cách nhau 140 px
    boxes = np.array([box(300), box(440)]); kpts = np.stack([person(300), person(440)])
    assert sg.dedupe_people(boxes, kpts, np.array([0.9, 0.8])) == [0, 1]


def test_owner_of_detection_uses_skeleton_not_big_box():
    """Khung người của bạn ngồi sát camera rất to và chùm lên bạn nằm gục bên cạnh: phát hiện 'ngủ' phải thuộc bạn nằm gục."""
    def person(box, pts):
        k = np.zeros((17, 3))
        for i, (x, y) in zip((sg.NOSE, sg.L_SHOULDER, sg.R_SHOULDER), pts):
            k[i] = [x, y, 0.9]
        return {"id": 0, "box": np.array(box, float), "kpts": k, "signals": {}}
    boy = person([300, 100, 700, 600], [(500, 200), (400, 330), (600, 330)])      # to, bao cả vùng bên trái
    girl = person([320, 380, 460, 520], [(380, 450), (340, 470), (430, 470)])     # nhỏ, nằm gục bên trong khung của bạn nam
    boy["id"], girl["id"] = 1, 2
    det = [310, 370, 470, 530]   # khung 'ngủ' bao quanh bạn nữ
    assert sg.owner_of_detection(det, [boy, girl])["id"] == 2
    assert sg.owner_of_detection([900, 900, 950, 950], [boy, girl]) is None


def test_phone_association_wrist_vs_occluded():
    """Học sinh A đang cầm điện thoại (thấy cổ tay), học sinh B ở gần nhưng không cầm."""
    kpts_a = np.zeros((17, 3))
    kpts_a[sg.L_SHOULDER] = [100, 200, 0.8]
    kpts_a[sg.R_SHOULDER] = [180, 200, 0.8]
    kpts_a[sg.R_WRIST] = [140, 260, 0.8]  # Cổ tay ngay tại (140, 260)
    box_a = [80, 150, 200, 350]

    kpts_b = np.zeros((17, 3))
    kpts_b[sg.L_SHOULDER] = [220, 200, 0.8]
    kpts_b[sg.R_SHOULDER] = [300, 200, 0.8]
    # B không thấy cổ tay
    box_b = [200, 150, 320, 350]

    phone_point = (142, 265)  # Điện thoại gần cổ tay của A

    d_a = sg.person_phone_distance(kpts_a, box_a, phone_point, 0.35)
    d_b = sg.person_phone_distance(kpts_b, box_b, phone_point, 0.35)

    assert d_a is not None, "A phải nhận diện được khoảng cách với điện thoại"
    # Nếu B nhận được giá trị thì d_a vẫn phải nhỏ hơn d_b rất nhiều
    assert d_b is None or d_a < d_b, f"A đang cầm ({d_a}) phải ưu tiên hơn B ({d_b})"


def test_spatial_tracker_id_continuity():
    """Bộ ổn định ID phải giữ nguyên ID khi YOLO bị nhảy track ID do học sinh gục đầu."""
    tracker = SpatialTracker()

    # Frame 1: Học sinh 1 và 2 ngồi ở 2 bàn
    boxes = [np.array([100, 100, 200, 300]), np.array([300, 100, 400, 300])]
    raw_ids = [1, 2]
    ids_t1 = tracker.assign_ids(raw_ids, boxes, t=0.0)
    assert ids_t1 == [1, 2]

    # Frame 2: Học sinh 1 gục đầu -> YOLO tracker nhảy thành ID 18 tại cùng vị trí bàn
    boxes_t2 = [np.array([102, 105, 202, 305]), np.array([300, 100, 400, 300])]
    raw_ids_t2 = [18, 2]
    ids_t2 = tracker.assign_ids(raw_ids_t2, boxes_t2, t=0.5)
    assert ids_t2 == [1, 2], f"Học sinh tại bàn 1 phải được giữ ID 1, không được nhảy thành {ids_t2[0]}"

    # Frame 3: YOLO tracker tạm mất dấu ID (None) nhưng vẫn phát hiện box
    boxes_t3 = [np.array([101, 102, 200, 300]), np.array([300, 100, 400, 300])]
    ids_t3 = tracker.assign_ids(None, boxes_t3, t=1.0)
    assert ids_t3 == [1, 2], f"Khi raw_ids là None, vị trí bàn phải giữ ID [1, 2], nhận được: {ids_t3}"


if __name__ == "__main__":
    test_one_shoulder_occluded_head_down()
    print("OK test_one_shoulder_occluded_head_down")
    test_face_down_face_invisible()
    print("OK test_face_down_face_invisible")
    test_webcam_head_only_not_head_down()
    print("OK test_webcam_head_only_not_head_down")
    test_dedupe_people_merges_same_person_only()
    print("OK test_dedupe_people_merges_same_person_only")
    test_owner_of_detection_uses_skeleton_not_big_box()
    print("OK test_owner_of_detection_uses_skeleton_not_big_box")
    test_phone_association_wrist_vs_occluded()
    print("OK test_phone_association_wrist_vs_occluded")
    test_spatial_tracker_id_continuity()
    print("OK test_spatial_tracker_id_continuity")
    print("TẤT CẢ CÁC BÀI TEST TỐI ƯU LỚP HỌC ĐÃ VƯỢT QUA!")
