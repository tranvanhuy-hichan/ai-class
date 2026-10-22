"""Chương trình chính: nhận diện hành vi bất thường của học sinh từ webcam/video.

Ví dụ:
  python app.py                       # webcam máy tính
  python app.py --source 1            # camera USB thứ 2
  python app.py --source http://192.168.1.5:8080/video          # điện thoại (app IP Webcam)
  python app.py --source "rtsp://admin:matkhau@192.168.1.64:554/Streaming/Channels/101"  # camera lớp
  python app.py --source lop_hoc.mp4  # video có sẵn
  python app.py --source lop_hoc.mp4 --save ket_qua.mp4 --no-show
Nhấn Q để thoát.
"""
import argparse
import time

import cv2

from core.camera import VideoSource
from core.display import Drawer, EventLogger, FPSMeter
from core.pipeline import Pipeline, load_config
from core.rules import BEHAVIOR_NAMES
from core.sound import play_alert


def main():
    ap = argparse.ArgumentParser(description="Hệ thống cảnh báo hành vi bất thường trong lớp học")
    ap.add_argument("--source", default="0", help="Số thứ tự webcam, link camera điện thoại/IP, hoặc file video")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--save", default="", help="Lưu video kết quả ra file .mp4")
    ap.add_argument("--no-show", action="store_true", help="Không mở cửa sổ hiển thị")
    args = ap.parse_args()

    cfg = load_config(args.config)
    pipe = Pipeline(cfg)
    drawer = Drawer(cfg["output"].get("font", ""))
    logger = EventLogger(cfg["output"]["log_dir"], cfg["output"]["save_snapshots"])
    fps_meter = FPSMeter()

    try:
        src = VideoSource(args.source)
    except RuntimeError as e:
        raise SystemExit(str(e))
    video_fps = src.fps
    writer = None
    t0, frame_idx = time.time(), 0

    print("Đang chạy... nhấn Q để thoát.")
    try:
        while True:
            frame = src.read()
            if frame is None:
                if src.live:
                    continue  # camera đang kết nối lại
                break
            # Camera trực tiếp: dùng đồng hồ thật. Video: dùng thời gian trong video để
            # kết quả không phụ thuộc máy chạy nhanh hay chậm.
            t = time.time() - t0 if src.live else frame_idx / video_fps
            frame_idx += 1

            people, alerts = pipe.process(frame, t)
            out = drawer.draw(frame, people, fps_meter.tick())
            for a in alerts:
                logger.log(a, out)
            if cfg["output"]["sound"]:
                for b in dict.fromkeys(a["behavior"] for a in alerts):
                    play_alert(b)

            if args.save:
                if writer is None:
                    h, w = out.shape[:2]
                    writer = cv2.VideoWriter(args.save, cv2.VideoWriter_fourcc(*"mp4v"), video_fps, (w, h))
                writer.write(out)
            if not args.no_show:
                cv2.imshow("Canh bao hanh vi lop hoc", out)
                if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q")):
                    break
    finally:
        src.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()
        logger.close()

    print("\n===== TỔNG KẾT =====")
    for b, name in BEHAVIOR_NAMES.items():
        print(f"  {name}: {logger.counts.get(b, 0)} lần")
    print(f"Nhật ký: {logger.path}")


if __name__ == "__main__":
    main()
