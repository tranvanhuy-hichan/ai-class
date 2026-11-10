"""Nạp / lưu settings.json và áp cấu hình điều chỉnh được từ giao diện vào config.yaml đã nạp."""
import json

STORAGE_DEFAULTS = {"save_snapshots": True, "keep_days": 7, "max_storage_mb": 1000}

# Các tham số giáo viên chỉnh được trên giao diện: (nhóm trong config.yaml, khoá)
TUNABLE = {
    "head_down_ratio": ("rules", "head_down_ratio"),
    "phone_seconds": ("timing", "phone"),
    "head_down_seconds": ("timing", "head_down"),
    "sleeping_seconds": ("timing", "sleeping"),
    "cooldown": ("timing", "cooldown"),
    "imgsz": ("detection", "imgsz"),
}


def load_settings(settings_file):
    try:
        return json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def apply_settings(cfg, settings):
    for key, (group, name) in TUNABLE.items():
        if key in settings:
            cfg[group][name] = type(cfg[group][name])(settings[key])
    if "head_down_pose" in settings:
        cfg["rules"]["head_down_pose"] = bool(settings["head_down_pose"])


def current_settings(engine):
    """Toàn bộ cài đặt hiện tại (giá trị đang áp dụng + thông tin phần cứng) để giao diện hiển thị."""
    from .hardware import hardware, recommended_cameras
    s = {key: engine.cfg[g][n] for key, (g, n) in TUNABLE.items()}
    s["telegram_token"] = engine.settings.get("telegram_token", "")
    s["telegram_chat_id"] = engine.settings.get("telegram_chat_id", "")
    s["show_skeleton"] = engine.settings.get("show_skeleton", False)
    s["head_down_pose"] = bool(engine.cfg["rules"].get("head_down_pose", True))
    s["autostart"] = engine.settings.get("autostart", True)
    s["parallel"] = engine.parallel()
    s["multi_camera"] = engine.multi()
    s["max_cameras"] = int(engine.settings.get("max_cameras", 4))
    s["max_fps"] = engine.settings.get("max_fps", 2)
    s["gpu"] = engine.has_gpu()
    s["hw"] = {**hardware(), "recommended": recommended_cameras(hardware(), engine.has_gpu())}
    s["server_sound"] = engine.settings.get("server_sound", engine.cfg["output"]["sound"])
    s.update(engine.storage())
    return s
