"""Mở giao diện thành 1 cửa sổ ứng dụng riêng (không thanh địa chỉ, không tab).

Dùng chế độ --app của trình duyệt nhân Chromium có sẵn trên máy (Edge luôn có trên Windows 10/11;
Chrome/Chromium trên Ubuntu). Cửa sổ dùng hồ sơ trình duyệt riêng nên theo dõi được lúc người dùng
đóng nó, và đóng cửa sổ = tắt app. Không có trình duyệt nào như vậy thì mở trình duyệt mặc định.
"""
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from .paths import DATA


def _candidates():
    if sys.platform == "win32":
        roots = [os.environ.get(k, "") for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe",
               r"BraveSoftware\Brave-Browser\Application\brave.exe"]
        return [str(Path(r) / p) for r in roots if r for p in rel]
    if sys.platform == "darwin":
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"]
    names = ["google-chrome", "google-chrome-stable", "microsoft-edge", "brave-browser", "chromium", "chromium-browser"]
    return [p for p in (shutil.which(n) for n in names) if p]


def find_browser():
    for path in _candidates():
        if Path(path).exists():
            return path
    return None


def _profile_dir(browser):
    # Chromium bản snap (Ubuntu) chỉ được ghi vào ~/snap/chromium/common
    if "snap" in os.path.realpath(browser) or (Path("/snap/bin/chromium").exists() and "chromium" in browser):
        return Path.home() / "snap" / "chromium" / "common" / "LopHocAI-window"
    return DATA / "window-profile"


def open_window(url):
    """Mở cửa sổ app. Trả về tiến trình cửa sổ (để chờ người dùng đóng), hoặc None nếu
    phải dùng trình duyệt mặc định (khi đó không biết lúc nào người dùng đóng)."""
    browser = find_browser()
    if not browser:
        webbrowser.open(url)
        return None
    profile = _profile_dir(browser)
    profile.mkdir(parents=True, exist_ok=True)
    cmd = [browser, f"--app={url}", f"--user-data-dir={profile}", "--window-size=1440,900",
           "--no-first-run", "--no-default-browser-check",
           "--autoplay-policy=no-user-gesture-required"]  # phát tiếng cảnh báo không cần bấm trước
    if sys.platform.startswith("linux"):
        cmd.append("--class=LopHocAI")  # để thanh dock hiện đúng biểu tượng "Lớp học AI"
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def wait_closed(proc):
    """Chờ người dùng đóng cửa sổ. Trả về False nếu cửa sổ thoát ngay (trình duyệt chuyển việc
    cho 1 tiến trình khác) - khi đó không theo dõi được, app tiếp tục chạy tới khi bấm "Tắt ứng dụng"."""
    t0 = time.time()
    proc.wait()
    return time.time() - t0 > 5
