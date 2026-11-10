"""Hàm tiện ích mô tả camera/hành vi dùng chung giữa application, runtime và web."""
import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

ANNOUNCE = {"phone": "dùng điện thoại", "head_down": "nằm gục xuống bàn", "sleeping": "ngủ gật",
            "fighting": "đánh nhau", "smoking": "hút thuốc"}


def source_kind(source):
    if source == "phone":
        return "phone"
    if source.isdigit():
        return "webcam"
    if source.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if "://" in source:
        return "ip"
    return "file"


def display_name(source):
    """Tên ngắn để hiện trên giao diện. Không bao giờ hiện mật khẩu camera."""
    if source.isdigit():
        return f"Webcam {source}"
    if "://" in source:
        return f"Camera IP {urlparse(source).hostname or ''}".strip()
    return f"Video: {Path(source).name}"


def mask_source(source):
    """Che mật khẩu camera khi gửi ra giao diện."""
    return re.sub(r"(//[^/@:]+):[^/@]*@", r"\1:***@", source)


def view_key(source):
    """Mỗi camera nhớ cách chỉnh hình riêng. Băm tên nguồn để không lưu mật khẩu camera dạng chữ."""
    return hashlib.sha1(source.encode()).hexdigest()[:10]


def announcement(behavior, count=1):
    """Câu thông báo chung, không nêu số thứ tự học sinh."""
    who = "Có học sinh" if count == 1 else f"Có {count} học sinh"
    return f"{who} {ANNOUNCE[behavior]}"
