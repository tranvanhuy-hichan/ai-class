# Bước 0 — Chốt đường cơ sở (trước khi chuyển native)

Ngày thực hiện: 10/11/2026. Không có mã nào bị thay đổi hành vi; chỉ khôi phục một file dữ liệu bị thiếu trong working tree và ghi lại hiện trạng.

## 1. Sự cố model đã xử lý

- `weights/behavior_lop.pt` bị xóa khỏi working tree nhưng `config.yaml` (dòng 17, 76) vẫn tham chiếu đến nó ở cả `models.custom_behavior` và override cho chế độ lớp học.
- File chưa từng được commit vào git (không có trong lịch sử, bị ignore vì là binary lớn).
- Tìm thấy bản giống hệt trong bản cài đã build trước đó: `~/.local/opt/lophocai/_internal/weights/behavior_lop.pt` (19.242.394 bytes).
- Đã copy file này về `weights/behavior_lop.pt`. Không thay model nào khác, không đổi config.
- Các file liên quan khác trong `weights/`: `behavior.pt` (bản cũ biết hút thuốc), `behavior_lop_cu.pt` (bản cũ, bị `.gitignore` loại qua rule `weights/*_cu.pt`), `behavior_v1.pt`.

## 2. Kết quả 4 bộ test hiện có

Môi trường: `.venv-build` (Python 3.14.7, torch 2.14.1 CPU, fastapi 0.159.1, opencv 5.0.0, ultralytics 8.4.183). pytest không có sẵn trong venv này (chỉ dùng để build), đã cài thêm `pytest 9.2.0` vào venv để chạy test — không ảnh hưởng runtime ứng dụng.

```
tests/test_classroom_crowd.py — 7 passed
tests/test_fight.py           — 8 passed
tests/test_focus.py           — 4 passed
tests/test_rules.py           — 6 passed
TOTAL: 25 passed in 1.33s
```

Không có lỗi sẵn có nào cần ghi nhận.

## 3. Kiểm kê route HTTP (`web.py: create_app()`, dòng 762–1093)

| Method | Path | Mục đích (tóm tắt) |
|---|---|---|
| GET | `/` | Trang quản trị (index.html) |
| GET | `/phone` | Trang điện thoại |
| GET | `/video/{cam_id}` | MJPEG stream camera |
| GET | `/api/cameras/{cam_id}/frame.jpg` | Một khung JPEG |
| GET | `/api/status` | Trạng thái camera/hệ thống |
| GET | `/api/focus` | Dữ liệu tập trung |
| GET | `/api/stats` | Thống kê |
| GET | `/api/info` | Thông tin phần cứng/hệ thống |
| GET/POST | `/api/mode` | Đọc/đổi chế độ Lớp học - Hành lang |
| GET/POST | `/api/cameras` | Danh sách / thêm camera |
| POST | `/api/cameras/test` | Thử kết nối camera |
| POST | `/api/cameras/{cam_id}` | Sửa camera |
| POST | `/api/cameras/{cam_id}/start` | Chạy camera |
| POST | `/api/cameras/{cam_id}/stop` | Dừng camera |
| DELETE | `/api/cameras/{cam_id}` | Xóa camera |
| POST | `/api/cameras/{cam_id}/view` | Đăng ký/hủy đăng ký xem (watch) |
| POST | `/api/upload` | Upload video nguồn |
| POST | `/api/settings` | Lưu cài đặt |
| POST | `/api/telegram/find-chat` | Tìm chat ID Telegram |
| POST | `/api/sound/test` | Thử âm thanh |
| POST | `/api/telegram/test` | Gửi thử Telegram |
| GET | `/api/storage` | Thông tin lưu trữ |
| POST | `/api/storage/clear` | Dọn lưu trữ thủ công |
| POST | `/api/quit` | Thoát ứng dụng |
| GET | `/api/history` | Lịch sử sự kiện (phân trang/lọc) |
| GET | `/api/events.csv` | Xuất CSV |
| GET | `/api/qr` | QR điện thoại |
| WS | `/ws/phone` | WebSocket nhận hình/điều khiển điện thoại |

Tổng: 29 route, khớp sơ bộ với bảng chức năng ở mục 5 của `KE_HOACH_CHUYEN_NATIVE.md`. Mỗi route cần được gắn vào dịch vụ/màn hình cụ thể ở Bước 3, chưa làm ở bước này.

## 4. Kích thước mã nguồn cần tách (tham khảo cho ước lượng công sức)

| File | Số dòng |
|---|---|
| `web.py` | 1275 |
| `core/pipeline.py` | 460 |
| `core/signals.py` | 294 |
| `core/camera.py` | 147 |
| `core/display.py` | 165 |
| `core/fight.py` | 179 |
| `core/focus.py` | 136 |
| `core/rules.py` | 119 |
| `core/sound.py` | 94 |
| `app.py` | 93 |
| `evaluate_clips.py` | 92 |
| `core/tts.py` | 82 |
| `core/window.py` | 68 |
| `core/cleanup.py` | 38 |
| `core/paths.py` | 24 |

`config.yaml` có 8 nhóm khóa cấp cao: `models`, `detection`, `performance`, `rules`, `timing`, `modes`, `fight`, `custom_class_map`, `output`.

## 5. Benchmark hiệu năng trước chuyển đổi

Chưa thực hiện trong phiên này — cần webcam/video thật, GPU/CPU cụ thể và cả hai chế độ (Lớp học/Hành lang) để đo FPS suy luận, FPS hiển thị, độ trễ p50/p95, CPU/RAM. Đây là việc cần môi trường phần cứng thật của bạn, không thể giả lập đáng tin cậy trong phiên này. Đề xuất đo trước khi bắt đầu Bước 2 (khi đã có desktop tối thiểu để so sánh).

## 6. Môi trường phát triển — vấn đề cần bạn lưu ý

- `.venv-build` ở gốc dự án có `pyvenv.cfg` ghi `home = /home/tranvanhuy0642/.pyenv/versions/3.14.7/bin` nhưng được tạo từ đường dẫn cũ `/home/tranvanhuy0642/Projects/My projects/khkt/.venv-build` (trước khi đổi tên thư mục dự án). Hệ quả: script `pip`, `pytest`, v.v. trong `.venv-build/bin/` có shebang trỏ đến đường dẫn không còn tồn tại và báo lỗi khi gọi trực tiếp.
- Cách lách qua trong phiên này: gọi `.venv-build/bin/python3.14 -m <module>` thay vì gọi script trực tiếp. Đây chỉ là giải pháp tạm; nếu tiếp tục dùng venv này, nên tạo lại venv (`python3.14 -m venv .venv-build --clear`) để sửa shebang, nhưng việc này cần xác nhận của bạn vì sẽ ghi đè venv hiện tại.
- Tên repo hiện dùng dấu gạch nối (`khkt-lophocai`), không còn khoảng trắng như thư mục cũ — không phải vấn đề của Bước 0, chỉ là tàn dư cấu hình venv.

## 7. Kết luận Bước 0

Điều kiện hoàn thành theo kế hoạch ("có bảng chức năng và kết quả trước chuyển đổi để đối chiếu") đã đạt ở phần mã nguồn/test/route. Phần benchmark hiệu năng thực tế (camera thật, hai chế độ) cần thực hiện trên máy có phần cứng khi bắt đầu Bước 2, không phải việc có thể hoàn tất từ phiên làm việc không có thiết bị video thật.

Đề xuất bước tiếp theo: Bước 1 — tạo `pyproject.toml`, `src/lophocai/`, tách `Engine`/`Camera` khỏi FastAPI, giữ `web.py` chạy qua lõi mới.
