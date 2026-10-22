"""Đường dẫn dùng chung, chạy đúng cả khi chạy code Python lẫn khi đã đóng gói thành app (.exe).

RES  - tài nguyên đi kèm app, chỉ đọc: giao diện web, mô hình AI, file âm thanh, config.yaml
DATA - dữ liệu người dùng, ghi được: cơ sở dữ liệu, ảnh cảnh báo, video tải lên, chứng chỉ HTTPS
       (app Windows: %LOCALAPPDATA%/LopHocAI, vì thư mục Program Files không ghi được)
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
RES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

if FROZEN:
    DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "LopHocAI"
else:
    DATA = RES / "appdata"
DATA.mkdir(parents=True, exist_ok=True)


def res(path):
    """Đường dẫn tương đối -> tính từ thư mục tài nguyên của app."""
    p = Path(path)
    return p if p.is_absolute() else RES / p
