# Cấu hình PyInstaller: đóng gói web.py + mô hình AI + giao diện thành 1 thư mục chạy được,
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
    (str(ROOT / "web"), "web"),
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
    "websockets", "python_multipart", "multipart", "qrcode.image.svg", "lap", "soundfile",
]

a = Analysis(  # noqa: F821
    [str(ROOT / "web.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tensorflow", "tensorboard", "IPython", "jupyter", "notebook", "pytest"],
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
    console=False,  # không hiện cửa sổ dòng lệnh; giao diện mở thành cửa sổ app, thông tin ghi vào app.log
    icon=str(ROOT / "packaging" / ("icon.ico" if sys.platform == "win32" else "icon.png")),
)
coll = COLLECT(exe, a.binaries, a.datas, name="LopHocAI")  # noqa: F821
