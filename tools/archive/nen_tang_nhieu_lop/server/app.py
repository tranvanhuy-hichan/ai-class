"""Các API của nền tảng (FastAPI). Giao diện nằm trong thư mục web/."""
import asyncio
import csv
import io
import json
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import cv2
import numpy as np
import requests
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

from core.paths import DATA, res
from core.rules import BEHAVIOR_NAMES
from core.sound import play_alert
from core.tts import make_class_clip

from .cameras import Manager, announcement, encode
from .db import DB, now_iso

WEB = res("web")
SNAPS = DATA / "snapshots"
VOICES = DATA / "voices"
UPLOADS = DATA / "uploads"
BEHAVIORS = list(BEHAVIOR_NAMES)

# Cài đặt quản trị viên chỉnh được trên web: khoá -> (nhóm trong config.yaml, tên)
TUNABLE = {
    "head_down_ratio": ("rules", "head_down_ratio"),
    "phone_seconds": ("timing", "phone"),
    "head_down_seconds": ("timing", "head_down"),
    "sleeping_seconds": ("timing", "sleeping"),
    "cooldown": ("timing", "cooldown"),
    "imgsz": ("detection", "imgsz"),
}
DEFAULTS = {"fps_background": 2, "fps_watch": 8, "keep_days": 30, "server_sound": True,
            "save_snapshots": True, "telegram_token": "", "telegram_chat_id": ""}


def apply_settings(cfg, settings):
    for key, (group, name) in TUNABLE.items():
        if key in settings:
            cfg[group][name] = type(cfg[group][name])(settings[key])


class Platform:
    """Trạng thái dùng chung của cả máy chủ."""

    def __init__(self, cfg, urls):
        self.cfg = cfg
        self.urls = urls
        self.db = DB(DATA / "lophoc.db")
        apply_settings(cfg, self.db.settings())
        self.manager = Manager(cfg, self.db, self.on_alert)
        threading.Thread(target=self._cleanup_loop, daemon=True).start()
        for r in self.db.all("SELECT id, name FROM classrooms"):  # tạo bù giọng đọc tên lớp còn thiếu
            if not (VOICES / f"{r['id']}.wav").exists():
                self.class_voice(r["id"], r["name"])

    def settings(self):
        s = {**DEFAULTS, **self.db.settings()}
        s.update({k: self.cfg[g][n] for k, (g, n) in TUNABLE.items()})
        return s

    # ---------------------------------------------------------- khi có cảnh báo
    def on_alert(self, worker, alert, frame):
        s = self.settings()
        t = datetime.now()
        snap = ""
        if s["save_snapshots"]:
            folder = SNAPS / str(worker.id)
            folder.mkdir(parents=True, exist_ok=True)
            name = f"{t:%Y%m%d_%H%M%S}_{alert['behavior']}_{alert['id']}.jpg"
            cv2.imwrite(str(folder / name), frame)
            snap = f"{worker.id}/{name}"
        self.db.run("INSERT INTO events(classroom_id, time, student, behavior, duration, snapshot) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (worker.id, t.isoformat(timespec="seconds"), alert["id"],
                                                  alert["behavior"], round(alert["duration"], 1), snap))
        text = f"{worker.name}: {announcement(alert['behavior'])}"
        print(f"[!] {t:%H:%M:%S} {text}")
        if s["server_sound"]:
            play_alert(alert["behavior"], prefix=VOICES / f"{worker.id}.wav")
        room = self.db.one("SELECT telegram_chat_id FROM classrooms WHERE id = ?", (worker.id,))
        chat = (room or {}).get("telegram_chat_id") or s["telegram_chat_id"]
        if s["telegram_token"] and chat:
            self.telegram(s["telegram_token"], chat, f"⚠️ {text}\n🕒 {t:%H:%M:%S %d/%m}",
                          SNAPS / snap if snap else None)

    @staticmethod
    def telegram(token, chat, text, photo=None):
        def send():
            try:
                url = f"https://api.telegram.org/bot{token}/"
                if photo:
                    with open(photo, "rb") as f:
                        requests.post(url + "sendPhoto", data={"chat_id": chat, "caption": text},
                                      files={"photo": f}, timeout=15)
                else:
                    requests.post(url + "sendMessage", data={"chat_id": chat, "text": text}, timeout=15)
            except requests.RequestException as e:
                print(f"[!] Gửi Telegram lỗi: {e}")
        threading.Thread(target=send, daemon=True).start()

    def class_voice(self, cid, name):
        threading.Thread(target=make_class_clip, args=(name, VOICES / f"{cid}.wav"), daemon=True).start()

    def _cleanup_loop(self):
        """Xoá cảnh báo + ảnh cũ hơn keep_days ngày để ổ cứng không đầy."""
        while True:
            try:
                days = int(self.settings()["keep_days"])
                cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
                for r in self.db.all("SELECT snapshot FROM events WHERE time < ? AND snapshot != ''", (cutoff,)):
                    (SNAPS / r["snapshot"]).unlink(missing_ok=True)
                self.db.run("DELETE FROM events WHERE time < ?", (cutoff,))
            except Exception as e:
                print(f"[!] Lỗi dọn dữ liệu cũ: {e}")
            time.sleep(6 * 3600)


def placeholder(drawer, text):
    img = np.full((360, 640, 3), 30, np.uint8)
    return encode(drawer.draw_text(img, text))


def create_app(p: Platform):
    app = FastAPI(title="Lớp học AI")
    db, mgr = p.db, p.manager

    # ================================================================ xác thực
    def user_dep(request: Request):
        user = db.session_user(request.cookies.get("sid"))
        if not user:
            raise HTTPException(401, "Chưa đăng nhập")
        return user

    def admin_dep(user=Depends(user_dep)):
        if user["role"] != "admin":
            raise HTTPException(403, "Chỉ quản trị viên được làm việc này")
        return user

    def allowed(user, cid):
        if cid not in db.class_ids_for(user):
            raise HTTPException(403, "Bạn không được xem lớp này")

    def set_login(resp, token):
        resp.set_cookie("sid", token, max_age=30 * 86400, httponly=True, samesite="lax")
        return resp

    @app.get("/")
    def index(request: Request):
        if not db.session_user(request.cookies.get("sid")):
            return RedirectResponse("/login")
        return FileResponse(WEB / "index.html")

    @app.get("/login")
    def login_page():
        return FileResponse(WEB / "login.html")

    @app.get("/api/setup-needed")
    def setup_needed():
        return {"needed": db.one("SELECT COUNT(*) AS n FROM users")["n"] == 0}

    @app.post("/api/setup")
    def setup(body: dict):
        """Lần chạy đầu: tạo tài khoản quản trị viên."""
        if not setup_needed()["needed"]:
            raise HTTPException(400, "Đã có tài khoản quản trị")
        username, password = str(body.get("username", "")).strip(), str(body.get("password", ""))
        if len(username) < 3 or len(password) < 6:
            raise HTTPException(400, "Tên đăng nhập ít nhất 3 ký tự, mật khẩu ít nhất 6 ký tự")
        db.create_user(username, body.get("name") or username, password, "admin")
        return set_login(Response('{"ok":true}', media_type="application/json"), db.login(username, password))

    @app.post("/api/login")
    def login(body: dict):
        token = db.login(str(body.get("username", "")), str(body.get("password", "")))
        if not token:
            time.sleep(1)  # chậm lại để khó dò mật khẩu
            raise HTTPException(401, "Sai tên đăng nhập hoặc mật khẩu")
        return set_login(Response('{"ok":true}', media_type="application/json"), token)

    @app.post("/api/logout")
    def logout(request: Request):
        db.run("DELETE FROM sessions WHERE token = ?", (request.cookies.get("sid", ""),))
        resp = Response('{"ok":true}', media_type="application/json")
        resp.delete_cookie("sid")
        return resp

    @app.get("/api/me")
    def me(user=Depends(user_dep)):
        return user

    @app.post("/api/me/password")
    def change_password(body: dict, user=Depends(user_dep)):
        row = db.one("SELECT pw_hash FROM users WHERE id = ?", (user["id"],))
        from .db import check_password, hash_password
        if not check_password(str(body.get("old", "")), row["pw_hash"]):
            raise HTTPException(400, "Mật khẩu cũ không đúng")
        if len(str(body.get("new", ""))) < 6:
            raise HTTPException(400, "Mật khẩu mới ít nhất 6 ký tự")
        db.run("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(body["new"]), user["id"]))
        return {"ok": True}

    # ================================================================ lớp học
    def room_out(r, admin):
        w = mgr.get(r["id"])
        out = {"id": r["id"], "name": r["name"], "enabled": bool(r["enabled"]),
               **(w.info() if w else {"state": "off", "error": "Đang tắt", "people": 0, "warning": 0,
                                      "fps": 0, "announcements": [], "viewers": 0, "phone_connected": False})}
        if admin:
            out.update(source=r["source"], telegram_chat_id=r["telegram_chat_id"])
        out["source_type"] = source_type(r["source"])
        out["source_label"] = source_label(r["source"])
        if out["source_type"] == "phone":
            out["station_url"] = f"{p.urls['https']}/station/{r['station_token']}" if p.urls.get("https") else ""
            out["streamer"] = w.streamer if w and out.get("phone_connected") else ""
        return out

    @app.get("/api/classes")
    def list_classes(user=Depends(user_dep)):
        ids = set(db.class_ids_for(user))
        rows = [r for r in db.all("SELECT * FROM classrooms ORDER BY name") if r["id"] in ids]
        return [room_out(r, user["role"] == "admin") for r in rows]

    def save_class(body, cid=None):
        name = str(body.get("name", "")).strip()
        if not name:
            raise HTTPException(400, "Chưa nhập tên lớp")
        source = str(body.get("source", "")).strip()
        try:
            if cid is None:
                cid = db.run("INSERT INTO classrooms(name, source, enabled, station_token, telegram_chat_id, created) "
                             "VALUES (?, ?, ?, ?, ?, ?)", (name, source, int(body.get("enabled", True)),
                                                           secrets.token_urlsafe(12),
                                                           str(body.get("telegram_chat_id", "")).strip(), now_iso()))
                p.class_voice(cid, name)
            else:
                old = db.one("SELECT name FROM classrooms WHERE id = ?", (cid,))
                if not old:
                    raise HTTPException(404, "Không có lớp này")
                db.run("UPDATE classrooms SET name = ?, source = ?, enabled = ?, telegram_chat_id = ? WHERE id = ?",
                       (name, source, int(body.get("enabled", True)), str(body.get("telegram_chat_id", "")).strip(), cid))
                if old["name"] != name:
                    p.class_voice(cid, name)
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(400, f"Đã có lớp tên '{name}'")
            raise
        mgr.sync()
        return {"ok": True, "id": cid}

    @app.post("/api/classes")
    def create_class(body: dict, _=Depends(admin_dep)):
        return save_class(body)

    @app.put("/api/classes/{cid}")
    def update_class(cid: int, body: dict, _=Depends(admin_dep)):
        return save_class(body, cid)

    @app.delete("/api/classes/{cid}")
    def delete_class(cid: int, _=Depends(admin_dep)):
        db.run("DELETE FROM classrooms WHERE id = ?", (cid,))
        shutil.rmtree(SNAPS / str(cid), ignore_errors=True)
        (VOICES / f"{cid}.wav").unlink(missing_ok=True)
        mgr.sync()
        return {"ok": True}

    @app.post("/api/classes/{cid}/upload")
    async def upload_video(cid: int, file: UploadFile = File(...), _=Depends(admin_dep)):
        room = db.one("SELECT * FROM classrooms WHERE id = ?", (cid,))
        if not room:
            raise HTTPException(404, "Không có lớp này")
        UPLOADS.mkdir(parents=True, exist_ok=True)
        dst = UPLOADS / f"{cid}_{Path(file.filename).name}"
        with open(dst, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return save_class({**room, "source": str(dst), "enabled": True}, cid)

    @app.post("/api/classes/{cid}/new-station-link")
    def new_station(cid: int, _=Depends(admin_dep)):
        db.run("UPDATE classrooms SET station_token = ? WHERE id = ?", (secrets.token_urlsafe(12), cid))
        return {"ok": True}

    @app.get("/api/cameras")
    def cameras(_=Depends(admin_dep)):
        """Tìm webcam đang cắm vào máy chủ (bỏ qua webcam đang được lớp nào dùng)."""
        used = {w.source for w in mgr.workers.values()}
        found = []
        for i in range(5):
            if str(i) in used:
                found.append(i)
                continue
            cap = cv2.VideoCapture(i)
            if cap.isOpened() and cap.read()[0]:
                found.append(i)
            cap.release()
        return found

    # ================================================================ video
    @app.get("/api/classes/{cid}/video")
    async def video(cid: int, user=Depends(user_dep)):
        allowed(user, cid)
        w = mgr.get(cid)
        if not w:
            raise HTTPException(404, "Lớp đang tắt")

        async def gen():
            w.viewers += 1
            last, last_change = -1, time.time()
            try:
                while True:
                    with w.frame_lock:
                        data, fid = w.jpeg, w.jpeg_id
                    if fid != last and data:
                        last, last_change = fid, time.time()
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + data + b"\r\n"
                    elif time.time() - last_change > 3:  # lâu không có hình -> báo trạng thái
                        msg = {"waiting": "Đang chờ điện thoại gửi hình...", "starting": "Đang kết nối camera...",
                               "off": w.error or "Chưa chọn camera"}.get(w.state, w.error or "Mất tín hiệu camera")
                        yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + placeholder(mgr.drawer, msg) + b"\r\n"
                        last_change = time.time()
                    await asyncio.sleep(0.03)
            finally:
                w.viewers -= 1
        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/classes/{cid}/thumb.jpg")
    def thumb(cid: int, user=Depends(user_dep)):
        allowed(user, cid)
        w = mgr.get(cid)
        data = w.thumb if w and w.thumb else None
        if data is None:
            msg = (w.error if w and w.error else "Đang kết nối...") if w else "Lớp đang tắt"
            data = placeholder(mgr.drawer, msg)
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/snapshots/{cid}/{name}")
    def snapshot(cid: int, name: str, user=Depends(user_dep)):
        allowed(user, cid)
        path = SNAPS / str(cid) / Path(name).name
        if not path.exists():
            raise HTTPException(404, "Ảnh đã bị xoá")
        return FileResponse(path)

    @app.get("/voices/{cid}.wav")
    def class_voice(cid: int, user=Depends(user_dep)):
        allowed(user, cid)
        path = VOICES / f"{cid}.wav"
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/assets/{name}")
    def assets(name: str):
        path = WEB / "assets" / Path(name).name
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "no-cache"})

    @app.get("/sounds/{name}")
    def sounds(name: str):
        path = WEB / "sounds" / Path(name).name
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path)

    # ================================================================ cảnh báo
    def event_out(e, names):
        return {**e, "class_name": names.get(e["classroom_id"], "?"), "name": BEHAVIOR_NAMES[e["behavior"]],
                "text": announcement(e["behavior"]),
                "snapshot": f"/snapshots/{e['snapshot']}" if e["snapshot"] else ""}

    def class_names():
        return {r["id"]: r["name"] for r in db.all("SELECT id, name FROM classrooms")}

    @app.get("/api/feed")
    def feed(after: int = 0, user=Depends(user_dep)):
        """Gọi mỗi giây: trạng thái các lớp + cảnh báo mới."""
        ids = db.class_ids_for(user)
        if not ids:
            return {"classes": [], "events": [], "today": {}}
        marks = ",".join("?" * len(ids))
        if after:
            rows = db.all(f"SELECT * FROM events WHERE id > ? AND classroom_id IN ({marks}) ORDER BY id LIMIT 50",
                          (after, *ids))
        else:
            rows = db.all(f"SELECT * FROM events WHERE classroom_id IN ({marks}) ORDER BY id DESC LIMIT 30", ids)[::-1]
        start = datetime.now().strftime("%Y-%m-%dT00:00:00")
        today = {}
        for r in db.all(f"SELECT classroom_id, behavior, COUNT(*) AS n FROM events WHERE time >= ? "
                        f"AND classroom_id IN ({marks}) GROUP BY classroom_id, behavior", (start, *ids)):
            today.setdefault(r["classroom_id"], {b: 0 for b in BEHAVIORS})[r["behavior"]] = r["n"]
        names = class_names()
        return {"classes": list_classes(user), "events": [event_out(e, names) for e in rows], "today": today}

    def query_events(user, class_id, behavior, date_from, date_to):
        ids = db.class_ids_for(user)
        if class_id:
            ids = [i for i in ids if i == class_id]
        if not ids:
            return "1 = 0", []
        where, args = [f"classroom_id IN ({','.join('?' * len(ids))})"], list(ids)
        if behavior:
            where.append("behavior = ?")
            args.append(behavior)
        if date_from:
            where.append("time >= ?")
            args.append(date_from + "T00:00:00")
        if date_to:
            where.append("time <= ?")
            args.append(date_to + "T23:59:59")
        return " AND ".join(where), args

    @app.get("/api/events")
    def events(class_id: int = 0, behavior: str = "", date_from: str = "", date_to: str = "",
               page: int = 1, size: int = 50, user=Depends(user_dep)):
        where, args = query_events(user, class_id, behavior, date_from, date_to)
        total = db.one(f"SELECT COUNT(*) AS n FROM events WHERE {where}", args)["n"]
        rows = db.all(f"SELECT * FROM events WHERE {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                      (*args, size, (max(page, 1) - 1) * size))
        names = class_names()
        return {"total": total, "rows": [event_out(e, names) for e in rows]}

    @app.get("/api/events.csv")
    def events_csv(class_id: int = 0, behavior: str = "", date_from: str = "", date_to: str = "",
                   user=Depends(user_dep)):
        where, args = query_events(user, class_id, behavior, date_from, date_to)
        names = class_names()
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Thời gian", "Lớp", "Học sinh (ID)", "Hành vi", "Kéo dài (giây)"])
        for e in db.all(f"SELECT * FROM events WHERE {where} ORDER BY id", args):
            w.writerow([e["time"].replace("T", " "), names.get(e["classroom_id"], ""), e["student"],
                        BEHAVIOR_NAMES[e["behavior"]], e["duration"]])
        return Response("﻿" + buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=canh_bao.csv"})

    @app.get("/api/stats")
    def stats(days: int = 7, class_id: int = 0, user=Depends(user_dep)):
        start = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
        where, args = query_events(user, class_id, "", start, "")
        rows = db.all(f"SELECT classroom_id, behavior, time FROM events WHERE {where}", args)
        names = class_names()
        empty = lambda: {b: 0 for b in BEHAVIORS}  # noqa: E731
        by_class, by_hour, by_day, totals = {}, {h: empty() for h in range(24)}, {}, empty()
        for i in range(days):
            by_day[(datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")] = empty()
        for r in rows:
            b = r["behavior"]
            by_class.setdefault(r["classroom_id"], empty())[b] += 1
            by_hour[int(r["time"][11:13])][b] += 1
            if r["time"][:10] in by_day:
                by_day[r["time"][:10]][b] += 1
            totals[b] += 1
        return {
            "totals": totals, "names": BEHAVIOR_NAMES,
            "by_class": sorted([{"id": k, "name": names.get(k, "?"), **v} for k, v in by_class.items()],
                               key=lambda x: -sum(x[b] for b in BEHAVIORS)),
            "by_hour": [{"label": f"{h}h", **v} for h, v in by_hour.items()],
            "by_day": [{"label": f"{d[8:10]}/{d[5:7]}", **v} for d, v in by_day.items()],
        }

    # ================================================================ giáo viên
    @app.get("/api/users")
    def users(_=Depends(admin_dep)):
        out = db.all("SELECT id, username, name, role, created FROM users ORDER BY role, name")
        for u in out:
            u["class_ids"] = [r["classroom_id"] for r in
                              db.all("SELECT classroom_id FROM assignments WHERE user_id = ?", (u["id"],))]
        return out

    def set_classes(uid, class_ids):
        db.run("DELETE FROM assignments WHERE user_id = ?", (uid,))
        for cid in class_ids:
            db.run("INSERT OR IGNORE INTO assignments(user_id, classroom_id) VALUES (?, ?)", (uid, int(cid)))

    @app.post("/api/users")
    def create_user(body: dict, _=Depends(admin_dep)):
        username, password = str(body.get("username", "")).strip(), str(body.get("password", ""))
        if len(username) < 3 or len(password) < 6:
            raise HTTPException(400, "Tên đăng nhập ít nhất 3 ký tự, mật khẩu ít nhất 6 ký tự")
        role = "admin" if body.get("role") == "admin" else "teacher"
        try:
            uid = db.create_user(username, body.get("name") or username, password, role)
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(400, f"Đã có tài khoản '{username}'")
            raise
        set_classes(uid, body.get("class_ids", []))
        return {"ok": True, "id": uid}

    @app.put("/api/users/{uid}")
    def update_user(uid: int, body: dict, admin=Depends(admin_dep)):
        role = "admin" if body.get("role") == "admin" else "teacher"
        if uid == admin["id"] and role != "admin":
            raise HTTPException(400, "Không thể tự bỏ quyền quản trị của chính mình")
        db.run("UPDATE users SET name = ?, role = ? WHERE id = ?", (str(body.get("name", "")).strip(), role, uid))
        if body.get("password"):
            from .db import hash_password
            if len(body["password"]) < 6:
                raise HTTPException(400, "Mật khẩu ít nhất 6 ký tự")
            db.run("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(body["password"]), uid))
            db.run("DELETE FROM sessions WHERE user_id = ?", (uid,))
        set_classes(uid, body.get("class_ids", []))
        return {"ok": True}

    @app.delete("/api/users/{uid}")
    def delete_user(uid: int, admin=Depends(admin_dep)):
        if uid == admin["id"]:
            raise HTTPException(400, "Không thể xoá chính mình")
        db.run("DELETE FROM users WHERE id = ?", (uid,))
        return {"ok": True}

    # ================================================================ cài đặt
    @app.get("/api/settings")
    def get_settings(_=Depends(admin_dep)):
        return p.settings()

    @app.post("/api/settings")
    def save_settings(body: dict, _=Depends(admin_dep)):
        clean = {}
        for k, v in body.items():
            if k in TUNABLE:
                clean[k] = int(v) if k == "imgsz" else float(v)
            elif k in ("fps_background", "fps_watch"):
                clean[k] = min(30.0, max(0.2, float(v)))
            elif k == "keep_days":
                clean[k] = max(1, int(v))
            elif k in ("server_sound", "save_snapshots"):
                clean[k] = bool(v)
            elif k in ("telegram_token", "telegram_chat_id"):
                clean[k] = str(v).strip()
        db.set_settings(clean)
        apply_settings(p.cfg, clean)
        return p.settings()

    @app.post("/api/telegram/find-chat")
    def find_chat(body: dict, _=Depends(admin_dep)):
        token = str(body.get("token", "")).strip()
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10).json()
        except requests.RequestException as e:
            raise HTTPException(400, f"Không kết nối được Telegram: {e}")
        if not r.get("ok"):
            raise HTTPException(400, "Token không đúng")
        chats = [u["message"]["chat"] for u in r["result"] if "message" in u]
        if not chats:
            raise HTTPException(400, "Chưa thấy tin nhắn nào. Hãy mở bot (hoặc nhóm có bot) trên Telegram, "
                                     "gửi 1 tin nhắn rồi thử lại.")
        chat = chats[-1]
        return {"chat_id": str(chat["id"]), "name": chat.get("title") or chat.get("first_name", "")}

    @app.post("/api/telegram/test")
    def test_telegram(body: dict, _=Depends(admin_dep)):
        s = p.settings()
        chat = str(body.get("chat_id") or s["telegram_chat_id"])
        if not (s["telegram_token"] and chat):
            raise HTTPException(400, "Chưa lưu token hoặc chat ID")
        p.telegram(s["telegram_token"], chat, "✅ Thử thông báo từ hệ thống giám sát lớp học")
        return {"ok": True}

    @app.post("/api/sound/test")
    def test_sound(body: dict, _=Depends(admin_dep)):
        cid = body.get("class_id")
        play_alert(str(body.get("behavior", "phone")), prefix=VOICES / f"{cid}.wav" if cid else None)
        return {"ok": True}

    @app.get("/api/info")
    def info(_=Depends(user_dep)):
        return {"urls": p.urls}

    @app.get("/api/qr")
    def qr(url: str, _=Depends(user_dep)):
        import qrcode
        import qrcode.image.svg
        svg = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).to_string()
        return Response(svg, media_type="image/svg+xml")

    # ================================================================ điện thoại làm camera
    @app.get("/station/{token}")
    def station_page(token: str):
        if not db.one("SELECT id FROM classrooms WHERE station_token = ?", (token,)):
            return Response("Link camera không đúng hoặc đã bị đổi. Hãy quét lại mã QR mới.", status_code=404,
                            media_type="text/plain; charset=utf-8")
        return FileResponse(WEB / "phone.html")

    @app.get("/api/station/{token}")
    def station_info(token: str):
        room = db.one("SELECT id, name, source FROM classrooms WHERE station_token = ?", (token,))
        if not room:
            raise HTTPException(404, "Link không đúng")
        return {"name": room["name"], "ready": room["source"] == "phone"}

    @app.websocket("/ws/station/{token}")
    async def ws_station(ws: WebSocket, token: str):
        await ws.accept()
        room = db.one("SELECT id, source FROM classrooms WHERE station_token = ?", (token,))
        w = mgr.get(room["id"]) if room else None
        if not room or room["source"] != "phone" or not w:
            await ws.send_text(json.dumps({"error": "Lớp này chưa được đặt nguồn camera là 'Điện thoại'. "
                                                    "Nhờ quản trị viên đổi trong mục Quản lý lớp."}))
            await ws.close()
            return
        await pump(ws, w, "Điện thoại (mã QR)")

    @app.websocket("/ws/broadcast/{cid}")
    async def ws_broadcast(ws: WebSocket, cid: int):
        """Giáo viên đã đăng nhập phát camera laptop/điện thoại của mình cho lớp được phân."""
        await ws.accept()
        user = db.session_user(ws.cookies.get("sid"))
        room = db.one("SELECT source FROM classrooms WHERE id = ?", (cid,))
        w = mgr.get(cid)
        error = ("Hết phiên đăng nhập, hãy đăng nhập lại" if not user else
                 "Bạn không được phân dạy lớp này" if cid not in db.class_ids_for(user) else
                 "Lớp này đang dùng camera cố định, không cần camera của máy này" if not room or room["source"] != "phone" else
                 "Lớp đang tạm dừng giám sát" if not w else "")
        if error:
            await ws.send_text(json.dumps({"error": error}, ensure_ascii=False))
            await ws.close()
            return
        await pump(ws, w, user["name"])

    async def pump(ws, w, who):
        """Nhận khung hình từ thiết bị. Thiết bị kết nối sau sẽ thay thế thiết bị trước."""
        me = object()
        w.stream_owner, w.streamer = me, who
        try:
            while True:
                data = await ws.receive_bytes()
                if w.stream_owner is not me:
                    await ws.send_text(json.dumps({"error": "Một thiết bị khác vừa bắt đầu phát camera cho lớp này"},
                                                  ensure_ascii=False))
                    await ws.close()
                    return
                w.phone.push_jpeg(data)
                await ws.send_text(json.dumps({"announcements": w.status["announcements"], "people": w.status["people"]},
                                              ensure_ascii=False))
        except WebSocketDisconnect:
            pass

    return app


def source_type(source):
    if not source:
        return "none"
    if source == "phone":
        return "phone"
    if source.isdigit():
        return "webcam"
    return "ip" if "://" in source else "video"


def source_label(source):
    """Tên ngắn của nguồn camera. Không bao giờ hiện mật khẩu camera."""
    from urllib.parse import urlparse
    if not source:
        return "Chưa có camera"
    if source == "phone":
        return "Thiết bị của giáo viên"
    if source.isdigit():
        return f"Webcam {source}"
    if "://" in source:
        return f"Camera IP {urlparse(source).hostname or ''}".strip()
    return f"Video: {Path(source).name.split('_', 1)[-1]}"
