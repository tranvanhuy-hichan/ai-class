"""Ghép các mô hình AI + luật thành 1 hệ thống hoàn chỉnh.

Mỗi khung hình đi qua các bước:
  1. YOLO-pose: tìm người, gán ID theo dõi (tracking), lấy 17 điểm khung xương
  2. SpatialTracker: ổn định ID học sinh theo vị trí bàn học (chống nhảy ID khi gục đầu)
  3. YOLO (COCO): tìm điện thoại -> gán cho học sinh trong vùng tương tác bàn/tay
  4. MediaPipe (hoặc mô hình mắt tự huấn luyện): mắt mở hay nhắm
  5. (Tuỳ chọn) Mô hình hành vi tự huấn luyện
  6. Luật thời gian -> quyết định có cảnh báo hay không
"""
import time
from pathlib import Path

import cv2
import numpy as np
import yaml
from ultralytics import YOLO

from . import signals as sg
from .fight import FightDetector
from .paths import res
from .rules import BehaviorRules

COCO_PHONE = 67  # chỉ số lớp "cell phone" trong bộ COCO


FACE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                  "face_landmarker/float16/1/face_landmarker.task")


def load_face_landmarker(path):
    try:
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError:
        print("[!] Chưa cài mediapipe (pip install mediapipe) -> tắt phát hiện nhắm mắt")
        return None
    if not Path(path).exists():
        import urllib.request
        print(f"[i] Đang tải mô hình khuôn mặt về {path} ...")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(FACE_MODEL_URL, path)
    return vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(path)), output_face_blendshapes=True,
        num_faces=1, running_mode=vision.RunningMode.IMAGE))


def load_config(path="config.yaml"):
    with open(res(path), encoding="utf-8") as f:
        return yaml.safe_load(f)


def desk_match_score(b1, b2):
    """Tính độ tương đồng vị trí người ngồi giữa 2 khung hình (hỗ trợ cả khi đổi tư thế gục)."""
    # 1. 2D IoU
    iou = sg.box_iou(b1, b2)
    if iou >= 0.20:
        return iou
    # 2. Độ trùng lặp trục ngang (X-overlap) khi học sinh ngồi cùng một cột bàn
    ix0 = max(b1[0], b2[0])
    ix1 = min(b1[2], b2[2])
    inter_w = max(0.0, ix1 - ix0)
    union_w = max(b1[2], b2[2]) - min(b1[0], b2[0])
    x_overlap = inter_w / union_w if union_w > 0 else 0.0

    c1 = sg.center(b1)
    c2 = sg.center(b2)
    avg_h = ((b1[3] - b1[1]) + (b2[3] - b2[1])) / 2
    y_dist = abs(c1[1] - c2[1])

    if x_overlap >= 0.40 and y_dist < 1.2 * avg_h:
        return 0.4 + 0.6 * x_overlap
    return 0.0


class SpatialTracker:
    """Ổn định ID học sinh trong lớp học dựa trên vị trí ngồi cố định tại bàn.

    Giải quyết triệt để các vấn đề trong lớp đông người:
    - Tracker của YOLO bị nhảy ID (ID switch) khi học sinh gục đầu/úp mặt xuống bàn.
    - Bộ đếm thời gian (vd: 10s ngủ gục) bị reset về 0 do ID đổi đột ngột.
    - Một số khung hình tracker chưa kịp gán ID (boxes.id is None).
    """

    def __init__(self, iou_thresh=0.25, max_lost_sec=15.0):
        self.iou_thresh = iou_thresh
        self.max_lost_sec = max_lost_sec
        # track_id -> {"box": [x0,y0,x1,y1], "last_seen": t}
        self.active_tracks = {}
        # yolo_id -> stable_id
        self.yolo_to_stable = {}
        self.next_fallback_id = 1

    def reset(self):
        self.active_tracks.clear()
        self.yolo_to_stable.clear()
        self.next_fallback_id = 1

    def assign_ids(self, raw_ids, boxes, t):
        """Gán ID ổn định cho danh sách boxes tại thời điểm t."""
        # 1. Dọn dẹp các track đã biến mất quá max_lost_sec (15 giây)
        for tid in [k for k, v in list(self.active_tracks.items()) if t - v["last_seen"] > self.max_lost_sec]:
            del self.active_tracks[tid]
            for y_id in [yk for yk, sv in list(self.yolo_to_stable.items()) if sv == tid]:
                del self.yolo_to_stable[y_id]

        stable_ids = []
        used_stable_ids = set()

        for i, box in enumerate(boxes):
            raw_id = raw_ids[i] if (raw_ids is not None and i < len(raw_ids)) else None
            assigned_id = None

            # A. Nếu raw_id đã được map trước đó và còn gần vị trí cũ
            if raw_id is not None and raw_id in self.yolo_to_stable:
                cand_id = self.yolo_to_stable[raw_id]
                if cand_id not in used_stable_ids and cand_id in self.active_tracks:
                    score = desk_match_score(box, self.active_tracks[cand_id]["box"])
                    if score >= 0.20:
                        assigned_id = cand_id

            # B. Nếu chưa có: tìm trong active_tracks xem có học sinh nào ở cùng vị trí bàn này không
            if assigned_id is None:
                best_id, best_score = None, 0.0
                for s_id, data in self.active_tracks.items():
                    if s_id in used_stable_ids:
                        continue
                    score = desk_match_score(box, data["box"])
                    if score > best_score and score >= self.iou_thresh:
                        best_score, best_id = score, s_id
                if best_id is not None:
                    assigned_id = best_id
                    if raw_id is not None:
                        self.yolo_to_stable[raw_id] = assigned_id

            # C. Nếu vẫn chưa có: ưu tiên tái sử dụng ID nhỏ hoặc cấp ID tiếp theo
            if assigned_id is None:
                if raw_id is not None and raw_id not in self.active_tracks:
                    assigned_id = raw_id
                else:
                    # Tìm ID nhỏ nhất chưa dùng
                    cur_ids = set(self.active_tracks.keys()) | used_stable_ids
                    new_id = 1
                    while new_id in cur_ids:
                        new_id += 1
                    assigned_id = new_id

                if raw_id is not None:
                    self.yolo_to_stable[raw_id] = assigned_id

            used_stable_ids.add(assigned_id)
            stable_ids.append(assigned_id)
            self.active_tracks[assigned_id] = {"box": box, "last_seen": t}

        return stable_ids


ALL_BEHAVIORS = ("phone", "head_down", "sleeping", "eyes_closed", "fighting", "smoking")


def mode_behaviors(cfg, mode):
    """Các hành vi được theo dõi ở chế độ `mode` (config.yaml, mục modes). Không có chế độ -> theo dõi tất cả."""
    mc = (cfg.get("modes") or {}).get(mode) if mode else None
    return set(mc["behaviors"]) if mc and mc.get("behaviors") else set(ALL_BEHAVIORS)


class Pipeline:
    def __init__(self, cfg, mode=None):
        """mode: tên chế độ trong config.yaml (vd "lop", "hanhlang"). Chỉ nạp và chạy các mô hình mà chế độ đó cần."""
        self.cfg = cfg
        self.mode = mode
        self.behaviors = mode_behaviors(cfg, mode)
        mc = (cfg.get("modes") or {}).get(mode) or {}
        m = cfg["models"]
        self.device = m.get("device") or None
        import torch
        self.has_cuda = torch.cuda.is_available() if not self.device else (str(self.device).lower() not in ("cpu", "-1"))
        if not self.has_cuda:
            print("[i] Đang chạy chế độ CPU (máy không có GPU) - áp dụng bộ tối ưu tiết kiệm tài nguyên.")

        self.pose = YOLO(str(res(m["pose"])))
        self.obj = YOLO(str(res(m["object"]))) if "phone" in self.behaviors else None   # chỉ dùng để tìm điện thoại

        self.eye = self.face = None
        method = m.get("eye_method", "mediapipe") if "eyes_closed" in self.behaviors else "off"
        if method == "mediapipe":
            self.face = load_face_landmarker(res(m.get("face_landmarker", "weights/face_landmarker.task")))
        elif method == "classifier" and res(m["eye_classifier"]).exists():
            self.eye = YOLO(str(res(m["eye_classifier"])))
            names = {v.lower(): k for k, v in self.eye.names.items()}
            self.closed_idx = names.get("closed", 0)
            print(f"[i] Đã nạp mô hình mắt: {m['eye_classifier']}")

        self.custom = None
        custom_path = mc.get("custom_behavior") or m.get("custom_behavior")
        if custom_path and res(custom_path).exists():
            model = YOLO(str(res(custom_path)))
            cmap = {k.lower(): v for k, v in cfg.get("custom_class_map", {}).items()}
            # Bỏ các lớp thuộc hành vi mà chế độ này không theo dõi (vd chế độ hành lang bỏ phone, sleep)
            cmap_mode = {i: cmap.get(n.lower()) for i, n in model.names.items()}
            self.custom_map = {i: (b if b in self.behaviors or (b == "sleeping" and "head_down" in self.behaviors) else None)
                               for i, b in cmap_mode.items()}
            if any(self.custom_map.values()):
                self.custom = model
                print(f"[i] Đã nạp mô hình hành vi: {custom_path} -> {self.custom_map}")

        self.tracker = SpatialTracker()
        self.rules = BehaviorRules(cfg["timing"])
        self.fight = FightDetector({"keypoint_conf": cfg["detection"]["keypoint_conf"], **cfg.get("fight", {})})

        # Máy yếu: các mô hình phụ (điện thoại, hành vi, mắt) không cần chạy ở mọi khung hình vì hành vi
        # kéo dài nhiều giây. Chạy thưa hơn và dùng lại kết quả cũ giữa 2 lần chạy.
        perf = cfg.get("performance", {})
        self.aux_interval = perf.get("aux_interval_gpu" if self.has_cuda else "aux_interval_cpu", 0.0)
        self.eye_interval = perf.get("eye_interval_gpu" if self.has_cuda else "eye_interval_cpu", 0.0)
        self.budget = perf.get("frame_budget_ms", 0) / 1000.0  # 0 = tắt tự giãn khi máy chậm
        self._clear_cache()

    def _clear_cache(self):
        self._phone_cache = ([], None)    # (danh sách khung điện thoại, thời điểm chạy)
        self._custom_cache = ([], None)   # (danh sách (khung, lớp), thời điểm chạy)
        self._eye_cache = {}              # id -> (xác suất nhắm, thời điểm đo)
        self._load = 1.0                  # hệ số giãn cách, tăng khi máy không theo kịp

    @staticmethod
    def _due(last_t, t, interval):
        return last_t is None or t < last_t or t - last_t >= interval

    def reset(self):
        """Gọi khi chuyển sang video mới hoặc đổi camera."""
        self.rules = BehaviorRules(self.cfg["timing"])
        self.tracker.reset()
        self.fight.reset()
        self._clear_cache()
        self.pose.predictor = None  # tạo lại bộ theo dõi (ID) từ đầu

    # ------------------------------------------------------------------
    def process(self, frame, t):
        """Xử lý 1 khung hình tại thời điểm t (giây).

        Trả về (people, alerts):
          people - list dict {id, box, kpts, signals, active}
          alerts - list dict {id, behavior, duration, box}
        """
        det, r = self.cfg["detection"], self.cfg["rules"]
        thr = det["keypoint_conf"]
        started = time.perf_counter()

        # Sử dụng bytetrack để theo dõi ổn định và mượt mà hơn trong lớp học
        res = self.pose.track(frame, persist=True, conf=det["person_conf"], imgsz=det["imgsz"],
                              tracker="bytetrack.yaml", device=self.device, verbose=False)[0]
        people = []
        if res.boxes is not None and len(res.boxes) > 0:
            boxes = res.boxes.xyxy.cpu().numpy()
            raw_ids = res.boxes.id.int().cpu().tolist() if res.boxes.id is not None else None
            kpts = res.keypoints.data.cpu().numpy()  # (N, 17, 3)
            ids = self.tracker.assign_ids(raw_ids, boxes, t)

            for tid, box, kp in zip(ids, boxes, kpts):
                # Loại bỏ các vật tĩnh như áo khoác treo tường không có điểm khung xương đáng tin
                if np.max(kp[:, 2]) < 0.40:
                    continue
                ratio = sg.head_ratio(kp, thr, box)
                is_head_down = "head_down" in self.behaviors and ratio is not None and ratio < r["head_down_ratio"]
                people.append({
                    "id": tid, "box": box, "kpts": kp, "head_ratio": ratio,
                    "signals": {"head_down": is_head_down},
                })

        if "fighting" in self.behaviors:
            self.fight.update(people, t)   # khung xương đã có sẵn nên gần như không tốn thêm thời gian

        if people:
            if self.obj is not None:
                self._detect_phones(frame, people, det, r, thr, t)
            if self.face is not None:
                self._check_eyes_mediapipe(frame, people, r, thr, t)
            elif self.eye is not None:
                self._check_eyes(frame, people, r, thr)
            if self.custom is not None:
                self._custom_behaviors(frame, people, det, t)

        for p in people:
            # Đang vật nhau/xô đẩy thì đầu cúi, mắt híp hay nhắm không phải gục hay ngủ: bỏ để khỏi báo nhầm
            if p["signals"].get("fighting"):
                p["signals"].pop("eyes_closed", None)
                p["signals"].pop("head_down", None)

        alerts = []
        for p in people:
            p["active"], new = self.rules.update(p["id"], p["signals"], t)
            for b in new:
                alerts.append({"id": p["id"], "behavior": b, "duration": p["active"][b], "box": p["box"]})
        self.rules.forget_old(t)
        self._adapt(time.perf_counter() - started)
        return people, alerts

    def _adapt(self, elapsed):
        """Máy chậm hơn ngân sách thời gian thì giãn thêm các mô hình phụ (tối đa x4); đỡ lại thì thu hẹp dần."""
        if self.budget <= 0:
            return
        if elapsed > self.budget:
            self._load = min(4.0, self._load * 1.25)
        else:
            self._load = max(1.0, self._load * 0.95)

    # ------------------------------------------------------------------
    def _detect_phones(self, frame, people, det, r, thr, t):
        """Nhận diện điện thoại và liên kết với học sinh tương ứng."""
        boxes, last = self._phone_cache
        if self._due(last, t, self.aux_interval * self._load):
            phone_conf = det.get("phone_conf", 0.15)
            res = self.obj.predict(frame, classes=[COCO_PHONE], conf=phone_conf, imgsz=det["imgsz"],
                                   device=self.device, verbose=False)[0]
            boxes = res.boxes.xyxy.cpu().numpy() if res.boxes is not None and len(res.boxes) else []
            self._phone_cache = (boxes, t)

        for box in boxes:
            c = sg.center(box)
            best_person = None
            best_dist = float("inf")

            for p in people:
                # 1. Kiểm tra xem điện thoại có nằm trong vùng tương tác (hai bên tay, bàn, lòng) không
                izone = sg.interaction_box(p["box"])
                if not sg.contains(izone, c, pad=0.0):
                    continue

                # 2. Đo khoảng cách tối ưu tới tay/khuỷu tay/bàn học sinh
                d = sg.person_phone_distance(p["kpts"], p["box"], c, thr, r.get("phone_wrist_factor", 1.2))
                if d is not None and d < best_dist:
                    best_person = p
                    best_dist = d
                elif d is None:
                    # Nếu điểm xương tay bị khuất (vd cận cảnh webcam) nhưng điện thoại nằm trong vùng tương tác
                    c_person = sg.center(p["box"])
                    norm_w = max(20.0, (p["box"][2] - p["box"][0]))
                    dist_to_person = np.hypot(c_person[0] - c[0], c_person[1] - c[1]) / norm_w
                    if dist_to_person < 1.8 and dist_to_person < best_dist:
                        best_person = p
                        best_dist = dist_to_person

            if best_person is not None:
                best_person["signals"]["phone"] = True
                best_person.setdefault("phone_boxes", []).append(box)

    def _check_eyes_mediapipe(self, frame, people, r, thr, t):
        """Kiểm tra nhắm mắt bằng MediaPipe. Bỏ qua học sinh đã gục đầu để tiết kiệm tài nguyên."""
        import mediapipe as mp
        min_eye_dist = r.get("min_eye_distance_px", 16)
        max_faces_per_frame = 4 if not self.has_cuda else 20
        checked_faces = 0
        interval = self.eye_interval * self._load
        alive = {p["id"] for p in people}
        self._eye_cache = {k: v for k, v in self._eye_cache.items() if k in alive}

        # Người có số đo cũ nhất được đo trước, để lớp đông thì mọi người đều lần lượt được đo
        for p in sorted(people, key=lambda p: self._eye_cache.get(p["id"], (0, -1e9))[1]):
            # Học sinh đã gục đầu thì chắc chắn đang gục/ngủ, không cần chạy MediaPipe
            if p["signals"].get("head_down"):
                continue
            cached = self._eye_cache.get(p["id"])
            if cached is not None and not self._due(cached[1], t, interval):
                p["eye_closed_prob"] = cached[0]
                p["signals"]["eyes_closed"] = cached[0] > r["blink_threshold"]
                continue
            if checked_faces >= max_faces_per_frame:
                continue

            box = sg.head_box(frame, p["kpts"], thr, min_eye_dist)
            if box is None:
                continue
            x0, y0, x1, y1 = box
            head = cv2.resize(frame[y0:y1, x0:x1], (256, 256))
            res = self.face.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                            data=cv2.cvtColor(head, cv2.COLOR_BGR2RGB)))
            checked_faces += 1
            if not res.face_blendshapes:
                continue
            score = {b.category_name: b.score for b in res.face_blendshapes[0]}
            closed = (score.get("eyeBlinkLeft", 0.0) + score.get("eyeBlinkRight", 0.0)) / 2
            self._eye_cache[p["id"]] = (closed, t)
            p["eye_closed_prob"] = closed
            p["signals"]["eyes_closed"] = closed > r["blink_threshold"]

    def _check_eyes(self, frame, people, r, thr):
        min_eye_dist = r.get("min_eye_distance_px", 16)
        for p in people:
            if p["signals"].get("head_down"):
                continue
            crops = sg.eye_crops(frame, p["kpts"], thr, min_eye_dist)
            if not crops:
                continue
            crops = [cv2.cvtColor(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR) for c in crops]
            outs = self.eye.predict(crops, imgsz=64, device=self.device, verbose=False)
            prob = sum(float(o.probs.data[self.closed_idx]) for o in outs) / len(outs)
            p["eye_closed_prob"] = prob
            p["signals"]["eyes_closed"] = prob > r["eye_closed_prob"]

    def _custom_behaviors(self, frame, people, det, t):
        dets, last = self._custom_cache
        if self._due(last, t, self.aux_interval * self._load):
            # Điếu thuốc nhỏ nên điểm tin cậy thấp hơn các hành vi khác: chạy với ngưỡng thấp nhất rồi lọc từng lớp
            smoke_conf = det.get("smoking_conf", 0.30)
            per_class = det.get("custom_conf", {})   # ngưỡng riêng từng hành vi, vd phone cao hơn để bớt báo nhầm
            res = self.custom.predict(frame, conf=min([det["person_conf"], smoke_conf, *per_class.values()]),
                                      imgsz=det["imgsz"], device=self.device, verbose=False)[0]
            dets = []
            if res.boxes is not None and len(res.boxes):
                for box, cls, cf in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.cls.int().cpu().tolist(),
                                        res.boxes.conf.cpu().tolist()):
                    behavior = self.custom_map.get(cls)
                    need = per_class.get(behavior, smoke_conf if behavior == "smoking" else det["person_conf"])
                    if cf >= need:
                        dets.append((box, cls))
            self._custom_cache = (dets, t)
        for box, cls in dets:
            behavior = self.custom_map.get(cls)
            if not behavior:
                continue
            c = sg.center(box)
            # Tìm học sinh có vùng tương tác chứa tâm phát hiện
            matches = [p for p in people if sg.contains(sg.interaction_box(p["box"]), c, pad=0.0)]
            if matches:
                owner = min(matches, key=lambda p: np.hypot(sg.center(p["box"])[0] - c[0], sg.center(p["box"])[1] - c[1]))
                if behavior == "sleeping":
                    # Chỉ coi là gục đầu; "nhắm mắt" phải do phép đo mắt xác nhận, tránh báo ngủ vì 1 lần nhận nhầm
                    owner["signals"]["head_down"] = True
                elif behavior == "phone":
                    owner["signals"]["phone"] = True
                    owner.setdefault("phone_boxes", []).append(box)
                elif behavior in owner["signals"]:
                    owner["signals"][behavior] = True
