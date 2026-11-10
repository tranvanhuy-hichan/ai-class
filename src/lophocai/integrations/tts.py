"""Tạo âm thanh cảnh báo tiếng Việt: tiếng chuông + giọng đọc (Microsoft Edge TTS / Google TTS).

Chỉ cần Internet lúc tạo file. File .wav tạo ra dùng mãi không cần mạng.
"""
import asyncio
import tempfile
import threading
import time
from pathlib import Path

import numpy as np

RATE = 24000
VOICE = "vi-VN-HoaiMyNeural"

PHRASES = {
    "phone": "Có học sinh dùng điện thoại",
    "sleeping": "Có học sinh ngủ gật",
    "head_down": "Có học sinh nằm gục xuống bàn",
    "fighting": "Có học sinh đánh nhau",
    "smoking": "Có học sinh hút thuốc",
}


def chime():
    """Tiếng chuông 2 nốt "ding-dong" để thu hút chú ý trước khi đọc."""
    parts = []
    for freq in (988, 784):  # nốt Si và Sol
        t = np.arange(int(RATE * 0.45)) / RATE
        tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * 2 * freq * t)
        parts.append(tone * np.exp(-5 * t) * np.minimum(1, t * 200))
    return np.concatenate(parts) * 0.35


def silence(seconds):
    return np.zeros(int(RATE * seconds))


def speak(text, engine="edge", voice=VOICE, rate="-5%"):
    """Đọc 1 câu, trả về mảng âm thanh RATE Hz. Cần Internet."""
    import soundfile as sf
    mp3 = Path(tempfile.mkdtemp()) / "tts.mp3"
    if engine == "edge":
        import edge_tts
        asyncio.run(edge_tts.Communicate(text, voice, rate=rate).save(str(mp3)))
    else:
        from gtts import gTTS
        gTTS(text, lang="vi").save(str(mp3))
    data, sr = sf.read(str(mp3))
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != RATE:  # đổi tần số lấy mẫu cho khớp tiếng chuông
        data = np.interp(np.linspace(0, len(data), int(len(data) * RATE / sr), endpoint=False),
                         np.arange(len(data)), data)
    return data / max(1e-6, np.abs(data).max()) * 0.9  # chuẩn hoá cho đủ to


def save_wav(path, audio):
    import soundfile as sf
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, RATE, subtype="PCM_16")


_lock = threading.Lock()


def make_class_clip(name, path, tries=3):
    """Tạo file đọc tên lớp, vd "Lớp 10A1". Trả về False nếu không có mạng/thư viện.

    Tạo lần lượt từng file (dịch vụ đọc hay từ chối khi nhận nhiều yêu cầu cùng lúc).
    """
    text = name if name.lower().startswith("lớp") else f"Lớp {name}"
    with _lock:
        for i in range(tries):
            try:
                save_wav(path, np.concatenate([speak(text), silence(0.1)]))
                return True
            except Exception as e:
                err = e
                time.sleep(2 * (i + 1))
    print(f"[i] Không tạo được giọng đọc tên lớp '{name}' (cần Internet): {err}")
    return False
