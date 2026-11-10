# Cấu hình PyInstaller: đóng gói ứng dụng desktop + mô hình AI + tài nguyên thành 1 thư mục chạy được,
# không cần cài Python. Dùng chung cho Linux và Windows.
#   pyinstaller packaging/lophocai.spec --noconfirm
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH do PyInstaller cung cấp)

# Chỉ gói mô hình app thật sự dùng. Bản đóng gói chạy PyTorch CPU nên không cần các mô hình nặng (m, x) và bản sao lưu;
# build trên máy có nhiều file lạ trong weights/ cũng không làm bộ cài phình ra.
SKIP_WEIGHTS = ("yolo11m", "yolo11x", "yolo11s.pt", "_cu.pt", "behavior_v1.pt")
datas = [
    (str(ROOT / "resources"), "resources"),   # âm thanh cảnh báo, trang điện thoại
    *[(str(f), "weights") for f in sorted((ROOT / "weights").iterdir())
      if f.is_file() and not any(k in f.name for k in SKIP_WEIGHTS)],
    (str(ROOT / "config.yaml"), "."),
]
binaries, hiddenimports = [], []
# torchvision: phải gom cả file _C (.so/.pyd) chứa hàm nms, nếu không AI báo lỗi "torchvision::nms does not exist"
for pkg in ("ultralytics", "mediapipe", "torchvision"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("uvicorn") + [
    "websockets", "qrcode.image.svg", "lap", "soundfile",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    # Bộ PySide6 đầy đủ rất nặng; app chỉ dùng Widgets/Gui/Core/Svg nên loại các phần còn lại
    excludes=["tensorflow", "tensorboard", "IPython", "jupyter", "notebook", "pytest",
              "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtMultimedia",
              "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf"],
    # Giữ mã nguồn .py của torch/ultralytics: một số chỗ cần đọc mã nguồn lúc chạy
    module_collection_mode={"torch": "pyz+py", "torchvision": "pyz+py", "ultralytics": "pyz+py"},
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LopHocAI",
    console=False,  # không hiện cửa sổ dòng lệnh; thông tin ghi vào app.log
    icon=str(ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.png")),
)
coll = COLLECT(exe, a.binaries, a.datas, name="LopHocAI")  # noqa: F821
