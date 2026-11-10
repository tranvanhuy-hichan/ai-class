"""Đường dẫn dùng chung, chạy đúng cả khi chạy code Python lẫn khi đã đóng gói thành app (.exe).

RES  - tài nguyên đi kèm app, chỉ đọc: mô hình AI, âm thanh, trang điện thoại, config.yaml
DATA - dữ liệu người dùng, ghi được: cơ sở dữ liệu, ảnh cảnh báo, video tải lên, chứng chỉ HTTPS
       (app Windows: %LOCALAPPDATA%/LopHocAI, vì thư mục Program Files không ghi được)
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# Chạy từ mã nguồn: thư mục tài nguyên là gốc dự án (chứa config.yaml, weights/, resources/), không phải
# thư mục package (src/lophocai/storage/..). PyInstaller đặt tài nguyên tại sys._MEIPASS.
_SRC_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RES = Path(getattr(sys, "_MEIPASS", _SRC_ROOT))

if FROZEN:
    DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "LopHocAI"
else:
    DATA = RES / "workspace" / "appdata"
DATA.mkdir(parents=True, exist_ok=True)


def res(path):
    """Đường dẫn tương đối -> tính từ thư mục tài nguyên của app."""
    p = Path(path)
    return p if p.is_absolute() else RES / p
