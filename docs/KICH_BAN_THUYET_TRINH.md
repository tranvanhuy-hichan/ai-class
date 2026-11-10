# Kịch bản thuyết trình: "Lớp học AI" cho các bạn THPT

Thời lượng gợi ý: **30–35 phút** (25 phút nói + 5–10 phút demo/hỏi đáp). Mỗi phần ghi sẵn thời gian, ý chính, lời nói mẫu và gợi ý slide/demo.
Giọng điệu: gần gũi, hỏi–đáp với khán giả, tránh thuật ngữ khi chưa giải thích.

---

## Phần 0. Mở đầu (2 phút)

**Slide:** ảnh lớp học, một bạn gục đầu, một bạn cầm điện thoại dưới ngăn bàn.

**Lời nói mẫu:**
> "Các bạn thử nghĩ: cô giáo đang giảng, lớp 45 bạn. Cô có nhìn được cùng lúc tất cả 45 bạn không? Có bạn đang mệt, có bạn lén xem điện thoại. Hôm nay tụi mình sẽ kể về một hệ thống dùng AI giúp **giáo viên không bỏ sót** các bạn đó. Và quan trọng hơn: tụi mình sẽ mở 'hộp đen' ra xem AI thật sự **nhìn** và **suy nghĩ** thế nào."

**Câu hỏi tương tác:** "Ai đã từng dùng Face ID, lọc ảnh TikTok, hay Google Lens?" (giơ tay) → "Tất cả đều là AI thị giác."

---

## Phần 1. AI là gì? (4 phút)

**Ý chính**
1. **AI (trí tuệ nhân tạo)** = máy tính làm những việc thường cần trí thông minh của con người: nhìn, nghe, hiểu, quyết định.
2. Cách làm truyền thống: lập trình viên **viết luật** ("nếu pixel màu này… thì là mèo"). Với ảnh thật, không thể viết hết luật.
3. Cách làm của **Machine Learning (học máy)**: không viết luật, mà **cho máy xem thật nhiều ví dụ có đáp án**, máy tự tìm ra quy luật.
4. **Deep Learning (học sâu)** là học máy dùng **mạng nơ-ron nhiều tầng**, rất mạnh với ảnh.

**Hình minh họa (vẽ 3 vòng tròn lồng nhau):** AI ⊃ Machine Learning ⊃ Deep Learning.

**Ví dụ dễ hiểu:** dạy em bé nhận ra con chó. Không ai giải thích "chó có 4 chân, tai nhọn…". Ta chỉ **cho xem nhiều con chó** và nói "đây là chó". Máy cũng học như vậy.

**Lời nói mẫu:**
> "AI không 'biết' gì từ đầu. Nó giống một học sinh rất chăm: xem hàng chục nghìn bức ảnh, đoán, bị sửa sai, rồi đoán lại tốt dần lên."

---

## Phần 2. AI học từ bộ dữ liệu như thế nào? (5 phút)

**Ý chính: vòng đời của một mô hình**

```
Thu thập ảnh ─► Gán nhãn ─► Huấn luyện ─► Kiểm tra ─► Đem dùng
 (dataset)     (đáp án)    (training)    (testing)
```

1. **Bộ dữ liệu (dataset):** hàng nghìn ảnh. Mỗi ảnh có **nhãn**, ví dụ "khung quanh cái điện thoại + chữ *phone*".
2. **Huấn luyện:** máy đoán → so với đáp án → sai thì chỉnh lại hàng triệu "núm vặn" (gọi là **tham số/trọng số**) → lặp lại nhiều vòng (mỗi vòng = 1 **epoch**).
3. **Chia dữ liệu:** phần để học (train), phần **giấu đi** để thi thử (test). Giống ôn đề rồi làm đề lạ. Nếu chỉ học thuộc đề cũ thì gọi là **học vẹt (overfitting)**.
4. **Chỉ số đánh giá:** độ chính xác (accuracy), ma trận nhầm lẫn (confusion matrix), đường PR.

**Dữ liệu dự án đã dùng** (nói đúng sự thật, đây là điểm cộng KHKT):

| Bộ dữ liệu | Dùng để |
|---|---|
| COCO (80 loại vật thể, có "cell phone", "person") | Dạy YOLO nhận ra người và điện thoại (mô hình có sẵn, đã huấn luyện) |
| Kaggle *yawn-eye-dataset* (ảnh mắt mở/nhắm) | Tự huấn luyện mô hình mắt mở/nhắm |
| SCB-Dataset, Roboflow *student-behaviour* | Hành vi học sinh: cúi đầu, ngủ, dùng điện thoại |
| Video tự quay trong thư mục `clips/` (có xin phép) | Kiểm thử trên lớp học Việt Nam thật |

**Thí nghiệm hay để kể (trung thực, rất ghi điểm):**
> "Tụi mình tự huấn luyện mô hình mắt mở/nhắm, đạt **100%** trên tập kiểm tra. Nhưng khi thử trên webcam thật thì **kết quả nhảy lung tung**. Vì sao? Ảnh trong bộ dữ liệu chụp cận cảnh, rõ nét; còn mắt cắt từ webcam thì mờ. Bài học: *điểm cao trên đề thi thử chưa chắc giỏi ngoài đời*. Vì vậy tụi mình chọn MediaPipe, ổn định hơn."

**Nhấn mạnh đạo đức dữ liệu:** quay video phải **xin phép nhà trường, phụ huynh, học sinh**; ứng dụng chạy trên một máy, **video không gửi lên Internet**.

---

## Phần 3. YOLO là gì? (6 phút)

**Câu mở:** "You Only Look Once" = *Bạn chỉ nhìn một lần.*

**Ý chính**
1. **Bài toán phát hiện đối tượng (object detection):** không chỉ trả lời "ảnh này có chó" mà phải chỉ ra **ở đâu** (khung chữ nhật) và **là gì**.
2. **Cách cũ:** trượt một cửa sổ nhỏ qua từng vị trí của ảnh, hỏi "ở đây có gì?", hàng nghìn lần → **chậm**.
3. **YOLO:** đưa cả bức ảnh qua mạng nơ-ron **một lần duy nhất**, mạng trả về luôn toàn bộ các khung + tên + độ tin cậy → **rất nhanh**, chạy được cả trên laptop thường.
4. **Mỗi khung kết quả gồm:** vị trí (x, y, rộng, cao), **lớp** (person, cell phone…), **độ tin cậy** (0–1).

**Minh họa nên vẽ:** chia ảnh thành lưới ô vuông; mỗi ô "bỏ phiếu" xem có vật nào có tâm nằm trong ô mình không; sau đó giữ khung tốt nhất (khái niệm **NMS** — lọc bớt khung trùng nhau).

**Dự án dùng 2 mô hình YOLO11 (bản nhỏ "n" = nano, nhẹ nhất):**

| Mô hình | Làm gì | Trong dự án |
|---|---|---|
| `yolo11n.pt` (detect) | Tìm vật thể | Tìm **điện thoại** |
| `yolo11n-pose.pt` (pose) | Tìm người + **17 điểm khung xương** | Tìm **đầu, vai, cổ tay** của từng học sinh |

**Demo 1 (1 phút):** mở một ảnh lớp học, hiện khung xanh quanh người, khung quanh điện thoại, và các chấm khung xương.

**Giải thích khung xương:** 17 điểm gồm mũi, mắt, tai, vai, khuỷu tay, cổ tay, hông, gối, cổ chân. Mỗi điểm có tọa độ (x, y) và **độ tin cậy**, điểm nào bị che thì độ tin cậy thấp.

**Theo dõi (tracking):** thuật toán **ByteTrack** gán cho mỗi bạn một **ID cố định** qua các khung hình, để biết "bạn số 7 đã gục đầu được bao lâu".

---

## Phần 4. Nhận diện hành vi: làm sao biết bạn đang gục / ngủ / dùng điện thoại? (7 phút)

**Nguyên tắc cốt lõi (nói chậm, đây là phần "trí tuệ" của dự án):**
> "YOLO chỉ cho tụi mình **tọa độ**. Biến tọa độ thành **ý nghĩa** ('bạn này đang gục') là phần tụi mình tự thiết kế."

Hệ thống chạy theo 2 tầng: **(1) tín hiệu tức thời trong từng khung hình** → **(2) luật thời gian**.

### 4.1. Gục đầu xuống bàn

- Lấy trung bình độ cao các điểm trên đầu (mũi, mắt, tai) so với độ cao hai vai.
- Công thức (xem `core/signals.py`):

```
tỉ lệ = (độ cao vai − độ cao đầu) / độ rộng vai
```

| Tình huống | Tỉ lệ |
|---|---|
| Ngồi thẳng | khoảng 0.5 – 1.0 |
| Gục xuống bàn | dưới 0.15 (đầu ngang/thấp hơn vai) |
| Thấy vai mà **không thấy điểm nào trên mặt** | coi là úp mặt xuống bàn |

- **Vì sao chia cho độ rộng vai?** Bạn ngồi gần camera thì trông to, bạn ở cuối lớp thì nhỏ. Chia cho độ rộng vai là **chuẩn hóa**, để cùng một ngưỡng dùng đúng cho mọi vị trí.

> Câu hỏi cho khán giả: "Nếu không chia cho độ rộng vai thì chuyện gì xảy ra?" (Bạn ngồi xa bị coi là luôn gục.)

### 4.2. Dùng điện thoại

1. YOLO tìm vật "cell phone" trong ảnh.
2. Với mỗi điện thoại, tính khoảng cách tới **cổ tay** của từng học sinh (từ khung xương).
3. Nếu khoảng cách < 0.8 × độ rộng vai → **bạn đó đang cầm điện thoại** (gán điện thoại cho đúng người).
4. Có điện thoại nằm trên bàn không ai cầm → **không báo**.

### 4.3. Ngủ gật (nhắm mắt)

- **MediaPipe Face Landmarker** đo **468 điểm trên khuôn mặt**, từ đó ra điểm "độ nhắm mắt" (mở ≈ 0.1–0.4, nhắm ≈ 0.6–0.9).
- Điểm > 0.55 → mắt nhắm.
- Chỉ đo khi mặt đủ to (khoảng cách hai mắt ≥ 30 px), nếu không thì máy tự biết mình "không đủ thông tin" và **không đoán bừa**.

### 4.4. Luật thời gian (tránh báo nhầm)

Một khoảnh khắc cúi nhặt bút **không phải** ngủ. Vì vậy hành vi phải **kéo dài đủ lâu**:

| Hành vi | Báo sau |
|---|---|
| Dùng điện thoại | 2 giây |
| Gục đầu | 3 giây |
| Nhắm mắt liên tục | 3 giây |
| Gục đầu liên tục | 10 giây → "ngủ gục" |

Hai cơ chế thông minh:
- **Thời gian ân hạn 0.8 giây:** AI bỏ sót vài khung hình thì **không reset đồng hồ**.
- **Thời gian chờ 15 giây:** đã báo một bạn thì không báo liên tục làm phiền giáo viên.

**Màu khung trên màn hình:** 🟩 bình thường · 🟧 có dấu hiệu nhưng chưa đủ lâu · 🟥 đang cảnh báo (kèm tiếng chuông và giọng đọc "Có học sinh ngủ gật").

### 4.5. Chỉ số tập trung của lớp (0–100)

Mỗi bạn: bình thường **100**, có dấu hiệu **50**, đang cảnh báo **0**; điểm lớp = trung bình, làm mượt ~5 giây.
**Nói thẳng:** đây là chỉ số **tham khảo** do nhóm tự đặt, chưa được kiểm chứng với đánh giá giáo viên → hướng phát triển tiếp theo.

**Demo 2 (3 phút, phần chính):** bật webcam hoặc video mẫu → một bạn gục đầu, một bạn cầm điện thoại → khung chuyển xanh → cam → đỏ, nghe tiếng báo.

---

## Phần 5. Kiến trúc hệ thống (4 phút)

**Slide sơ đồ (vẽ từ trái sang phải):**

```
Camera (webcam / camera trường RTSP / điện thoại / video)
        │
        ▼
 ┌─────────────────────── Máy chạy ứng dụng (Python) ───────────────────────┐
 │  Khung hình ─► YOLO11-pose ─► người + ID + khung xương ─┐                 │
 │            ├─► YOLO11 ───────► điện thoại ──────────────┤                 │
 │            └─► MediaPipe ────► độ nhắm mắt ─────────────┤─► Luật thời gian│
 │                                                          │      │          │
 └──────────────────────────────────────────────────────────┘      ▼          │
                                          Cảnh báo: khung đỏ + chuông + giọng đọc
                                          + nhật ký CSV + ảnh chụp + Telegram
                                                   │
                                                   ▼
                                  Trang web giám sát (localhost:8000)
```

**Ý chính cần nói**
1. **Mô-đun hóa:** mỗi khâu một file (`camera.py`, `signals.py`, `rules.py`, `pipeline.py`...) → dễ sửa, dễ thay mô hình.
2. **Giao diện web:** giáo viên mở trình duyệt xem video có khung, biểu đồ tập trung, nhật ký cảnh báo, chỉnh độ nhạy ngay.
3. **Đa nguồn camera:** webcam, camera RTSP của trường, **điện thoại làm camera** (quét QR, không cần cài app), hoặc video có sẵn.
4. **Cấu hình không cần sửa code:** mọi ngưỡng nằm ở `config.yaml`.
5. **Riêng tư theo thiết kế:** chạy **trên một máy**, chỉ mở ở `localhost`, video **không gửi đi đâu**; điện thoại làm camera chỉ gửi được hình, phải có mã bí mật đổi mỗi lần mở.
6. **Chạy được máy yếu:** hành vi kéo dài vài giây nên 2–3 FPS là đủ.

**Bảng số liệu thực đo (nên chiếu):**

| `imgsz` | Người nhỏ nhất nhận ra | GPU RTX 3050 | CPU i7-11800H |
|---|---|---|---|
| 640 | cao ~190 px (1–3 người gần webcam) | ~55 FPS | ~30 FPS |
| 1280 | cao ~125 px (cả lớp) | ~20 FPS | ~7 FPS |

**Hạn chế nói thẳng:** vật nhỏ như điện thoại, mắt ở bàn cuối khó nhận; gục đầu thì nhận được ở mọi vị trí nhờ khung xương.

---

## Phần 6. Đóng gói thành file .exe (3 phút)

**Vấn đề:** "Code chạy được trên máy em, nhưng thầy cô đâu biết cài Python, cài thư viện?"

**Giải pháp 3 bước:**

1. **PyInstaller** (`packaging/lophocai.spec`): gói Python + thư viện + mô hình thành một thư mục chạy độc lập → người dùng **không cần cài Python**.
2. **Inno Setup** (`packaging/windows/lophocai.iss`): tạo **bộ cài** `LopHocAI-Setup-x.y.z.exe` → bấm Next → Install, có biểu tượng ngoài Desktop.
3. **GitHub Actions** (`.github/workflows/build.yml`): bấm một nút (hoặc đẩy tag `v1.0.0`), máy chủ GitHub **tự build** bản Windows (.exe) và Ubuntu (.deb) rồi đính vào mục **Releases**.

```
Mã nguồn ─► PyInstaller ─► thư mục chạy độc lập ─► Inno Setup ─► Setup.exe
                                  └─ GitHub Actions tự động hóa cả chuỗi này
```

**Bài học kỹ thuật kể vui:** PyTorch rất nặng, nên bản build dùng **PyTorch CPU** để file nhỏ hơn và máy không có card đồ họa vẫn chạy. Dữ liệu người dùng lưu ở `%LOCALAPPDATA%\LopHocAI`, không ghi vào thư mục cài đặt.

---

## Phần 7. Đạo đức, hạn chế và hướng phát triển (2 phút)

**Đạo đức (khán giả THPT rất quan tâm):**
- Hệ thống **hỗ trợ giáo viên**, không để chấm điểm hay kỷ luật học sinh.
- Không nhận diện khuôn mặt/tên, chỉ gán **ID tạm thời**; video xử lý tại chỗ, không lên mạng.
- Luôn cần sự đồng ý của nhà trường, phụ huynh, học sinh.

**Hạn chế:** có thể báo nhầm (cúi đọc sách giống gục), ánh sáng yếu, bàn cuối khó thấy.
**Hướng phát triển:** huấn luyện thêm với video lớp học Việt Nam, kiểm chứng chỉ số tập trung với đánh giá của giáo viên, dùng 2 camera cho lớp rộng.

---

## Phần 8. Kết và hỏi đáp (2 phút)

**Lời kết mẫu:**
> "AI không thần kỳ. Nó là **dữ liệu + mô hình + những quy tắc do con người thiết kế**. Bạn nào ở đây cũng có thể bắt đầu: chỉ cần một webcam, một chút Python, và một câu hỏi thực tế muốn giải quyết. Cảm ơn các bạn!"

### Câu hỏi hay gặp (chuẩn bị sẵn)

| Câu hỏi | Gợi ý trả lời |
|---|---|
| AI có nhận ra mặt/tên từng bạn không? | Không. Chỉ gán ID tạm thời để đếm thời gian. |
| Báo nhầm thì sao? | Có luật thời gian và ngưỡng chỉnh được; giáo viên là người quyết định cuối. |
| Sao không tự huấn luyện hết, mà dùng YOLO có sẵn? | Huấn luyện từ đầu cần hàng trăm nghìn ảnh và GPU mạnh. Ta dùng **học chuyển giao (transfer learning)**: tận dụng mô hình đã học sẵn, chỉ tinh chỉnh phần cần thiết. |
| Độ chính xác bao nhiêu? | Nêu số liệu thật từ `evaluate_clips.py` trên video thử nghiệm; nói rõ điều kiện (góc camera, khoảng cách). |
| Có cần Internet không? | Không, chạy hoàn toàn cục bộ (Telegram là tùy chọn). |
| Em muốn học AI thì bắt đầu từ đâu? | Python → thư viện `ultralytics` → thử huấn luyện bộ dữ liệu nhỏ trên Google Colab (miễn phí). |

---

## Phụ lục: Checklist chuẩn bị

- [ ] Laptop đã cài bản `.exe`, thử chạy trước 1 lần (cửa sổ dòng lệnh đừng tắt).
- [ ] 2 video demo ngắn (gục đầu, dùng điện thoại) **phòng khi webcam/ánh sáng trục trặc**.
- [ ] Ảnh minh họa YOLO có khung và khung xương.
- [ ] Biểu đồ `runs/.../confusion_matrix.png`, `results.png` của mô hình mắt.
- [ ] Slide bảng số liệu FPS và so sánh MediaPipe vs mô hình tự huấn luyện.
- [ ] Giấy đồng ý quay video của nhà trường/phụ huynh (nếu dùng video lớp thật).
- [ ] Loa để demo tiếng chuông và giọng đọc cảnh báo.

## Gợi ý phân bổ thời gian

| Phần | Phút |
|---|---|
| 0. Mở đầu | 2 |
| 1. AI là gì | 4 |
| 2. Học từ dữ liệu | 5 |
| 3. YOLO | 6 |
| 4. Nhận diện hành vi + demo | 7 |
| 5. Kiến trúc | 4 |
| 6. Build .exe | 3 |
| 7–8. Đạo đức, kết, hỏi đáp | 4+ |
