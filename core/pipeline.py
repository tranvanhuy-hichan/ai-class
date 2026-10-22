"""Ghép các mô hình AI + luật thành 1 hệ thống hoàn chỉnh.

Mỗi khung hình đi qua các bước:
  1. YOLO-pose: tìm người, gán ID theo dõi (tracking), lấy 17 điểm khung xương
  2. YOLO (COCO): tìm điện thoại -> gán cho học sinh đang cầm nó
  3. MediaPipe (hoặc mô hình mắt tự huấn luyện): mắt mở hay nhắm
  4. (Tuỳ chọn) Mô hình hành vi tự huấn luyện
  5. Luật thời gian -> quyết định có cảnh báo hay không
"""
from pathlib import Path

import cv2
import yaml
from ultralytics import YOLO

from . import signals as sg
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


class Pipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        m = cfg["models"]
        self.device = m.get("device") or None
        self.pose = YOLO(str(res(m["pose"])))
        self.obj = YOLO(str(res(m["object"])))

        self.eye = self.face = None
        method = m.get("eye_method", "mediapipe")
        if method == "mediapipe":
            self.face = load_face_landmarker(res(m.get("face_landmarker", "weights/face_landmarker.task")))
        elif method == "classifier" and res(m["eye_classifier"]).exists():
            self.eye = YOLO(str(res(m["eye_classifier"])))
            names = {v.lower(): k for k, v in self.eye.names.items()}
            self.closed_idx = names.get("closed", 0)
            print(f"[i] Đã nạp mô hình mắt: {m['eye_classifier']}")

        self.custom = None
        if m.get("custom_behavior") and res(m["custom_behavior"]).exists():
            self.custom = YOLO(str(res(m["custom_behavior"])))
            cmap = {k.lower(): v for k, v in cfg.get("custom_class_map", {}).items()}
            self.custom_map = {i: cmap.get(n.lower()) for i, n in self.custom.names.items()}
            print(f"[i] Đã nạp mô hình hành vi: {m['custom_behavior']} -> {self.custom_map}")

        self.rules = BehaviorRules(cfg["timing"])

    def reset(self):
        """Gọi khi chuyển sang video mới."""
        self.rules = BehaviorRules(self.cfg["timing"])
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

        res = self.pose.track(frame, persist=True, conf=det["person_conf"], imgsz=det["imgsz"],
                              device=self.device, verbose=False)[0]
        people = []
        if res.boxes is not None and res.boxes.id is not None:
            boxes = res.boxes.xyxy.cpu().numpy()
            ids = res.boxes.id.int().cpu().tolist()
            kpts = res.keypoints.data.cpu().numpy()  # (N, 17, 3)
            for tid, box, kp in zip(ids, boxes, kpts):
                ratio = sg.head_ratio(kp, thr)
                people.append({
                    "id": tid, "box": box, "kpts": kp, "head_ratio": ratio,
                    "signals": {"head_down": ratio is not None and ratio < r["head_down_ratio"]},
                })

        if people:
            self._detect_phones(frame, people, det, r, thr)
            if self.face is not None:
                self._check_eyes_mediapipe(frame, people, r, thr)
            elif self.eye is not None:
                self._check_eyes(frame, people, r, thr)
            if self.custom is not None:
                self._custom_behaviors(frame, people, det)

        alerts = []
        for p in people:
            p["active"], new = self.rules.update(p["id"], p["signals"], t)
            for b in new:
                alerts.append({"id": p["id"], "behavior": b, "duration": p["active"][b], "box": p["box"]})
        self.rules.forget_old(t)
        return people, alerts

    # ------------------------------------------------------------------
    def _detect_phones(self, frame, people, det, r, thr):
        res = self.obj.predict(frame, classes=[COCO_PHONE], conf=det["phone_conf"], imgsz=det["imgsz"],
                               device=self.device, verbose=False)[0]
        for box in res.boxes.xyxy.cpu().numpy():
            c = sg.center(box)
            best, best_d = None, None
            for p in people:
                if not sg.contains(p["box"], c):
                    continue
                d = sg.wrist_distance(p["kpts"], c, thr)
                if d is not None and d > r["phone_wrist_factor"]:
                    continue  # điện thoại nằm trong khung nhưng xa tay (vd để trên bàn)
                d = 0.0 if d is None else d
                if best is None or d < best_d:
                    best, best_d = p, d
            if best is not None:
                best["signals"]["phone"] = True
                best.setdefault("phone_boxes", []).append(box)

    def _check_eyes_mediapipe(self, frame, people, r, thr):
        import mediapipe as mp
        for p in people:
            box = sg.head_box(frame, p["kpts"], thr, r["min_eye_distance_px"])
            if box is None:
                continue
            x0, y0, x1, y1 = box
            # Phóng to vùng đầu để MediaPipe nhìn rõ cả khi học sinh ngồi xa
            head = cv2.resize(frame[y0:y1, x0:x1], (256, 256))
            res = self.face.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                                            data=cv2.cvtColor(head, cv2.COLOR_BGR2RGB)))
            if not res.face_blendshapes:
                continue
            score = {b.category_name: b.score for b in res.face_blendshapes[0]}
            closed = (score["eyeBlinkLeft"] + score["eyeBlinkRight"]) / 2
            p["eye_closed_prob"] = closed
            p["signals"]["eyes_closed"] = closed > r["blink_threshold"]

    def _check_eyes(self, frame, people, r, thr):
        for p in people:
            crops = sg.eye_crops(frame, p["kpts"], thr, r["min_eye_distance_px"])
            if not crops:
                continue
            # Ảnh mắt trong bộ dữ liệu thường là ảnh xám -> chuyển cho giống
            crops = [cv2.cvtColor(cv2.cvtColor(c, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR) for c in crops]
            outs = self.eye.predict(crops, imgsz=64, device=self.device, verbose=False)
            prob = sum(float(o.probs.data[self.closed_idx]) for o in outs) / len(outs)
            p["eye_closed_prob"] = prob
            p["signals"]["eyes_closed"] = prob > r["eye_closed_prob"]

    def _custom_behaviors(self, frame, people, det):
        res = self.custom.predict(frame, conf=det["person_conf"], imgsz=det["imgsz"],
                                  device=self.device, verbose=False)[0]
        for box, cls in zip(res.boxes.xyxy.cpu().numpy(), res.boxes.cls.int().cpu().tolist()):
            behavior = self.custom_map.get(cls)
            if behavior is None:
                continue
            signal = "eyes_closed" if behavior == "sleeping" else behavior
            c = sg.center(box)
            # Gán cho người có khung nhỏ nhất chứa tâm của phát hiện
            owners = [p for p in people if sg.contains(p["box"], c, pad=0.0)]
            if owners:
                owner = min(owners, key=lambda p: (p["box"][2] - p["box"][0]) * (p["box"][3] - p["box"][1]))
                owner["signals"][signal] = True
