# Phương án chuyển Lớp học AI sang desktop Qt

Ngày lập: 10/11/2026. Đây là phương án triển khai; chưa di chuyển mã hoặc thay đổi hành vi ứng dụng.

## 1. Mục tiêu và phạm vi

- Có ứng dụng desktop dùng PySide6/Qt Widgets cho Windows và Linux, không cần trình duyệt để giám sát.
- Giữ các chức năng đang có trong mã nguồn, cấu hình và dữ liệu người dùng.
- Tách nghiệp vụ khỏi HTTP và giao diện để desktop, web dự phòng và CLI dùng cùng lõi.
- Giảm chi phí hiển thị video; chỉ kết luận tăng hiệu năng sau khi đo trên cùng phần cứng và video.
- Chưa đổi mô hình, ngưỡng, thuật toán theo dõi hoặc công thức tập trung trong đợt chuyển giao diện.

Native ở đây là giao diện desktop Qt và xử lý trực tiếp trong ứng dụng; lõi AI vẫn là Python với PyTorch/OpenCV. Không dùng Qt WebEngine để bọc lại trang web.

## 2. Hiện trạng đã rà soát

- `web.py` chứa `Camera`, `Engine`, điều phối AI, cấu hình, lịch sử, Telegram, HTTP, HTTPS điện thoại và khởi động ứng dụng.
- `core/pipeline.py`, `rules.py`, `signals.py`, `fight.py` chứa phần lớn thuật toán có thể tái sử dụng.
- `core/display.py` đang gộp vẽ ảnh, ghi sự kiện và đo FPS; cần tách trách nhiệm.
- `Camera._show()` nén JPEG. Desktop có thể nhận khung hình trực tiếp, web vẫn cần bộ chuyển đổi JPEG riêng.
- Việc hiển thị đang phụ thuộc `watch_ts`/`watched()`. Desktop phải đăng ký camera đang xem để giữ cơ chế tiết kiệm tài nguyên hiện có.
- AI hiện đã chạy ở luồng camera riêng; cần giữ điều phối `Gate`, giới hạn camera và các tối ưu xử lý thưa, lớp trống, tăng tần suất khi nghi xô đẩy.
- `core/paths.py` phân biệt tài nguyên đi kèm và dữ liệu ghi được. Khi đổi cấu trúc phải cập nhật cả cấu hình, đường dẫn tài nguyên và PyInstaller.
- Quy trình GitHub Actions hiện build Windows; Linux được build qua script tại máy. README chưa phản ánh đầy đủ hiện trạng này.
- Tại thời điểm rà soát, Git ghi nhận `weights/behavior_lop.pt` đang bị xóa trong working tree trong khi cấu hình hai nơi vẫn tham chiếu đến nó. Cần xác định mô hình hợp lệ trước khi nghiệm thu nhận diện lớp học; không tự thay bằng mô hình khác.
- Working tree có các thay đổi tài liệu của người dùng. Việc triển khai phải giữ nguyên các thay đổi đó.

## 3. Kiến trúc đích

```text
Qt desktop ──────────────┐
Web dự phòng / CLI ──────┼──> Application services ──> Detection / Camera workers
                        │              │
                        │              ├──> Settings / CSV / Snapshots / Focus
                        │              └──> Sound / Telegram
Điện thoại HTTPS + WS ───┴──> Phone input adapter ──> PushSource
```

- `application` cung cấp các thao tác camera, chọn chế độ, cài đặt, lịch sử, thống kê và vòng đời ứng dụng. Qt gọi trực tiếp, HTTP chỉ chuyển yêu cầu sang cùng dịch vụ.
- `detection` không import Qt hoặc FastAPI. Kết quả được mô tả bằng kiểu dữ liệu rõ ràng: trạng thái camera, học sinh, cảnh báo, thống kê, khung hình và dấu thời gian.
- `runtime` giữ worker camera và điều phối AI độc lập với Qt. Giai đoạn đầu giữ luồng hiện có để hạn chế thay đổi; chỉ xét tiến trình riêng khi đo cho thấy cần thiết.
- `desktop` chỉ hiển thị, nhận thao tác và chuyển thông báo từ worker sang Qt signals; mọi cập nhật widget diễn ra trên luồng giao diện.
- `integrations/phone` phục vụ trang điện thoại, QR, chứng chỉ và WebSocket; giữ phản hồi thông báo về điện thoại.
- HTTP quản trị/MJPEG chỉ dùng cho web dự phòng. Desktop không cần gọi API localhost để hoạt động.

### Hợp đồng truyền khung hình

- Mỗi camera có bộ đệm khung hình mới nhất với số thứ tự và timestamp. Ghi đè khung cũ để không tích hàng đợi khi giao diện chậm.
- Qt lấy khung mới theo nhịp hiển thị có giới hạn; không phát một queued signal mang ảnh cho mọi khung camera.
- Quy định rõ quyền sở hữu bộ nhớ: ảnh công bố không bị worker sửa tiếp; `QImage` phải giữ bộ nhớ hợp lệ hoặc sao chép trước khi bộ đệm NumPy được tái sử dụng.
- Phân biệt nhịp lấy hình, nhịp suy luận và nhịp hiển thị. Giữ logic bỏ overlay quá cũ, thời gian video và reset tracker khi đổi hình/chế độ.
- Chỉ vẽ/nén cho camera có người xem hoặc cần ảnh cảnh báo. JPEG nằm ở adapter web, không nằm ở lõi bắt buộc.
- Theo dõi đăng ký xem theo từng consumer; đóng màn hình hoặc đổi camera phải hủy đăng ký.

## 4. Cấu trúc thư mục đề xuất

```text
khkt-lophocai/
├── pyproject.toml                 # package, entry points, nhóm phụ thuộc
├── README.md
├── src/lophocai/
│   ├── __init__.py
│   ├── __main__.py                # python -m lophocai -> desktop
│   ├── bootstrap.py               # khởi tạo, logging, đóng ứng dụng
│   ├── application/
│   │   ├── engine.py
│   │   ├── cameras.py
│   │   ├── settings.py
│   │   ├── history.py
│   │   └── statistics.py
│   ├── domain/
│   │   ├── models.py              # kiểu dữ liệu dùng chung
│   │   └── behaviors.py
│   ├── detection/
│   │   ├── pipeline.py
│   │   ├── signals.py
│   │   ├── rules.py
│   │   ├── fight.py
│   │   └── tracking.py
│   ├── runtime/
│   │   ├── camera_worker.py
│   │   ├── scheduler.py
│   │   ├── frame_buffer.py
│   │   └── lifecycle.py
│   ├── video/
│   │   ├── sources.py
│   │   ├── transforms.py
│   │   └── overlay.py
│   ├── storage/
│   │   ├── paths.py
│   │   ├── settings_repository.py
│   │   ├── events.py
│   │   ├── focus.py
│   │   └── cleanup.py
│   ├── integrations/
│   │   ├── audio.py
│   │   ├── telegram.py
│   │   └── phone/
│   │       ├── server.py
│   │       ├── certificates.py
│   │       └── security.py
│   ├── desktop/
│   │   ├── app.py
│   │   ├── main_window.py
│   │   ├── bridge.py
│   │   ├── pages/                # chọn chế độ, giám sát, lịch sử, thống kê, cài đặt
│   │   ├── dialogs/              # camera, điện thoại/QR, chỉnh hình
│   │   └── widgets/              # video, thẻ camera, biểu đồ
│   ├── web/
│   │   ├── app.py
│   │   └── routes/
│   └── cli/
│       ├── preview.py
│       └── evaluate.py
├── resources/
│   ├── defaults/config.yaml
│   ├── sounds/
│   ├── icons/
│   └── web/                     # phone.html và giao diện web dự phòng
├── weights/                     # mô hình; manifest nêu file, phiên bản, checksum
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/                # dữ liệu nhỏ, giả lập camera/kết quả AI
├── tools/
│   ├── datasets/
│   ├── training/
│   ├── evaluation/
│   └── assets/                  # tạo icon, giọng đọc
├── packaging/
│   ├── lophocai.spec
│   ├── linux/
│   └── windows/
├── docs/
├── experiments/                 # cấu hình/kết quả nghiên cứu cần giữ
├── archive/                     # bản nhiều lớp chưa hoàn thiện
└── .github/workflows/
```

Không tạo toàn bộ các module rỗng trước. Tách file theo từng bước khi chuyển chức năng thực tế; tránh thêm tầng chỉ chuyển tiếp hàm.

`appdata/`, `.venv*`, `build/`, `dist/`, dữ liệu huấn luyện và video lớn là dữ liệu cục bộ/sản phẩm sinh ra, không phải mã nguồn. Không tự xóa hoặc di chuyển dữ liệu người dùng để làm sạch cây thư mục. `runs/`, `data/`, `clips/` được kiểm kê trước; chỉ chuyển tài liệu/kết quả cần lưu vào `experiments/`, còn đường dẫn dữ liệu lớn được cấu hình rõ ràng.

## 5. Đối chiếu chức năng bắt buộc giữ

| Nhóm | Hành vi phải giữ trên desktop | Cách nghiệm thu |
|---|---|---|
| Chế độ | Chọn Lớp học/Hành lang; đổi chế độ dừng camera và nạp đúng pipeline | Thử cả hai chế độ, tự chạy camera sau chọn |
| Nhận diện | Điện thoại, gục đầu, ngủ/nhắm mắt, đánh nhau, hút thuốc theo cấu hình hiện có | So kết quả lõi trước/sau với cùng tín hiệu và clip |
| Theo dõi | ID học sinh, grace, cooldown, chống trùng người, kiểm tra chéo tư thế | Chạy lại kiểm thử và dữ liệu đặc trưng |
| Nguồn hình | Webcam USB, RTSP/IP/HTTP, điện thoại, file video lặp lại | Một kịch bản thật cho từng nguồn |
| Camera | Thêm/sửa/xóa, thử kết nối, bật/tắt, tự chạy, nhiều camera, chặn nguồn trùng | Kiểm tra giới hạn và các lỗi nguồn |
| Giám sát | Chọn camera, ảnh xem trước, khung màu, nhãn, skeleton, trạng thái/FPS/số người | Kiểm tra camera chính và camera nền |
| Chỉnh hình | Lật ngang/dọc, xoay, độ sáng, zoom; nhớ riêng mỗi camera | Đóng/mở app, đổi nguồn và kiểm tra reset tracker |
| Tối ưu sẵn có | Giới hạn FPS/đồng thời, GPU/CPU, mô hình CPU, lớp trống, tăng nhịp nghi xô đẩy | So lịch xử lý và giới hạn tài nguyên |
| Tập trung | Hiện tại, trung bình, phút thấp nhất, biểu đồ theo khoảng thời gian/camera/tổng hợp | So với CSV và công thức cũ |
| Cảnh báo | Chuông/giọng tiếng Việt, bật/tắt/thử âm thanh, thông báo đang hoạt động | Không phát trùng giữa Qt và dịch vụ âm thanh |
| Telegram | Lưu token/chat ID, tìm chat, gửi thử, gửi cảnh báo kèm ảnh | Giả lập phản hồi và thử thật khi có cấu hình |
| Lịch sử | Lọc phiên/hành vi/camera, phân trang, xem ảnh và xuất CSV | Đọc cả dữ liệu từ bản cũ |
| Lưu trữ | Bật/tắt ảnh, giới hạn ngày/dung lượng, dọn thủ công/tự động, bảo vệ video đang dùng | Thử trên thư mục tạm có file được bảo vệ |
| Điện thoại | QR mới mỗi phiên, HTTPS, nhận hình qua WS, phản hồi thông báo, từ chối mã cũ | Thử bằng điện thoại trong LAN và mã sai |
| Cài đặt | Độ nhạy, ngưỡng thời gian, imgsz, nâng cao và thông tin phần cứng | Áp dụng ngay theo hành vi cũ, giữ sau khởi động |
| Vòng đời | Một phiên desktop, mở lại đưa cửa sổ lên, đóng app giải phóng camera/file/server | Chạy/đóng/mở lặp lại trên cả hai OS |
| Công cụ | Preview OpenCV, đánh giá clip, tạo giọng, huấn luyện và chuẩn bị dataset | Entry point và hướng dẫn vẫn sử dụng được |

Mỗi route trong `create_app()` và mỗi thao tác trong `web/index.html`, `web/phone.html` phải được gắn với dịch vụ hoặc màn hình tương ứng trước khi ngừng dùng web làm mặc định. Bảng này là mốc ban đầu, cần hoàn tất đối chiếu từng thao tác khi triển khai.

## 6. Ánh xạ mã cũ sang mã mới

| Hiện tại | Đích |
|---|---|
| `web.py: Engine` | `application/engine.py` và các dịch vụ camera/cài đặt/thống kê |
| `web.py: Camera`, `Gate` | `runtime/camera_worker.py`, `scheduler.py` |
| Điều chỉnh hình trong `web.py` | `video/transforms.py` |
| Route trong `web.py` | `web/routes/`, gọi dịch vụ chung |
| QR/HTTPS/WS/chứng chỉ | `integrations/phone/` |
| `core/pipeline.py` | `detection/pipeline.py`; tracker sang `tracking.py` khi cần |
| `core/rules.py`, `signals.py`, `fight.py` | `detection/` |
| `core/camera.py` | `video/sources.py` |
| `core/display.py` | `video/overlay.py`, `storage/events.py`; FPS sang runtime |
| `core/focus.py`, `cleanup.py`, `paths.py` | `storage/` |
| `core/sound.py`, `tts.py` | `integrations/audio.py`, `tools/assets/` |
| `core/window.py` | Chỉ giữ cho web dự phòng, desktop dùng vòng đời Qt |
| `app.py`, `evaluate_clips.py` | `cli/` với wrapper tương thích lúc chuyển tiếp |
| `scripts/` | `tools/` theo mục đích; cập nhật lệnh trong tài liệu |

## 7. Dữ liệu và tương thích

1. Giai đoạn chuyển tiếp giữ nguyên nơi lưu: chạy nguồn dùng `appdata/`; bản cài dùng `%LOCALAPPDATA%/LopHocAI` hoặc `~/.local/share/LopHocAI`.
2. Giữ `settings.json`, ID camera, nguồn, view, CSV sự kiện, CSV focus, ảnh, upload và các đường dẫn được tham chiếu. Chưa chuyển sang SQLite trong cùng đợt.
3. Tài nguyên chỉ đọc được resolve độc lập với working directory; xử lý cả chạy package và PyInstaller. Nguồn video/file người dùng vẫn là đường dẫn dữ liệu, không resolve thành tài nguyên.
4. Nếu cần đổi schema: có version, sao lưu trước khi chuyển, ghi qua file tạm rồi replace, kiểm thử chuyển lại nhiều lần không làm hỏng dữ liệu. Không ghi đè bản cũ bằng cấu hình mặc định.
5. Phân biệt snapshot path/ID trong lõi và URL trong web adapter; Qt mở ảnh qua repository thay vì dùng `/snapshots/...` như đường dẫn file.
6. Giữ app cũ chạy được trên bản sao dữ liệu để quay lui; không cho hai app cùng ghi một thư mục dữ liệu.

## 8. Lộ trình và điều kiện chuyển bước

### Bước 0 — Chốt đường cơ sở

- Kiểm kê thao tác UI/route, cấu hình, model và dữ liệu; xử lý rõ tình trạng thiếu `behavior_lop.pt`.
- Chạy bốn bộ kiểm thử hiện có: rules, fight, focus, classroom_crowd; ghi lại lỗi sẵn có nếu có.
- Ghi kết quả và số liệu hiệu năng từ cùng một tập video có đủ hai chế độ, trên cấu hình CPU/GPU có sẵn.
- Hoàn thành khi có bảng chức năng và kết quả trước chuyển đổi để đối chiếu.

### Bước 1 — Tách lõi và tổ chức package

- Tạo `pyproject.toml` và `src/lophocai`, tách `Engine`/`Camera` và dịch vụ khỏi FastAPI; giữ wrapper `web.py`/`app.py` tạm thời.
- Di chuyển thuật toán theo từng nhóm và sửa import, resource resolver, test, script và spec đi kèm.
- Không đồng thời sửa thuật toán hoặc ngưỡng. Web cũ phải hoạt động qua lõi mới trước khi viết đầy đủ Qt.
- Hoàn thành khi kiểm thử cũ và kiểm thử dịch vụ/HTTP tương ứng chạy qua, dữ liệu cũ vẫn đọc được.

### Bước 2 — Desktop tối thiểu chạy xuyên suốt

- Khởi động Qt, chọn chế độ, thêm nguồn, chạy/dừng, xem video và nhận cảnh báo qua lõi chung.
- Thêm frame buffer, đăng ký người xem, bridge trạng thái và cơ chế đóng có kiểm soát.
- Hoàn thành khi không tích khung cũ, không treo UI lúc nạp AI và không giữ camera sau đóng app.

### Bước 3 — Hoàn tất chức năng tương đương

- Làm nhiều camera, chỉnh hình, focus/chart, lịch sử/ảnh/CSV, cài đặt, âm thanh, Telegram, lưu trữ và điện thoại.
- Tách phone server khỏi web quản trị; chỉ mở ra LAN các endpoint cần cho điện thoại, giữ kiểm tra mã phiên với cả HTTP và WS.
- Không đưa vào luồng người dùng các chức năng chưa hoàn thiện ở bản nhiều lớp trong kho lưu trữ.
- Hoàn thành khi từng hàng trong bảng chức năng có kết quả nghiệm thu.

### Bước 4 — Bộ cài và kiểm thử hai hệ điều hành

- PyInstaller dạng thư mục, bộ cài Inno Setup cho Windows và `.deb` cho Ubuntu/Debian.
- Build riêng trên mỗi OS; kiểm tra plugin Qt platform, thư viện OpenCV, MediaPipe, Torch, âm thanh và font tiếng Việt.
- Chốt phiên bản thư viện đã kiểm chứng; tách dependency runtime/desktop/phone/dev/training. Khai báo trực tiếp các import như `requests`, `numpy` thay vì dựa vào dependency bắc cầu.
- Bản CPU là cấu hình phát hành ban đầu theo bộ cài hiện tại; bản GPU chỉ công bố khi kiểm chứng đủ dependency và driver.
- Thử bộ cài trên máy sạch, tài khoản không quyền quản trị khi chạy, đường dẫn có khoảng trắng/chữ Việt, khởi động không mạng với mô hình đã đóng gói.
- Kiểm tra nghĩa vụ phân phối giấy phép Qt/PySide6 và thư viện/mô hình theo cấu hình đóng gói thực tế.

### Bước 5 — Đo và chuyển mặc định

- So sánh desktop/web sau khi đạt đủ chức năng; sửa các bottleneck có số đo chứng minh.
- Chỉ đặt desktop làm mặc định sau nghiệm thu hai OS và dữ liệu cũ; giữ web dự phòng trong giai đoạn chuyển tiếp.
- ONNX/OpenVINO/TensorRT là đợt tối ưu riêng sau đó, có kiểm thử độ chính xác và tương thích model.

Mỗi bước là một nhóm commit có thể review/quay lui. Không di chuyển toàn bộ thư mục và viết lại giao diện trong một lần thay đổi.

## 9. Kiểm thử và đo hiệu năng

- Giữ kiểm thử thuật toán hiện có; thêm kiểm thử có ý nghĩa cho vòng đời camera, đổi chế độ, cấu hình cũ, đăng ký khung hình, stop/cleanup và bảo vệ file đang dùng.
- Dùng nguồn giả lập và kết quả AI giả lập để kiểm thử dịch vụ mà không cần webcam/GPU. Kiểm thử thật riêng cho camera, model, âm thanh và điện thoại.
- Đối chiếu lõi trên cùng chuỗi tín hiệu/thời gian; với suy luận thực tế dùng cùng clip, model, threshold, device và nêu sai số do backend nếu có.
- Đo CPU, RAM, VRAM nếu có, thời gian khởi động/nạp model, FPS suy luận, FPS hiển thị và độ trễ từ nhận khung đến hiển thị (p50/p95). Không dùng FPS hiển thị để thay cho FPS suy luận.
- So cùng số camera, độ phân giải, chế độ, view và giới hạn FPS; có warm-up và đo lặp. Kiểm tra khi thu nhỏ UI hoặc không xem camera.
- Mục tiêu nghiệm thu: đủ chức năng, không tăng hàng đợi theo thời gian, không rò camera/worker khi chạy lại, không mất dữ liệu, lõi giữ kết quả. Mức giảm CPU/RAM/độ trễ chỉ chốt sau số đo đường cơ sở.

## 10. Nguồn tham khảo

- Qt for Python deployment: https://doc.qt.io/qtforpython-6/deployment/index.html
- Qt threading và QObject: https://doc.qt.io/qt-6/threads-qobject.html
- QImage và vòng đời bộ nhớ: https://doc.qt.io/qt-6/qimage.html
- PyInstaller và build theo hệ điều hành: https://pyinstaller.org/en/stable/operating-mode.html

Các phiên bản cụ thể, nền tảng hỗ trợ và lựa chọn đóng gói cần được kiểm tra lại lúc triển khai.
