"""Ứng dụng cảnh báo hành vi trong lớp học (chạy trên 1 máy).

  python web.py                 # mở http://localhost:8000
  python web.py --source 1      # bắt đầu với camera USB thứ 2
  python web.py --no-browser    # không tự mở trình duyệt

Chỉ người ngồi ở máy đang chạy app xem được (trang web chỉ mở trên localhost).
Điện thoại làm camera: quét mã QR trong Cài đặt. Điện thoại chỉ gửi được hình
(cổng HTTPS 8443, có mã bí mật), không xem được gì.
"""
import argparse
import asyncio
import hashlib
import ipaddress
import json
import secrets
import shutil
import socket
import sys
import threading
import time
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from core.paths import DATA, FROZEN, res

if FROZEN:
    # App đã cài không có cửa sổ dòng lệnh (sys.stdout = None trên Windows). Phải chuyển thông tin
    # ra file TRƯỚC khi nạp thư viện AI, vì chúng in thông tin ngay lúc được nạp.
    _log = open(DATA / "app.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = _log

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import requests  # noqa: E402
import uvicorn  # noqa: E402
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from core import cleanup
from core.focus import FocusTracker, label as focus_label
from core.camera import PushSource, VideoSource
from core.display import Drawer, EventLogger, FPSMeter
from core.pipeline import Pipeline, load_config
from core.rules import BEHAVIOR_NAMES
from core.sound import play_alert
from core.window import open_window, wait_closed

WEB = res("web")
SETTINGS_FILE = DATA / "settings.json"
UPLOADS = DATA / "uploads"
# Luôn hỏi lại máy chủ khi mở trang, để sau khi cập nhật app không bị kẹt giao diện bản cũ
NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}
STORAGE_DEFAULTS = {"save_snapshots": True, "keep_days": 7, "max_storage_mb": 1000}
# Mã bí mật trong mã QR của điện thoại: chỉ ai quét mã mới gửi hình vào được. Đổi mỗi lần mở app.
PHONE_KEY = secrets.token_urlsafe(8)
# Trùng với câu trong file âm thanh (scripts/make_voices.py)
ANNOUNCE = {"phone": "dùng điện thoại", "head_down": "nằm gục xuống bàn", "sleeping": "ngủ gật", "fighting": "đánh nhau", "smoking": "hút thuốc"}

# Các tham số giáo viên chỉnh được trên web: (nhóm trong config.yaml, khoá)
TUNABLE = {
    "head_down_ratio": ("rules", "head_down_ratio"),
    "phone_seconds": ("timing", "phone"),
    "head_down_seconds": ("timing", "head_down"),
    "sleeping_seconds": ("timing", "sleeping"),
    "cooldown": ("timing", "cooldown"),
    "imgsz": ("detection", "imgsz"),
}


def lan_ip():
    """Địa chỉ IP của máy trong mạng Wi-Fi/LAN (không gửi dữ liệu ra ngoài)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def is_local(host):
    """Yêu cầu đến từ chính máy này?"""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host == "localhost"


DEFAULT_VIEW = {"flip_h": True, "flip_v": False, "rotate": 0, "brightness": 0, "zoom": 1.0}


def view_key(source):
    """Mỗi camera nhớ cách chỉnh hình riêng. Băm tên nguồn để không lưu mật khẩu camera dạng chữ."""
    return hashlib.sha1(source.encode()).hexdigest()[:10]


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


def display_name(source):
    """Tên ngắn để hiện trên web. Không bao giờ hiện mật khẩu camera."""
    if source.isdigit():
        return f"Webcam {source}"
    if "://" in source:
        return f"Camera IP {urlparse(source).hostname or ''}".strip()
    return f"Video: {Path(source).name}"


def announcement(behavior, count=1):
    """Câu thông báo chung, không nêu số thứ tự học sinh."""
    who = "Có học sinh" if count == 1 else f"Có {count} học sinh"
    return f"{who} {ANNOUNCE[behavior]}"


def placeholder(text):
    img = np.full((360, 640, 3), 40, np.uint8)
    return Drawer(size=22).draw_text(img, text)


class Engine:
    """Chạy AI liên tục trong 1 luồng riêng; web chỉ đọc kết quả mới nhất."""

    def __init__(self, cfg, settings):
        self.cfg = cfg
        self.settings = settings
        self.pipe = Pipeline(cfg)
        self.drawer = Drawer(cfg["output"].get("font", ""))
        self.logger = EventLogger(DATA / cfg["output"]["log_dir"],
                                  settings.get("save_snapshots", cfg["output"]["save_snapshots"]))
        self.phone = PushSource()
        self.focus = FocusTracker(DATA / cfg["output"]["log_dir"] / "focus.csv")
        self.src = None
        self.view = dict(DEFAULT_VIEW)
        self.source = ""
        self.source_name = ""
        self.thread = None
        self.running = False
        self.switch_lock = threading.Lock()
        self.frame_lock = threading.Lock()
        self.jpeg = self._encode(placeholder("Chưa chọn camera - vào mục Nguồn camera"))
        self.jpeg_id = 0
        self.events = deque(maxlen=500)
        self.event_id = 0
        self.status = {"focus": None, "people": 0, "warning": 0, "fps": 0.0, "active": [], "announcements": []}
        self.error = ""

    @staticmethod
    def _encode(img):
        return cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 75])[1].tobytes()

    # ---------------------------------------------------------- nguồn video
    def set_source(self, source):
        with self.switch_lock:
            if source == "phone":
                self.stop()
                src, name = self.phone, "Camera điện thoại (trình duyệt)"
            else:
                if source == self.source:
                    self.stop()  # cùng 1 webcam thì phải tắt trước mới mở lại được
                # Mở nguồn mới trước; lỗi thì ném RuntimeError và nguồn cũ vẫn chạy
                src = VideoSource(source)
                self.stop()
                name = display_name(source)
            self.pipe.reset()
            self.view = clean_view(self.settings.get("views", {}).get(view_key(source), {}))
            self.src, self.source_name, self.source = src, name, source
            self.error = ""
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def set_view(self, patch):
        """Đổi cách chỉnh hình của camera đang dùng, nhớ cho lần sau và áp dụng ngay."""
        new = clean_view({**self.view, **patch})
        if (new["rotate"], new["flip_h"], new["flip_v"], new["zoom"]) != \
                (self.view["rotate"], self.view["flip_h"], self.view["flip_v"], self.view["zoom"]):
            self.pipe.reset()  # đổi hướng/khung hình thì mã số học sinh cũ không còn đúng
        self.view = new
        self.settings.setdefault("views", {})[view_key(self.source)] = new
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        return new

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        if self.src:
            self.src.release()
        self.src = None

    # ---------------------------------------------------------- vòng lặp AI
    def _loop(self):
        fps_meter = FPSMeter()
        t0, idx = time.time(), 0
        src = self.src
        while self.running:
            frame = src.read(timeout=1.0)
            if frame is None:
                if src is self.phone:
                    self._show(placeholder("Đang chờ điện thoại gửi hình..."))
                    continue
                if src.live:
                    continue
                # Hết video -> phát lại từ đầu (tiện khi demo)
                src.release()
                src = self.src = VideoSource(self.source)
                self.pipe.reset()
                t0, idx = time.time(), 0
                continue

            t = time.time() - t0 if src.live else idx / src.fps
            idx += 1
            try:
                frame = adjust(frame, self.view)
                people, alerts = self.pipe.process(frame, t)
            except Exception as e:  # không để 1 lỗi làm sập cả hệ thống
                self.error = str(e)
                continue
            out = self.drawer.draw(frame, people, fps_meter.tick(), header=False)  # số liệu đã có trên giao diện
            self._show(out)

            for a in alerts:
                snap = self.logger.log(a, out)
                self.event_id += 1
                ev = {
                    "id": self.event_id, "time": datetime.now().isoformat(timespec="seconds"),
                    "student": a["id"], "behavior": a["behavior"], "name": BEHAVIOR_NAMES[a["behavior"]],
                    "duration": round(a["duration"], 1), "text": announcement(a["behavior"]),
                    "snapshot": f"/snapshots/{Path(snap).name}" if snap else "",
                }
                self.events.append(ev)
                self._telegram(ev, snap)
            if self.settings.get("server_sound", self.cfg["output"]["sound"]):
                for b in dict.fromkeys(a["behavior"] for a in alerts):  # mỗi hành vi đọc 1 lần
                    play_alert(b)

            focus = self.focus.update(people)
            self.status = {
                "focus": None if focus is None else round(focus),
                "people": len(people),
                "warning": sum(1 for p in people if p["active"]),
                "fps": round(fps_meter.fps or 0, 1),
                "active": [{"student": p["id"], "behaviors": [BEHAVIOR_NAMES[b] for b in p["active"]]}
                           for p in people if p["active"]],
                "announcements": [announcement(b, n) for b, n in
                                  Counter(b for p in people for b in p["active"]).items()],
            }

            if not src.live:  # video: phát đúng tốc độ thật để demo trông tự nhiên
                wait = t - (time.time() - t0)
                if wait > 0:
                    time.sleep(wait)

    def _show(self, img):
        data = self._encode(img)
        with self.frame_lock:
            self.jpeg, self.jpeg_id = data, self.jpeg_id + 1

    # ---------------------------------------------------------- dọn ổ cứng
    def storage(self):
        return {**STORAGE_DEFAULTS, **{k: self.settings[k] for k in STORAGE_DEFAULTS if k in self.settings}}

    def clean_storage(self, everything=False):
        """Xoá ảnh cảnh báo và video tải lên cũ. everything=True: xoá hết ảnh (giữ video đang chạy)."""
        st = self.storage()
        days, mb = (0, 0) if everything else (st["keep_days"], st["max_storage_mb"])
        removed = cleanup.clean([self.logger.snap_dir], days, mb)
        removed += cleanup.clean([UPLOADS], st["keep_days"], st["max_storage_mb"], protect=[self.source])
        if removed:
            print(f"[i] Đã dọn {removed} file cũ")
        return removed

    def cleanup_loop(self):
        while True:
            try:
                self.clean_storage()
            except Exception as e:
                print(f"[!] Lỗi khi dọn ổ cứng: {e}")
            time.sleep(1800)  # 30 phút dọn 1 lần

    # ---------------------------------------------------------- Telegram
    def _telegram(self, ev, snap):
        token, chat = self.settings.get("telegram_token"), self.settings.get("telegram_chat_id")
        if not (token and chat):
            return
        caption = f"⚠️ {ev['text']}\n🕒 {ev['time'][11:]}"

        def send():
            try:
                url = f"https://api.telegram.org/bot{token}/"
                if snap:
                    with open(snap, "rb") as f:
                        requests.post(url + "sendPhoto", data={"chat_id": chat, "caption": caption},
                                      files={"photo": f}, timeout=15)
                else:
                    requests.post(url + "sendMessage", data={"chat_id": chat, "text": caption}, timeout=15)
            except requests.RequestException as e:
                print(f"[!] Gửi Telegram lỗi: {e}")
        threading.Thread(target=send, daemon=True).start()


# ====================================================================== web
def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_settings(cfg, settings):
    for key, (group, name) in TUNABLE.items():
        if key in settings:
            cfg[group][name] = type(cfg[group][name])(settings[key])


def create_app(engine, urls):
    app = FastAPI(title="Cảnh báo hành vi lớp học")
    Path(engine.logger.snap_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/snapshots", StaticFiles(directory=engine.logger.snap_dir), name="snapshots")
    app.mount("/sounds", StaticFiles(directory=WEB / "sounds"), name="sounds")

    @app.middleware("http")
    async def only_this_computer(request: Request, call_next):
        """Máy khác trong mạng (vd điện thoại) chỉ được mở trang gửi hình, có đúng mã bí mật."""
        if not is_local(request.client.host):
            if request.url.path != "/phone" or request.query_params.get("k") != PHONE_KEY:
                return Response("Chỉ xem được trên máy đang chạy ứng dụng. Điện thoại: hãy quét lại mã QR mới.",
                                status_code=403, media_type="text/plain; charset=utf-8")
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return FileResponse(WEB / "index.html", headers=NO_CACHE)

    @app.get("/phone", response_class=HTMLResponse)
    def phone_page():
        return FileResponse(WEB / "phone.html", headers=NO_CACHE)

    @app.get("/video")
    async def video():
        async def gen():
            last = -1
            while True:
                with engine.frame_lock:
                    data, fid = engine.jpeg, engine.jpeg_id
                if fid != last:
                    last = fid
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                await asyncio.sleep(0.03)
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")

    @app.get("/api/status")
    def status(after: int = 0):
        return {
            **engine.status, "source": engine.source_name, "error": engine.error, "view": engine.view,
            "phone_connected": time.time() - engine.phone.last_push < 3,
            "events": [e for e in engine.events if e["id"] > after][-50:],
            "counts": {b: engine.logger.counts.get(b, 0) for b in BEHAVIOR_NAMES},
        }

    @app.get("/api/focus")
    def focus(minutes: int = 60):
        return engine.focus.summary(max(5, min(minutes, 24 * 60)))

    @app.get("/api/stats")
    def stats(minutes: int = 30):
        now = datetime.now()
        buckets = [{"label": (now - timedelta(minutes=i)).strftime("%H:%M"),
                    **{b: 0 for b in BEHAVIOR_NAMES}} for i in reversed(range(minutes))]
        index = {b["label"]: b for b in buckets}
        for e in engine.events:
            label = e["time"][11:16]
            if label in index:
                index[label][e["behavior"]] += 1
        students = {}
        for e in engine.events:
            students.setdefault(e["student"], {b: 0 for b in BEHAVIOR_NAMES})[e["behavior"]] += 1
        top = sorted(students.items(), key=lambda kv: -sum(kv[1].values()))[:10]
        return {"timeline": buckets, "students": [{"student": k, **v} for k, v in top],
                "names": BEHAVIOR_NAMES}

    @app.get("/api/info")
    def info():
        return {"urls": urls, "cameras": list_cameras(), "settings": current_settings(engine)}

    @app.post("/api/source")
    def set_source(body: dict):
        source = str(body.get("source", "")).strip()
        if not source:
            raise HTTPException(400, "Chưa nhập nguồn camera")
        try:
            engine.set_source(source)
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "source": engine.source_name}

    @app.post("/api/view")
    def set_view(body: dict):
        try:
            return {"ok": True, "view": engine.set_view(body)}
        except (ValueError, TypeError):
            raise HTTPException(400, "Giá trị không hợp lệ")

    @app.post("/api/upload")
    async def upload(file: UploadFile = File(...)):
        UPLOADS.mkdir(exist_ok=True)
        dst = UPLOADS / Path(file.filename).name
        with open(dst, "wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            engine.set_source(str(dst))
        except RuntimeError as e:
            raise HTTPException(400, str(e))
        return {"ok": True, "source": engine.source_name}

    @app.post("/api/settings")
    def save_settings(body: dict):
        for key in TUNABLE:
            if key in body:
                engine.settings[key] = float(body[key]) if key != "imgsz" else int(body[key])
        for key in ("telegram_token", "telegram_chat_id"):
            if key in body:
                engine.settings[key] = str(body[key]).strip()
        if "server_sound" in body:
            engine.settings["server_sound"] = bool(body["server_sound"])
        if "save_snapshots" in body:
            engine.settings["save_snapshots"] = engine.logger.save_snapshots = bool(body["save_snapshots"])
        if "keep_days" in body:
            engine.settings["keep_days"] = max(1, int(float(body["keep_days"])))
        if "max_storage_mb" in body:
            engine.settings["max_storage_mb"] = max(50, int(float(body["max_storage_mb"])))
        threading.Thread(target=engine.clean_storage, daemon=True).start()  # áp dụng giới hạn mới ngay
        apply_settings(engine.cfg, engine.settings)
        SETTINGS_FILE.write_text(json.dumps(engine.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "settings": current_settings(engine)}

    @app.post("/api/telegram/find-chat")
    def find_chat(body: dict):
        token = str(body.get("token", "")).strip()
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
        except requests.RequestException as e:
            raise HTTPException(400, f"Không kết nối được Telegram: {e}")
        if not r.get("ok"):
            raise HTTPException(400, "Token không đúng")
        chats = [u["message"]["chat"] for u in r["result"] if "message" in u]
        if not chats:
            raise HTTPException(400, "Chưa thấy tin nhắn nào. Hãy mở bot trên Telegram, bấm Start rồi thử lại.")
        chat = chats[-1]
        return {"chat_id": str(chat["id"]), "name": chat.get("first_name") or chat.get("title", "")}

    @app.post("/api/sound/test")
    def test_sound(body: dict):
        play_alert(str(body.get("behavior", "phone")))
        return {"ok": True}

    @app.post("/api/telegram/test")
    def test_telegram():
        engine._telegram({"text": "Thử thông báo từ hệ thống giám sát lớp học",
                          "time": datetime.now().isoformat(timespec="seconds")}, "")
        return {"ok": True}

    @app.get("/api/storage")
    def storage():
        files, mb = cleanup.usage([engine.logger.snap_dir, UPLOADS])
        return {"files": files, "mb": round(mb, 1), **engine.storage()}

    @app.post("/api/storage/clear")
    def clear_storage():
        return {"removed": engine.clean_storage(everything=True)}

    @app.post("/api/quit")
    def quit_app():
        """Nút "Tắt ứng dụng" trên giao diện."""
        threading.Timer(0.5, request_exit).start()
        return {"ok": True}

    @app.get("/api/events.csv")
    def events_csv():
        return FileResponse(engine.logger.path, filename="canh_bao.csv", media_type="text/csv")

    @app.get("/api/qr")
    def qr(url: str):
        import qrcode
        import qrcode.image.svg
        svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).to_string()
        return Response(svg, media_type="image/svg+xml")

    @app.websocket("/ws/phone")
    async def ws_phone(ws: WebSocket):
        await ws.accept()
        if not is_local(ws.client.host) and ws.query_params.get("k") != PHONE_KEY:
            await ws.send_text(json.dumps({"error": "Mã QR đã cũ (app vừa mở lại). Hãy quét lại mã QR mới."},
                                          ensure_ascii=False))
            await ws.close()
            return
        if engine.source != "phone":  # điện thoại kết nối -> tự chuyển sang camera điện thoại
            await asyncio.to_thread(engine.set_source, "phone")
        try:
            while True:
                engine.phone.push_jpeg(await ws.receive_bytes())
                await ws.send_text(json.dumps({"announcements": engine.status["announcements"]}, ensure_ascii=False))
        except WebSocketDisconnect:
            pass

    return app


def current_settings(engine):
    s = {key: engine.cfg[g][n] for key, (g, n) in TUNABLE.items()}
    s["telegram_token"] = engine.settings.get("telegram_token", "")
    s["telegram_chat_id"] = engine.settings.get("telegram_chat_id", "")
    s["server_sound"] = engine.settings.get("server_sound", engine.cfg["output"]["sound"])
    s.update(engine.storage())
    return s


_camera_cache = None


def list_cameras(max_index=4):
    """Tìm các webcam đang cắm (chỉ dò 1 lần vì mở camera khá chậm)."""
    global _camera_cache
    if _camera_cache is None:
        found = []
        for i in range(max_index):
            if engine_ref and engine_ref.source == str(i):
                found.append(i)  # đang dùng thì không mở lại được, nhưng chắc chắn có
                continue
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                found.append(i)
            cap.release()
        _camera_cache = found
    return _camera_cache


def make_cert(ip):
    """Tạo chứng chỉ HTTPS tự ký để điện thoại được phép dùng camera trong trình duyệt."""
    cert_dir = DATA / "certs"
    key_file, cert_file, ip_file = cert_dir / "key.pem", cert_dir / "cert.pem", cert_dir / "ip.txt"
    if key_file.exists() and cert_file.exists() and ip_file.exists() and ip_file.read_text() == ip:
        return str(key_file), str(cert_file)  # đổi mạng Wi-Fi (IP khác) thì tạo lại
    try:
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        return None
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "khkt-lop-hoc")])
    alt = x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                       x509.IPAddress(ipaddress.ip_address(ip))])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.now() - timedelta(days=1))
            .not_valid_after(datetime.now() + timedelta(days=3650))
            .add_extension(alt, critical=False).sign(key, hashes.SHA256()))
    cert_dir.mkdir(parents=True, exist_ok=True)
    ip_file.write_text(ip)
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(key_file), str(cert_file)


engine_ref = None
servers = []


def request_exit():
    for s in servers:
        s.should_exit = True


def already_running(port):
    """App đã mở rồi (vd bấm biểu tượng lần 2)?"""
    try:
        return requests.get(f"http://127.0.0.1:{port}/api/status", timeout=1).ok
    except requests.RequestException:
        return False


def main():
    global engine_ref
    if FROZEN:
        print(f"\n===== Mở app lúc {datetime.now():%Y-%m-%d %H:%M:%S} =====")
    ap = argparse.ArgumentParser(description="Web cảnh báo hành vi lớp học")
    ap.add_argument("--source", default="0", help='Nguồn ban đầu: "0" webcam, link camera, file video, "none"')
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--https-port", type=int, default=8443)
    ap.add_argument("--no-browser", action="store_true", help="Không mở cửa sổ giao diện (chạy nền)")
    args = ap.parse_args()

    if already_running(args.port):  # chỉ mở lại cửa sổ, không chạy thêm bản thứ 2
        if not args.no_browser:
            proc = open_window(f"http://localhost:{args.port}")
            print("App đang chạy sẵn, đã mở lại cửa sổ.")
            if proc:
                proc.wait()
        return

    cfg = load_config(args.config)
    settings = load_settings()
    apply_settings(cfg, settings)
    engine = engine_ref = Engine(cfg, settings)
    threading.Thread(target=engine.cleanup_loop, daemon=True).start()
    if args.source != "none":
        try:
            engine.set_source(args.source)
        except RuntimeError:
            print(f"[i] Không mở được nguồn '{args.source}', hãy chọn camera trên trang web.")

    ip = lan_ip()
    cert = make_cert(ip)
    urls = {"local": f"http://localhost:{args.port}",
            "phone": f"https://{ip}:{args.https_port}/phone?k={PHONE_KEY}" if cert else ""}
    app = create_app(engine, urls)

    # Trang xem chỉ mở trên máy này (127.0.0.1). Cổng HTTPS mở ra mạng Wi-Fi chỉ để
    # điện thoại gửi hình (đã chặn mọi trang khác bằng only_this_computer).
    # Luồng video trực tiếp không bao giờ tự đóng, nên khi tắt chỉ chờ 2 giây rồi tắt hẳn.
    opts = dict(log_level="warning", timeout_graceful_shutdown=2)
    servers.append(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, **opts)))
    if cert:
        servers.append(uvicorn.Server(uvicorn.Config(app, host="0.0.0.0", port=args.https_port,
                                                     ssl_keyfile=cert[0], ssl_certfile=cert[1], **opts)))
    print("\n" + "=" * 60)
    print(" HỆ THỐNG CẢNH BÁO HÀNH VI LỚP HỌC ĐANG CHẠY")
    print(f"   Mở trên máy này: {urls['local']}")
    print(f"   Dữ liệu lưu ở:   {DATA}")
    print(" Đóng cửa sổ app (hoặc nhấn Ctrl+C) để tắt.")
    print("=" * 60 + "\n")
    if not args.no_browser:
        def window():
            # Đóng cửa sổ app = tắt app (nếu theo dõi được cửa sổ)
            time.sleep(1.0)
            proc = open_window(urls["local"])
            if proc and wait_closed(proc):
                print("Cửa sổ đã đóng -> tắt app.")
                request_exit()
        threading.Thread(target=window, daemon=True).start()

    async def serve():
        # Ctrl+C chỉ báo cho 1 server, nên khi 1 cái dừng thì dừng luôn cái còn lại
        tasks = [asyncio.create_task(s.serve()) for s in servers]
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for s in servers:
            s.should_exit = True
        await asyncio.gather(*pending)
    try:
        asyncio.run(serve())
    finally:
        engine.stop()
        engine.focus.close()
        engine.logger.close()


if __name__ == "__main__":
    main()
