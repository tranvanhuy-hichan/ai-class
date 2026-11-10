# Tài liệu dữ liệu và kế hoạch huấn luyện mô hình mạnh nhất

Tổng hợp ngày 26/10/2026 từ kết quả tìm kiếm trên web. **Số ảnh, tên lớp và giấy phép lấy từ trang giới thiệu, chưa được tải về kiểm tra.** Mở từng trang để xác nhận trước khi dùng. Mục nào chưa kiểm chứng đều ghi rõ.

## 1. Kết luận ngắn

- Không có bộ nào bao phủ đủ điện thoại, ngủ gục, gục xuống bàn, đánh nhau, hút thuốc. Phải **ghép nhiều bộ** và **tự thêm ảnh từ chính lớp học của bạn**.
- Mô hình COCO và các mô hình tổng quát bỏ sót vì chưa từng thấy "điện thoại trong lòng, camera xa" hay "úp mặt vào tay". Đã đo: tăng kích thước mô hình (m, l, x) hầu như không giúp, **dữ liệu mới là điểm nghẽn**.
- Chia thành 3 hướng riêng, vì mỗi hành vi cần một loại dữ liệu khác nhau:

| Hành vi | Hướng làm | Loại dữ liệu |
|---|---|---|
| Điện thoại, gục đầu, ngủ gục | Huấn luyện YOLO phát hiện vật thể | Ảnh có khung (định dạng YOLO) |
| Hút thuốc | Huấn luyện YOLO (đã có) | Ảnh có khung |
| Đánh nhau | Giữ luật khung xương, chỉnh ngưỡng bằng video | Video có nhãn có/không bạo lực |

## 2. Dữ liệu ảnh có khung (điện thoại, gục đầu, ngủ)

### Ưu tiên cao
| Bộ | Nội dung | Ghi chú |
|---|---|---|
| [SCB-Dataset5](https://arxiv.org/pdf/2304.02488) | 7.428 ảnh, 106.830 nhãn, 20 lớp, có cúi đầu, dùng điện thoại, nằm bò ra bàn | Tải ở GitHub `Whiffe/SCB-dataset`. Không thấy lớp "ngủ" riêng. **Giấy phép chưa rõ**, đọc file LICENSE và README trong repo |
| [SCB-Dataset3](https://arxiv.org/pdf/2310.02522) | 5.686 ảnh, 45.578 nhãn, 6 hành vi: giơ tay, đọc, viết, dùng điện thoại, cúi đầu, nằm bò ra bàn | Cùng repo. Các tác giả báo mAP tới 80,3% (YOLOv5/7/8) |
| Student Behaviour Detection (Mywork) | Khoảng 2.470 ảnh, lớp Using_phone, sleep, bow_head | Roboflow Universe, [tìm theo class:sleep](https://universe.roboflow.com/search?q=class%3Asleep). Chưa có link trực tiếp |
| Ambient Intelligence Classroom (ĐH Công nghệ Quốc gia Đài Bắc) | Khoảng 1.350 ảnh, lớp Drowsy/Sleeping, Looking down, Using-Phone | Roboflow Universe. Chưa có link trực tiếp |

### Bổ sung
| Bộ | Nội dung | Ghi chú |
|---|---|---|
| [Student Behaviour (Burak)](https://universe.roboflow.com/burak-koyfx/student-behaviour) | 4 lớp, có looking at phone, sleeping | CC BY 4.0. Repo đã có lệnh tải trong `scripts/download_datasets.py` |
| [student-behaviors (prcv)](https://universe.roboflow.com/prcv/student-behaviors) | 6 lớp: Sleeping, Using Phone, Distracting, Focusing, Hand Raising | CC BY 4.0 |
| [student-classroom-activity](https://universe.roboflow.com/studentactivity/student-classroom-activity) | 3 lớp: phone, sleep, study | |
| [classroom (yolo)](https://universe.roboflow.com/yolo-vvz1a/classroom-ct9lw) | Khoảng 270 ảnh | Cũ (khoảng 4 năm), nhỏ, ít giá trị |

### Riêng cho điện thoại cầm tay
Điện thoại là lớp khó nhất (vật nhỏ, hay bị che). Nên thêm:
- [hand phone detection (carols-work)](https://universe.roboflow.com/carols-work/hand-phone-detection), CC BY 4.0.
- [phone-in-hand](https://universe.roboflow.com/phone-in-hand), khoảng 257 ảnh. Nhỏ nhưng đúng chủ đề.
- Các bộ nhiều lớp có hand và phone: [310M](https://universe.roboflow.com/s-workspace-vaedj/310m), [object-detection2](https://universe.roboflow.com/dbsdufhr1946-gmail-com/object-detection2-5h1pi).
- Chưa kiểm tra chất lượng nhãn và kích thước điện thoại trong ảnh. Xem thử vài chục ảnh mỗi bộ.

### Bộ không dùng được
- Bộ của R. Zheng và cộng sự (70 nghìn giơ tay, 20 nghìn đứng, 3 nghìn ngủ) lấy từ camera giám sát thật ở 30 trường và **không công khai**.

## 3. Đánh nhau

Hướng chính là luật khung xương trong `core/fight.py`. Các bộ video dưới đây dùng để **đo và chỉnh ngưỡng**, không dùng để huấn luyện YOLO.

| Bộ | Nội dung | Truy cập |
|---|---|---|
| [RWF-2000](https://arxiv.org/pdf/1911.05913) | 2.000 clip camera giám sát, nhãn theo clip (có/không bạo lực) | Công khai trên GitHub của tác giả |
| [NTU CCTV-Fights](https://rose1.ntu.edu.sg/dataset/cctvFights/) | 1.000 video đánh nhau thật (280 CCTV, 720 từ điện thoại...), có thời điểm bắt đầu và kết thúc, 7,2 GB | **Phải đăng ký và được duyệt**, ký thỏa thuận |
| Hockey Fight, RLVS, UCF-Crime | Phổ biến trong bài báo | Chưa tìm được nguồn tải chính thức, tự kiểm tra |

Tài liệu tham khảo về phát hiện bạo lực bằng khung xương trong trường học: [Omarov 2022](https://doi.org/10.32604/cmc.2022.024566), [MoveNet nhận diện bắt nạt](https://thesai.org/Downloads/Volume14No5/Paper_78-MoveNET_Enabled_Neural_Network_for_Fast_Detection_of_Physical_Bullying.pdf), [Hammami 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6938897/).

Nếu muốn đi xa hơn luật thủ công: lấy chuỗi khung xương từ video (yolo11-pose), trích đặc trưng tốc độ, góc, khoảng cách giữa hai người trong cửa sổ 1–2 giây, rồi huấn luyện bộ phân loại nhỏ (SVM hoặc mạng nhỏ) trên RWF-2000 cộng clip của bạn. Cách này đã được các bài báo trên dùng.

## 4. Hút thuốc và mắt

Đã có sẵn trong repo, dùng lại:
- `python scripts/download_datasets.py smoking` rồi `scripts/prepare_smoking_dataset.py`.
- `python scripts/download_datasets.py eyes` rồi `scripts/prepare_eye_dataset.py`.

## 5. Bảng ghép lớp đề nghị

Gộp tất cả về 4 lớp, đúng với `custom_class_map` trong config.yaml:

| Lớp đích | Gồm các lớp nguồn |
|---|---|
| `phone` | phone, using_phone, Using-Phone, looking at phone, phone-in-hand |
| `sleeping` | sleep, sleeping, Drowsy/Sleeping |
| `head_down` | bow head, bowing the head, leaning over the table, Looking down |
| `smoking` | smoking (bộ đã có) |

Các lớp khác như giơ tay, đọc, viết, study, focusing nên **loại hoặc giữ làm nền** (không gán), để mô hình không học nhầm.

**Cẩn thận:** "nằm bò ra bàn", "cúi đầu đọc bài" và "ngủ" dễ nhầm lẫn giữa các bộ do mỗi nhóm gán nhãn một kiểu. Xem 30–50 ảnh mỗi lớp mỗi bộ trước khi gộp.

## 6. Dữ liệu từ chính lớp của bạn (quan trọng nhất)

Mô hình chỉ giỏi trên cảnh giống cảnh đã học.

1. Cắt khung hình từ các video đã quay, cách nhau 1–2 giây. Mục tiêu 1.000–2.000 ảnh, **bao gồm cả ảnh bình thường** để mô hình biết thế nào là không có hành vi.
2. Quay thêm cảnh diễn có chủ đích: điện thoại trong lòng, dưới bàn, cầm lên; nằm gục úp mặt vào tay; ngồi sát nhau; nhiều góc camera và thời điểm sáng tối.
3. Gán nhãn nháp bằng mô hình lớn, rồi sửa tay trong Roboflow hoặc CVAT.
4. **Giữ riêng 15–20% làm tập kiểm tra**, không đưa vào huấn luyện. Chia theo video chứ không chia theo khung hình, nếu không số đo sẽ cao ảo.
5. Cần sự đồng ý của học sinh và nhà trường khi quay và dùng ảnh.

## 7. Công thức huấn luyện đề nghị

Đây là khuyến nghị theo thông lệ, chưa được thử trên dữ liệu của bạn.

- Mô hình: `yolo11m.pt` (GPU RTX 3050 4 GB chạy được nhưng cần giảm batch xuống 8 hoặc 4). Máy yếu hơn dùng `yolo11s.pt`.
- Độ phân giải huấn luyện: 960 (điện thoại là vật nhỏ). 640 sẽ làm mất chi tiết.
- Số epoch: 80–150, bật dừng sớm.
- Tăng cường dữ liệu: lật ngang, thay đổi độ sáng, mosaic. Tránh xoay mạnh vì học sinh luôn ngồi thẳng.
- Trộn ảnh của bạn với tỉ lệ cao hơn ảnh công khai (ví dụ nhân đôi ảnh của bạn trong tập huấn luyện).
- Lệnh có sẵn: `python scripts/train_behavior.py --data <data.yaml> --model yolo11m.pt --imgsz 960 --batch 8`.

## 8. Cách đo xem có tốt lên không

- Dùng `evaluate_clips.py` với thư mục `clips/phone`, `clips/head_down`, `clips/sleeping`, `clips/normal` (và clip đánh nhau).
- Theo dõi hai số: **tỉ lệ phát hiện đúng** và **tỉ lệ báo nhầm** trên clip bình thường. Với báo động lớp học thì báo nhầm thường gây khó chịu hơn bỏ sót.
- Chỉnh ngưỡng (`phone_conf`, `person_conf`, thời gian trong `timing`) sau khi huấn luyện, dựa trên số đo chứ không đoán.

## 9. Giấy phép và đạo đức

- Nhiều bộ Roboflow là CC BY 4.0 (phải ghi nguồn). SCB-Dataset chưa xác nhận giấy phép. CCTV-Fights hạn chế theo thỏa thuận nghiên cứu.
- Nếu nộp thi KHKT hoặc công bố, ghi rõ nguồn dữ liệu và bài báo trích dẫn trong báo cáo.
- Ảnh học sinh là dữ liệu nhạy cảm: xin phép, chỉ lưu cục bộ, không đăng công khai.

## 10. Việc cần làm tiếp

- [ ] Tải SCB-Dataset5 theo hướng dẫn trong repo `Whiffe/SCB-dataset`, đọc LICENSE.
- [ ] Lấy API key Roboflow miễn phí, tải các bộ ở mục 2.
- [ ] Xem mẫu và chốt bảng ghép lớp ở mục 5.
- [ ] Cắt khung hình và gán nhãn ảnh của lớp bạn (mục 6).
- [ ] Huấn luyện, đo bằng clip kiểm tra riêng (mục 7 và 8).
