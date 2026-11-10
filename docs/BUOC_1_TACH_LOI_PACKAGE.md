# Bước 1 — Tách lõi thành package `src/lophocai/` (đã hoàn thành phần tách; chưa chuyển `web.py` sang dùng nó)

Ngày thực hiện: 10/11/2026.

## 1. Đã làm

- Tạo `pyproject.toml` khai báo trực tiếp mọi dependency import được (`requests`, `psutil`, `numpy` trước đây dựa vào transitive), nhóm `web`/`phone`/`training`/`dev` tách biệt runtime lõi.
- Tạo `src/lophocai/` theo đúng cấu trúc đích ở mục 4 của `KE_HOACH_CHUYEN_NATIVE.md`, đã có nội dung thật (không phải thư mục rỗng) cho các phần sau:

| Thư mục | Nội dung |
|---|---|
| `storage/` | `paths.py`, `cleanup.py`, `focus.py`, `events.py` (tách từ `display.py`) |
| `detection/` | `pipeline.py`, `rules.py`, `signals.py`, `fight.py` — **không đổi thuật toán**, chỉ đổi import |
| `video/` | `sources.py` (từ `camera.py`), `overlay.py` (Drawer, tách từ `display.py`), `transforms.py` (adjust/clean_view, tách từ `web.py`) |
| `runtime/` | `fps.py` (FPSMeter, tách từ `display.py`), `scheduler.py` (Gate), `camera_worker.py` (class `Camera`, tách từ `web.py`) |
| `application/` | `engine.py` (class `Engine`), `hardware.py`, `settings.py` |
| `domain/` | `models.py` (mask_source, source_kind, view_key, announcement...) |
| `integrations/` | `audio.py` (từ `sound.py`), `tts.py`, `phone/security.py` (lan_ip, is_local), `phone/certificates.py` (make_cert) |
| `web/` | `routes/api.py` (toàn bộ `create_app` + 29 route, nguyên trạng), `app.py` (entrypoint CLI, thay cho phần `main()` của `web.py`), `window.py` (giữ cho web dự phòng, như tài liệu yêu cầu) |
| `cli/` | `preview.py` (từ `app.py`), `evaluate.py` (từ `evaluate_clips.py`) |

- `core/`, `web.py`, `app.py`, `evaluate_clips.py` **giữ nguyên, chưa xoá, chưa sửa** — vẫn là bản đang chạy thật, đúng yêu cầu "giữ wrapper tạm thời" của tài liệu.
- Cài `lophocai` ở chế độ editable (`pip install -e . --no-deps`) vào `.venv-build` để kiểm thử.

## 2. Thay đổi hành vi duy nhất phải thực hiện (không tránh được)

`core/paths.py` tính `RES` bằng `Path(__file__).resolve().parent.parent` (vì `core/` ở ngay dưới gốc dự án). File mới `storage/paths.py` nằm sâu hơn 2 cấp (`src/lophocai/storage/`), nên phải đổi thành `.parent.parent.parent.parent` để `RES` vẫn trỏ đúng gốc dự án (chứa `config.yaml`, `web/`, `weights/`). Đã kiểm chứng bằng cách import trực tiếp: `RES` ra đúng gốc dự án, `config.yaml` và `web/` được tìm thấy.

Đây là thay đổi kỹ thuật bắt buộc do đổi cấu trúc thư mục, không phải thay đổi thuật toán hay ngưỡng.

## 3. Đối chiếu đã thực hiện

1. **Import toàn bộ 26 module mới** — không lỗi.
2. **4 bộ test gốc (`tests/`, trỏ `core/`)** — chạy lại sau khi tạo package mới: 25/25 pass, không đổi (core/ chưa bị động tới).
3. **Bản sao tạm của 4 bộ test trỏ vào `lophocai.*`** — tạo tạm để đối chiếu logic lõi mới cho cùng kết quả, 25/25 pass giống hệt, sau đó **đã xoá theo yêu cầu của bạn** (quyết định: không giữ 2 bộ test song song cho đến khi `web.py` chính thức chuyển sang dùng `lophocai`).
4. **Khởi tạo `Engine` thật** với `config.yaml` thật, thư mục dữ liệu tạm: `modes_info()`, `overview()`, `storage()` trả đúng giá trị mong đợi (2 chế độ Lớp học/Hành lang, 0 người, mặc định lưu trữ 7 ngày/1000 MB).
5. **Gọi `create_app()` thật** với Engine thật: tạo thành công FastAPI app với 36 route (29 route nghiệp vụ + route tự động của FastAPI/StaticFiles).

Chưa kiểm chứng được (cần phần cứng thật, nằm ngoài khả năng phiên này):
- Chạy thật với webcam/video — không có file video mẫu nào trong `clips/` ở máy này để thử `add_camera` + `start`.
- Benchmark FPS/độ trễ trước/sau (vẫn treo từ Bước 0).

## 4. Việc cố tình CHƯA làm ở Bước 1 này

- **Chưa sửa `web.py` để gọi qua lõi mới.** Tài liệu yêu cầu "Web cũ phải hoạt động qua lõi mới trước khi viết đầy đủ Qt" — đây là bước tiếp theo, cần sửa cẩn thận từng route và chạy thử thật với camera vì rủi ro cao (không có camera thật ở đây để tự kiểm chứng toàn bộ luồng hiển thị/MJPEG/WebSocket điện thoại).
- **Chưa sửa `scripts/`, `evaluate_clips.py`, `app.py` gốc** để dùng package mới — chúng vẫn chạy qua `core/` như cũ.
- **Chưa đổi `.github/workflows/`, PyInstaller spec** để build từ `src/lophocai/` — nằm ở Bước 4.
- **Chưa xoá `core/`** — theo đúng nguyên tắc "giữ wrapper tạm thời", chỉ xoá khi `web.py` đã chuyển hẳn và kiểm thử xong.

## 5. Rủi ro cần bạn lưu ý trước khi làm tiếp

- `web/routes/api.py` còn giữ gần như y nguyên toàn bộ route cũ (chủ ý, tránh sửa 2 việc cùng lúc). Khi chuyển `web.py` sang dùng lõi mới, cần test thủ công tối thiểu: mở trang `/`, thêm 1 camera webcam thật, xem video, đổi chế độ, lưu cài đặt — tất cả những việc cần màn hình/camera thật mà tôi không có ở đây.
- `Engine.__init__` đổi chữ ký (`cfg, settings, data_dir, uploads_dir, settings_file` thay vì `cfg, settings` + đọc global `DATA`/`SETTINGS_FILE`). Bất kỳ chỗ nào còn tạo `Engine(...)` kiểu cũ sẽ lỗi ngay khi chạy — đã audit: chỉ `web.py` gốc tạo `Engine`, chưa sửa nên chưa bị ảnh hưởng.

## 6. Đề xuất bước tiếp theo

Sửa `web.py` để nó trở thành một wrapper mỏng chỉ gọi `lophocai.web.app:main`, loại bỏ toàn bộ logic trùng lặp — đúng tinh thần "Hoàn thành khi kiểm thử cũ và kiểm thử dịch vụ/HTTP tương ứng chạy qua, dữ liệu cũ vẫn đọc được" của Bước 1. Việc này cần chạy thử thật (mở trình duyệt, bật camera) trước khi coi là xong, nên cần bạn xác nhận lại trên máy có camera trước khi tôi xoá `core/`.
