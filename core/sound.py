"""Phát âm thanh cảnh báo qua loa của máy chạy hệ thống (Windows / macOS / Linux).

Nếu có file web/sounds/<hành vi>.wav (tạo bằng scripts/make_voices.py) thì phát chuông
+ giọng đọc tiếng Việt, ví dụ "Có học sinh dùng điện thoại". Không có thì chỉ kêu bíp.
Các cảnh báo được xếp hàng phát lần lượt, không chồng tiếng lên nhau.
"""
import platform
import queue
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from .paths import res

SOUNDS = res("web/sounds")
# Dự phòng khi chưa có file giọng đọc: (tần số Hz, số tiếng bíp)
TONES = {"phone": (1000, 2), "head_down": (800, 2), "sleeping": (1300, 3), "fighting": (1500, 4), "smoking": (1700, 3)}
_queue = queue.Queue()
_pending = set()
_worker = None


def _beep_file(freq, beeps):
    rate = 22050
    tone = np.sin(2 * np.pi * freq * np.arange(int(rate * 0.18)) / rate)
    tone *= np.minimum(1, np.linspace(0, 20, tone.size)) * np.minimum(1, np.linspace(20, 0, tone.size))
    gap = np.zeros(int(rate * 0.1))
    data = np.concatenate([np.concatenate([tone, gap]) for _ in range(beeps)])
    path = Path(tempfile.gettempdir()) / f"khkt_alert_{freq}_{beeps}.wav"
    if not path.exists():
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((data * 0.6 * 32767).astype(np.int16).tobytes())
    return path


def sound_file(behavior):
    voice = SOUNDS / f"{behavior}.wav"
    return voice if voice.exists() else _beep_file(*TONES.get(behavior, (1000, 2)))


def _play(path):
    if platform.system() == "Windows":
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME)
        return
    for cmd in (["paplay"], ["aplay", "-q"], ["afplay"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            return
    print("\a", end="", flush=True)


def _files(behavior, prefix):
    """Có file tên lớp: chuông -> "Lớp 10A1" -> "Có học sinh...". Không có: file gộp sẵn."""
    say, ding = SOUNDS / f"say_{behavior}.wav", SOUNDS / "chime.wav"
    if prefix and Path(prefix).exists() and say.exists() and ding.exists():
        return [ding, Path(prefix), say]
    return [sound_file(behavior)]


def _run():
    while True:
        key, behavior, prefix = _queue.get()
        try:
            for f in _files(behavior, prefix):
                _play(f)
        except Exception as e:
            print(f"[!] Không phát được âm thanh: {e}")
        finally:
            _pending.discard(key)


def play_alert(behavior="phone", prefix=None):
    """Xếp hàng phát cảnh báo (không chặn chương trình). Cảnh báo giống hệt đang chờ phát thì bỏ qua.

    prefix: file .wav đọc tên lớp (vd "Lớp 10A1") phát trước câu cảnh báo.
    """
    global _worker
    key = (behavior, str(prefix))
    if key in _pending or len(_pending) >= 4:
        return
    _pending.add(key)
    if _worker is None:
        _worker = threading.Thread(target=_run, daemon=True)
        _worker.start()
    _queue.put((key, behavior, prefix))
