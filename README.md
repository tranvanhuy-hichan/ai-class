# Hệ thống AI cảnh báo hành vi bất thường của học sinh trong lớp học

Camera quay lớp học → AI nhận diện từng học sinh → cảnh báo (khung đỏ + tiếng bíp + ghi nhật ký)
khi phát hiện:

| Hành vi | Cách nhận diện | Cảnh báo sau |
|---|---|---|
| Dùng điện thoại | YOLO tìm "cell phone" nằm gần cổ tay học sinh | 2 giây |
| Gục đầu xuống bàn | Khung xương: đầu thấp ngang/thấp hơn vai, hoặc thấy vai mà không thấy mặt | 3 giây |
| Ngủ gục / ngủ gật | Gục đầu liên tục ≥ 10 giây, **hoặc** mắt nhắm ≥ 3 giây (MediaPipe đo độ nhắm mắt) | 10 s / 3 s |

Mọi ngưỡng nằm trong [config.yaml](config.yaml).

## 0. Cài bằng bộ cài (không cần cài Python)

Tải bộ cài ở mục [Releases](https://github.com/tranvanhuy-hichan/ai-class/releases):

| Hệ điều hành | File | Cách cài |
|---|---|---|
| **Windows 10/11** | `LopHocAI-Setup-x.y.z.exe` | Bấm đúp, chọn Next → Install. Mở bằng biểu tượng **Lớp học AI** ngoài Desktop |
| **Ubuntu / Debian** | `lophocai_x.y.z_amd64.deb` | `sudo apt install ./lophocai_x.y.z_amd64.deb`, rồi mở **Lớp học AI** trong menu ứng dụng hoặc gõ `lophocai` |

Mở app sẽ hiện một cửa sổ dòng lệnh (**đừng tắt** khi đang dùng) và trình duyệt tự mở trang giám sát.
Dữ liệu lưu ở `%LOCALAPPDATA%\LopHocAI` (Windows) hoặc `~/.local/share/LopHocAI` (Ubuntu).

**Tự build bộ cài:**
- Ubuntu: `./packaging/build_linux.sh`, cần môi trường `.venv-build` có PyTorch bản CPU (xem lệnh trong
  [.github/workflows/build.yml](.github/workflows/build.yml)). Cài thử không cần sudo: `./packaging/install_user.sh`.
- Windows và Ubuntu tự động trên GitHub: tab **Actions → Build bộ cài → Run workflow**. Hoặc tạo tag
  `git tag v1.0.0 && git push origin v1.0.0` thì bộ cài được gắn vào mục Releases.

## 1. Chạy từ mã nguồn (bấm một lần)

Cần cài [Python](https://www.python.org/downloads/) 3.10 trở lên. Trên Windows, khi cài nhớ tick **"Add Python to PATH"**.

- **Windows**: bấm đúp `start.bat`
- **Linux / macOS**: `./start.sh`

Lần đầu chạy, máy tự cài thư viện (mất 5–15 phút) rồi tự mở trình duyệt ở `http://localhost:8000`.
Từ lần sau chỉ mất vài giây. Khi Windows hỏi tường lửa, chọn **Allow** để điện thoại kết nối được.

Ứng dụng chạy hoàn toàn trên **một máy**:
- **Chỉ người ngồi ở máy đó xem được.** Trang web chỉ mở trên `localhost`, máy khác trong mạng không vào được.
  Video không gửi đi đâu.
- **Nguồn camera**: webcam của máy, camera của trường (RTSP), điện thoại làm camera, hoặc video có sẵn.
- Điện thoại làm camera kết nối qua Wi-Fi (cổng HTTPS 8443) nhưng **chỉ gửi được hình**, phải quét mã QR
  có mã bí mật, và mã này đổi mỗi lần mở app.
- Dữ liệu (nhật ký, ảnh cảnh báo, cài đặt) lưu ở thư mục `appdata/` khi chạy từ code, hoặc
  `%LOCALAPPDATA%\LopHocAI` khi cài bằng bộ cài Windows.

### Dùng trên trang web

| Muốn | Làm |
|---|---|
| Dùng webcam máy tính | **⚙ Cài đặt → Webcam 0** |
| Dùng điện thoại làm camera (không cần cài app) | Bấm **📱 Camera điện thoại**, dùng điện thoại cùng Wi-Fi quét mã, bấm **Bắt đầu**. Trình duyệt báo "không an toàn" thì chọn *Nâng cao → Tiếp tục* |
| Dùng camera của trường (Hikvision, Dahua, Imou...) | **⚙ Cài đặt**, dán link `rtsp://...`, bấm **Kết nối** (trang có sẵn địa chỉ mẫu). Máy phải cùng mạng với camera |
| Demo bằng video có sẵn | **⚙ Cài đặt → Video có sẵn → Tải lên & chạy** (video tự phát lặp lại) |
| Nhận cảnh báo qua Telegram | **⚙ Cài đặt → Thông báo Telegram**, làm theo 3 bước trên trang |
| Xem lớp đang tập trung đến đâu | Thẻ **Mức độ tập trung** cạnh video: số 0–100 theo thời gian thực, trung bình, phút thấp nhất và biểu đồ theo từng phút (30 phút đến cả ngày). Điểm trung bình từng phút được lưu ở `logs/focus.csv` |
| Hình bị ngược trái-phải, camera đặt nghiêng, phòng tối | Trên video bấm nút **⇄ Lật ngang**, hoặc nút chỉnh hình bên cạnh để **lật dọc, xoay 90°/180°, tăng độ sáng, phóng to giữa khung**. Nhớ riêng cho từng camera, áp dụng ngay |
| Chỉnh độ nhạy | **⚙ Cài đặt → Độ nhạy**, có tác dụng ngay |
| Lấy số liệu cho báo cáo | **Thống kê → Tải nhật ký** (mở bằng Excel) |

Màu khung: 🟩 bình thường · 🟧 có dấu hiệu nhưng chưa đủ lâu · 🟥 đang cảnh báo.

> Bản nền tảng nhiều lớp, có tài khoản giáo viên và lãnh đạo, đang được cất trong
> [_luu_tru/nen_tang_nhieu_lop/](_luu_tru/nen_tang_nhieu_lop/) và chưa hoàn thiện.

### Chỉ số tập trung

Mỗi khung hình, từng học sinh được chấm **100%** khi bình thường, **50%** khi có dấu hiệu nhưng chưa đủ lâu để
cảnh báo (vd mới cúi đầu 1–2 giây), **0%** khi đang bị cảnh báo. Điểm của lớp là trung bình các học sinh trong
khung hình, làm mượt khoảng 5 giây. Từ 80 trở lên là "Tập trung tốt", 55–79 "Trung bình", dưới 55 "Dễ mất tập trung".

> **Đây là chỉ số tham khảo** do nhóm tự đặt công thức, chưa được kiểm chứng với đánh giá của giáo viên. Khi trình bày
> nên nói rõ điều này. Muốn kiểm chứng: nhờ giáo viên chấm mức tập trung của các đoạn video mẫu rồi so với điểm của hệ thống.

### Âm thanh cảnh báo

Khi có cảnh báo, loa phát tiếng chuông "ding-dong" rồi đọc **"Có học sinh dùng điện thoại"**, **"Có học sinh ngủ gật"** hoặc
**"Có học sinh nằm gục xuống bàn"**. Âm thanh phát trên loa máy chạy hệ thống, và cả trên laptop hoặc điện thoại của giáo viên
đang mở trang web.

Giọng đọc là file có sẵn trong `web/sounds/`, tạo bằng giọng Neural **vi-VN-HoaiMyNeural** của Microsoft Edge TTS (miễn phí),
nên khi chạy không cần Internet. Muốn đổi giọng (cần Internet lúc tạo):

```bash
python scripts/make_voices.py --voice vi-VN-NamMinhNeural   # giọng nam
python scripts/make_voices.py --engine gtts                 # giọng Google
python scripts/make_voices.py --rate=-15%                   # đọc chậm hơn
```

Muốn đổi câu đọc thì sửa `PHRASES` trong [scripts/make_voices.py](scripts/make_voices.py) rồi chạy lại lệnh trên.

### Bản không cần web (cửa sổ OpenCV)

```bash
python app.py                        # webcam, nhấn Q để thoát
python app.py --source http://192.168.1.5:8080/video   # app IP Webcam trên điện thoại
python app.py --source video.mp4 --save ket_qua.mp4
```

Mỗi cảnh báo được lưu vào `logs/events.csv` (mở bằng Excel), ảnh chụp lưu trong `logs/snapshots/`.

## 3. Cách hệ thống hoạt động

```
Khung hình ─► YOLO11-pose ─► người + ID theo dõi + 17 điểm khung xương ─┐
          ├─► YOLO11 (COCO) ─► điện thoại ─► gán cho học sinh cầm nó ────┤
          ├─► MediaPipe: độ nhắm mắt (khi mặt đủ to) ────────────────────┤─► Luật thời gian ─► Cảnh báo
          └─► (tuỳ chọn) mô hình hành vi tự huấn luyện ──────────────────┘
```

- **Tín hiệu tức thời** ([core/signals.py](core/signals.py)): tính tỉ lệ
  `(độ cao vai − độ cao đầu) / độ rộng vai`. Ngồi thẳng ≈ 0.5–1.0, gục xuống bàn < 0.15.
  Chia cho độ rộng vai để không phụ thuộc học sinh ngồi gần hay xa camera.
- **Luật thời gian** ([core/rules.py](core/rules.py)): một tín hiệu phải kéo dài đủ lâu mới
  cảnh báo, nhờ đó cúi nhặt bút hay liếc điện thoại 1 giây không bị báo nhầm. Có "thời gian ân
  hạn" 0.8 s để mô hình bỏ sót vài khung hình không làm reset bộ đếm, và "thời gian chờ" 15 s để
  không báo liên tục cùng một học sinh.
- **Theo dõi (tracking)**: ByteTrack gán ID cố định cho từng học sinh qua các khung hình.

### Dùng cho cả lớp học / máy tính yếu

Đo thực tế (ảnh 1080p, YOLO11n):

| Cài đặt `imgsz` | Người nhỏ nhất nhận ra được | GPU RTX 3050 | CPU i7-11800H |
|---|---|---|---|
| 640 | cao ~190 px trở lên (1-3 người gần webcam) | ~55 FPS | ~30 FPS |
| 1280 | cao ~125 px (cả lớp, bàn cuối) | ~20 FPS | ~7 FPS |

- Cả lớp học: đặt `detection.imgsz: 1280`, dùng camera 1080p đặt trên cao phía trước lớp.
  Lớp rộng: dùng 2 camera, mỗi camera quay nửa lớp.
- Hành vi kéo dài vài giây nên chỉ cần 2-3 FPS là đủ. Máy cũ không có GPU vẫn chạy được, hệ
  thống tự điều chỉnh khi máy chậm.
- Điện thoại và mắt là vật nhỏ: ở bàn cuối, hệ thống khó nhận ra điện thoại, còn mắt mở/nhắm
  chỉ nhận được khi học sinh ngồi gần camera. Gục đầu thì nhận được ở mọi vị trí vì dựa vào
  khung xương.

## 4. Dữ liệu

### 4.1. Dữ liệu công khai

| Bộ dữ liệu | Nội dung | Dùng để |
|---|---|---|
| [SCB-Dataset](https://github.com/Whiffe/SCB-dataset) ([bài báo](https://arxiv.org/abs/2310.02522)) | Ảnh lớp học thật, nhãn: giơ tay, đọc, viết, **dùng điện thoại, cúi đầu, nằm bò ra bàn**... | Huấn luyện mô hình hành vi (mục 5.2) |
| [Roboflow: student-behaviour](https://universe.roboflow.com/burak-koyfx/student-behaviour) | 4 lớp: nghe giảng, không nghe giảng, **xem điện thoại, ngủ** (CC BY 4.0) | Huấn luyện mô hình hành vi |
| [Roboflow: studentactivity](https://universe.roboflow.com/studentactivity) | Nhiều bộ hoạt động học sinh trong lớp | Tham khảo / bổ sung |
| [Kaggle: yawn-eye-dataset-new](https://www.kaggle.com/datasets/serenaraju/yawn-eye-dataset-new) | Ảnh mắt **mở/nhắm**, miệng ngáp/không ngáp | Huấn luyện mô hình mắt (mục 5.1) |
| [MRL Eye Dataset](http://mrl.cs.vsb.cz/eyedataset) | ~85.000 ảnh mắt mở/nhắm của 37 người | Bổ sung cho mô hình mắt |

Hãy đọc giấy phép (license) của từng bộ và ghi nguồn trong báo cáo.

### 4.2. Dữ liệu tự thu thập (rất nên làm cho KHKT)

Dữ liệu công khai phần lớn quay ở Trung Quốc, Ấn Độ... nên khác lớp học Việt Nam (đồng phục,
bàn ghế, góc camera). Tự thu thập là điểm cộng lớn:

1. Xin phép nhà trường và **được sự đồng ý của các bạn học sinh** (và phụ huynh) trước khi quay.
2. Đặt điện thoại/webcam ở góc bảng, cao ~2 m, nhìn xuống lớp.
3. Nhờ các bạn "diễn" từng hành vi, quay mỗi video 15–30 giây, xếp vào:
   `clips/phone/`, `clips/head_down/`, `clips/sleeping/`, `clips/normal/`.
4. Muốn huấn luyện mô hình riêng: trích ảnh từ video, gán nhãn bằng
   [Roboflow](https://roboflow.com) hoặc [CVAT](https://www.cvat.ai) (miễn phí), xuất định dạng YOLO.

## 5. Huấn luyện mô hình (nâng cao)

### 5.1. Mô hình mắt mở/nhắm (phát hiện ngủ gật)

```bash
pip install kagglehub
python scripts/download_datasets.py eyes
python scripts/prepare_eye_dataset.py --src data/raw_eyes
python scripts/train_eye_classifier.py --epochs 20
```

Xong sẽ có `weights/eye_cls.pt`. Muốn dùng thì đặt `models.eye_method: classifier` trong config.yaml
(mặc định là `mediapipe`).

**Kết quả thực tế (nên đưa vào báo cáo):** mô hình đạt 100% trên tập kiểm tra của Kaggle, nhưng trên
webcam thật thì dự đoán dao động mạnh (xác suất "nhắm" từ 0.33 đến 0.96 khi đang mở mắt). Lý do là ảnh
Kaggle chụp mắt cận cảnh rõ nét, còn mắt cắt ra từ webcam thì mờ. MediaPipe ổn định hơn nhiều (0.1–0.4
khi mở mắt), nên được chọn làm mặc định. So sánh hai phương pháp này là một thực nghiệm hay. Muốn mô
hình tự huấn luyện tốt hơn thì cần thu thập ảnh mắt từ chính camera của lớp.

### 5.2. Mô hình phát hiện hành vi

```bash
pip install roboflow
python scripts/download_datasets.py roboflow --api-key <KEY_CỦA_BẠN>
python scripts/train_behavior.py --data data/student-behaviour/data.yaml --epochs 50
```

Hoặc dùng SCB-Dataset / dữ liệu tự gán nhãn: trỏ `--data` tới file `data.yaml` tương ứng.
Rồi sửa [config.yaml](config.yaml): `models.custom_behavior: weights/behavior.pt`, và chỉnh
`custom_class_map` cho khớp tên lớp. Không có GPU thì dùng
[Google Colab](https://colab.research.google.com) miễn phí.

Biểu đồ trong `runs/behavior/` (`results.png`, `confusion_matrix.png`, `PR_curve.png`) đưa
thẳng vào báo cáo được.

## 6. Đánh giá độ chính xác

```bash
python evaluate_clips.py --clips clips
```

In bảng tỉ lệ phát hiện đúng cho từng hành vi và số lần báo nhầm trên video bình thường,
chi tiết lưu ở `logs/evaluation.csv`. Nên có ít nhất 10 video cho mỗi nhóm.

Kiểm tra luật (không cần camera): `python tests/test_rules.py`

## 7. Gợi ý cho hồ sơ KHKT

- **Tính mới**: kết hợp khung xương + vật thể + luật thời gian thay vì chỉ phân loại ảnh, nên
  phân biệt được "cúi xuống nhặt bút" với "gục đầu ngủ"; chạy được trên laptop thường.
- **Thực nghiệm**: so sánh độ chính xác khi thay đổi ngưỡng (`head_down_ratio` 0.1 / 0.15 / 0.2),
  thời gian (`head_down` 2 / 3 / 5 s), góc đặt camera, ánh sáng, số học sinh trong khung hình.
- **So sánh**: chỉ dùng luật vs. thêm mô hình tự huấn luyện (mục 5.2).
- **Đạo đức & quyền riêng tư**: hệ thống chỉ hỗ trợ giáo viên, không dùng để chấm điểm hay
  phạt; có thể tắt lưu ảnh (`save_snapshots: false`); xoá dữ liệu sau khi dùng.
- **Hạn chế** (nên trình bày thật): học sinh bị che khuất, ngồi quay lưng, cúi đầu viết bài lâu có
  thể bị nhận là gục đầu; điện thoại giấu dưới gầm bàn khó phát hiện; mắt chỉ nhận được khi ở gần.
- **Hướng phát triển**: gửi cảnh báo về điện thoại giáo viên (Telegram bot), bảng thống kê theo
  tiết học, chạy trên Raspberry Pi / Jetson Nano.

## Cấu trúc thư mục

```
start.bat / start.sh   Bấm một lần để cài và chạy (từ mã nguồn)
packaging/             Đóng gói bộ cài (.deb Ubuntu, .exe Windows)
.github/workflows/     Tự build bộ cài trên GitHub
web.py                 Chương trình chính: AI + giao diện web (chỉ mở trên máy này)
web/                   Giao diện (index.html: màn hình chính, phone.html: điện thoại làm camera)
core/paths.py          Nơi lưu dữ liệu (chạy code / app đã cài)
app.py                 Bản cửa sổ OpenCV, không cần web
core/camera.py         Đọc webcam / camera IP / điện thoại / video
evaluate_clips.py      Đánh giá trên video mẫu
config.yaml            Toàn bộ ngưỡng / cấu hình
core/pipeline.py       Ghép các mô hình AI
core/signals.py        Tính tín hiệu từ khung xương
core/rules.py          Luật thời gian -> hành vi
core/display.py        Vẽ, âm thanh, nhật ký
scripts/               Tải dữ liệu, chuẩn bị dữ liệu, huấn luyện
tests/                 Kiểm thử luật
```
