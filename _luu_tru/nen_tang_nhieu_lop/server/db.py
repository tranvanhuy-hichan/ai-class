"""Cơ sở dữ liệu SQLite (1 file, không cần cài thêm gì) + mật khẩu + phiên đăng nhập."""
import hashlib
import json
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'teacher')),
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS classrooms (
    id INTEGER PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL DEFAULT '',      -- "0" webcam | rtsp://... | http://... | "phone" | file video
    enabled INTEGER NOT NULL DEFAULT 1,
    station_token TEXT NOT NULL,          -- mã bí mật cho điện thoại làm camera của lớp
    telegram_chat_id TEXT NOT NULL DEFAULT '',
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assignments (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, classroom_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    classroom_id INTEGER NOT NULL REFERENCES classrooms(id) ON DELETE CASCADE,
    time TEXT NOT NULL,
    student INTEGER NOT NULL,
    behavior TEXT NOT NULL,
    duration REAL NOT NULL,
    snapshot TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_class_time ON events(classroom_id, time);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

SESSION_DAYS = 30


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def hash_password(password):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
    return f"scrypt${salt.hex()}${h.hex()}"


def check_password(password, stored):
    try:
        _, salt, h = stored.split("$")
        test = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** 14, r=8, p=1)
        return secrets.compare_digest(test.hex(), h)
    except ValueError:
        return False


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.executescript(SCHEMA)

    def all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        with self.lock:
            r = self.conn.execute(sql, args).fetchone()
            return dict(r) if r else None

    def run(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).lastrowid

    # ---------------------------------------------------------- cài đặt
    def settings(self):
        return {r["key"]: json.loads(r["value"]) for r in self.all("SELECT key, value FROM settings")}

    def set_settings(self, values):
        for k, v in values.items():
            self.run("INSERT INTO settings(key, value) VALUES (?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, json.dumps(v)))

    # ---------------------------------------------------------- tài khoản
    def create_user(self, username, name, password, role):
        return self.run("INSERT INTO users(username, name, pw_hash, role, created) VALUES (?, ?, ?, ?, ?)",
                        (username.strip().lower(), name.strip(), hash_password(password), role, now_iso()))

    def login(self, username, password):
        user = self.one("SELECT * FROM users WHERE username = ?", (username.strip().lower(),))
        if not user or not check_password(password, user["pw_hash"]):
            return None
        token = secrets.token_urlsafe(32)
        expires = (datetime.now() + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")
        self.run("INSERT INTO sessions(token, user_id, expires) VALUES (?, ?, ?)", (token, user["id"], expires))
        return token

    def session_user(self, token):
        if not token:
            return None
        return self.one("SELECT u.id, u.username, u.name, u.role FROM sessions s JOIN users u ON u.id = s.user_id "
                        "WHERE s.token = ? AND s.expires > ?", (token, now_iso()))

    def class_ids_for(self, user):
        """Lớp mà người dùng được xem: quản trị viên xem tất cả."""
        if user["role"] == "admin":
            return [r["id"] for r in self.all("SELECT id FROM classrooms")]
        return [r["classroom_id"] for r in self.all("SELECT classroom_id FROM assignments WHERE user_id = ?",
                                                    (user["id"],))]
