"""Thông tin phần cứng máy đang chạy (CPU, RAM, GPU/VRAM) và số camera nên chạy cùng lúc."""
import os
import time


def cpu_name():
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    import platform
    return platform.processor() or platform.machine()


_hw_cache = (0.0, None)


def hardware():
    """Cấu hình máy và mức đang dùng (RAM, VRAM). Lưu tạm 3 giây vì được hỏi mỗi giây."""
    global _hw_cache
    if time.time() - _hw_cache[0] < 3 and _hw_cache[1]:
        return _hw_cache[1]
    gb = 2 ** 30
    hw = {"cpu": cpu_name(), "cores": os.cpu_count() or 1, "ram_gb": 0.0, "ram_used_gb": 0.0, "ram_free_gb": 0.0,
          "gpu": "", "vram_gb": 0.0, "vram_free_gb": 0.0}
    try:
        import psutil
        vm = psutil.virtual_memory()
        hw.update(ram_gb=vm.total / gb, ram_free_gb=vm.available / gb, ram_used_gb=(vm.total - vm.available) / gb)
    except ImportError:
        pass
    try:
        import torch
        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            hw.update(gpu=torch.cuda.get_device_name(0), vram_gb=total / gb, vram_free_gb=free / gb)
    except Exception:
        pass
    hw = {k: round(v, 1) if isinstance(v, float) else v for k, v in hw.items()}
    _hw_cache = (time.time(), hw)
    return hw


def recommended_cameras(hw, gpu):
    """Số camera nên chạy cùng lúc, tính theo bộ nhớ còn trống và sức mạnh xử lý.
    Đo thực tế trên RTX 3050 Laptop 4 GB: mỗi camera thêm khoảng 0,15 GB RAM và 0,2 GB VRAM; tổng khoảng 44 hình/giây;
    mỗi camera chỉ cần xử lý ~5 hình/giây (hành vi kéo dài vài giây) nên chạy được khoảng 8 camera. Máy chỉ có CPU tốn nặng hơn nhiều."""
    if gpu and hw["gpu"]:
        by_mem = int(min((hw["vram_free_gb"] - 0.3) / 0.25, (hw["ram_free_gb"] - 1.0) / 0.3))
        by_speed = 8 if hw["vram_gb"] < 7 else 12
        return max(1, min(by_mem, by_speed))
    by_mem = int((hw["ram_free_gb"] - 1.5) / 0.8)
    by_cpu = hw["cores"] // 6
    return max(1, min(by_mem, by_cpu, 3))
