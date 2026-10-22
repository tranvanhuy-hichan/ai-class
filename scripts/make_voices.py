"""Tạo sẵn file âm thanh cảnh báo tiếng Việt (chuông "ding-dong" + giọng đọc).

  python scripts/make_voices.py                               # giọng nữ HoaiMy (mặc định)
  python scripts/make_voices.py --voice vi-VN-NamMinhNeural   # giọng nam
  python scripts/make_voices.py --engine gtts                 # giọng Google

Chỉ cần Internet lúc chạy lệnh này. File được lưu ở web/sounds/ và dùng được mãi
không cần mạng, cho cả loa máy chạy hệ thống lẫn trình duyệt:
  <hành vi>.wav      chuông + câu đọc (loa máy chủ)
  chime.wav          chỉ tiếng chuông       \\  trình duyệt ghép: chuông -> "Lớp 10A1" ->
  say_<hành vi>.wav  chỉ câu đọc            /  "Có học sinh dùng điện thoại"
Muốn đổi câu đọc thì sửa PHRASES trong core/tts.py.
"""
import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.tts import PHRASES, RATE, chime, save_wav, silence, speak  # noqa: E402

OUT = ROOT / "web" / "sounds"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["edge", "gtts"], default="edge")
    ap.add_argument("--voice", default="vi-VN-HoaiMyNeural", help="vi-VN-HoaiMyNeural (nữ) hoặc vi-VN-NamMinhNeural (nam)")
    ap.add_argument("--rate", default="-5%", help="Tốc độ đọc của edge-tts, vd -10%% là chậm hơn")
    a = ap.parse_args()

    save_wav(OUT / "chime.wav", np.concatenate([chime(), silence(0.1)]))
    for key, text in PHRASES.items():
        voice = speak(text, a.engine, a.voice, a.rate)
        save_wav(OUT / f"say_{key}.wav", np.concatenate([voice, silence(0.15)]))
        full = np.concatenate([chime(), silence(0.15), voice, silence(0.15)])
        save_wav(OUT / f"{key}.wav", full)
        print(f"✔ web/sounds/{key}.wav  ({len(full) / RATE:.1f}s)  \"{text}\"")


if __name__ == "__main__":
    main()
