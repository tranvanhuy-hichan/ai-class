"""Ứng dụng desktop Qt: python -m lophocai   (hoặc lệnh `lophocai` sau khi cài).

  python -m lophocai                 dùng webcam máy tính
  python -m lophocai --source 1      camera USB thứ 2
  python -m lophocai --source none   không tự thêm camera nào
"""
import argparse
import os
import sys
import threading
from datetime import datetime

from lophocai.storage.paths import DATA, FROZEN

if FROZEN:
    # App đã cài không có cửa sổ dòng lệnh (sys.stdout = None trên Windows). Phải chuyển thông tin
    # ra file TRƯỚC khi nạp thư viện AI, vì chúng in thông tin ngay lúc được nạp.
    _log = open(DATA / "app.log", "a", buffering=1, encoding="utf-8")
    sys.stdout = sys.stderr = _log
    print(f"\n===== Mở app lúc {datetime.now():%Y-%m-%d %H:%M:%S} =====")

# Trên một số bản Linux (vd GNOME thiếu khoá cấu hình antialiasing), plugin GTK3 theme của Qt
# gọi g_log với cờ lỗi nghiêm trọng và làm app bị Abort ngay khi tạo QApplication, không ném được
# ngoại lệ Python để bắt. Ép theme "generic" (Qt tự vẽ, không dùng GTK3) để tránh phụ thuộc này.
# Chỉ đặt khi người dùng/biến môi trường hệ thống chưa tự chọn theme khác.
os.environ.setdefault("QT_QPA_PLATFORMTHEME", "generic")

from lophocai.application.engine import Engine  # noqa: E402
from lophocai.application.settings import apply_settings, load_settings  # noqa: E402
from lophocai.detection.pipeline import load_config  # noqa: E402
from lophocai.integrations.phone.server import PhoneServer  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Lớp học AI")
    ap.add_argument("--source", default="0", help='Nguồn ban đầu: "0" webcam, link camera, file video, "none"')
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    from PySide6.QtCore import QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication(sys.argv)
    app.setApplicationName("Lớp học AI")

    # Chỉ một phiên chạy: hai bản cùng ghi một thư mục dữ liệu sẽ làm hỏng cài đặt và nhật ký.
    lock = QLockFile(str(DATA / "app.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "Lớp học AI", "Ứng dụng đang chạy rồi. Hãy chuyển sang cửa sổ đang mở.")
        return 0

    from . import theme
    settings_file = DATA / "settings.json"
    settings = load_settings(settings_file)
    theme.init(app, settings.get("theme", "system"))

    cfg = load_config(args.config)
    apply_settings(cfg, settings)
    engine = Engine(cfg, settings, DATA, DATA / "uploads", settings_file)
    threading.Thread(target=engine.cleanup_loop, daemon=True).start()
    if not engine.cameras and args.source != "none":
        engine.add_camera("Camera 1", args.source)

    phone = PhoneServer(engine, DATA)
    phone_url = phone.start()

    from .main_window import MainWindow
    window = MainWindow(engine, phone_url=phone_url)
    window.show()
    threading.Thread(target=engine.autostart, daemon=True).start()

    code = app.exec()
    phone.stop()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
