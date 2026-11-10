"""Tự dọn ảnh cảnh báo và video tải lên để ổ cứng không bị đầy."""
import time
from pathlib import Path


def _files(folders):
    out = []
    for folder in folders:
        folder = Path(folder)
        if folder.exists():
            out += [f for f in folder.iterdir() if f.is_file()]
    return out


def usage(folders):
    """(số file, dung lượng MB)."""
    files = _files(folders)
    return len(files), sum(f.stat().st_size for f in files) / 1e6


def clean(folders, keep_days, max_mb, protect=()):
    """Xoá file cũ hơn keep_days ngày; nếu vẫn vượt max_mb thì xoá tiếp file cũ nhất.

    protect: các file không được xoá (vd video đang dùng làm nguồn camera).
    Trả về số file đã xoá.
    """
    protect = {Path(p).resolve() for p in protect if p}
    files = sorted((f for f in _files(folders) if f.resolve() not in protect), key=lambda f: f.stat().st_mtime)
    cutoff = time.time() - keep_days * 86400
    removed = 0
    total = sum(f.stat().st_size for f in files)
    for f in files:
        size = f.stat().st_size
        if f.stat().st_mtime < cutoff or total > max_mb * 1e6:
            f.unlink(missing_ok=True)
            total -= size
            removed += 1
    return removed
