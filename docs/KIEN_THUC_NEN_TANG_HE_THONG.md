# Kiến thức cần nắm về hệ thống "Lớp học AI"

## Phần 1. Hệ thống làm gì, theo ba bước

1. **Nhìn:** AI xem ảnh từ camera, tìm ra từng học sinh, điện thoại, và vị trí đầu, vai, tay của từng em.
2. **Hiểu:** bộ quy tắc do nhóm viết biến những gì AI thấy thành hành vi: "em này gục đầu", "em kia cầm điện thoại".
3. **Báo:** nếu hành vi kéo dài đủ lâu thì hiện khung đỏ, phát chuông và giọng đọc, ghi nhật ký.

**Câu nên nhớ:** *AI chỉ giúp máy "nhìn". Phần "hiểu" là quy tắc do nhóm tự viết, và đó là phần quan trọng nhất của đề tài.*

### Hai chế độ
- **Lớp học:** điện thoại, gục đầu xuống bàn, ngủ gật.
- **Hành lang:** đánh nhau, hút thuốc.
- Mỗi chế độ chỉ chạy các mô hình nó cần, nên máy yếu vẫn dùng được.

## Phần 2. AI cơ bản (chỉ cần hiểu ở mức này)

### AI học như thế nào
- Cho máy xem rất nhiều ảnh đã được người khoanh sẵn và ghi tên ("đây là điện thoại", "đây là bạn đang ngủ"). Máy tự tìm ra đặc điểm chung.
- Giống học sinh làm nhiều đề có đáp án rồi mới đi thi.
- Sau khi học, ta để riêng một số ảnh máy chưa từng thấy để "thi", xem máy nhận ra thật hay chỉ học thuộc lòng.

### Dùng lại mô hình có sẵn
- Có những mô hình đã "biết nhìn" (nhận ra người, điện thoại...). Nhóm lấy mô hình đó rồi cho học thêm ảnh lớp học.
- Giống một bạn đã học giỏi, ta chỉ dạy thêm phần mới: tiết kiệm thời gian và không cần máy quá mạnh.

### Ba công cụ AI nhóm dùng
- **YOLO (tìm vật):** nhìn ảnh và khoanh khung quanh từng vật, ghi tên và mức chắc chắn. Ví dụ: "điện thoại, chắc chắn 0,8". Rất nhanh.
- **Khung xương:** tìm từng người và 17 điểm trên cơ thể (mũi, mắt, tai, vai, khuỷu tay, cổ tay, hông, gối, cổ chân). Biết các điểm này là biết đầu đang ngẩng hay gục, tay đang ở đâu.
- **MediaPipe (của Google):** xem mắt đang mở hay nhắm.

### Mức chắc chắn
- AI luôn cho kèm một con số 0–1 cho mỗi kết quả. Ta đặt mức tối thiểu: **đặt cao thì ít báo nhầm nhưng dễ bỏ sót; đặt thấp thì ngược lại.**

### Theo dõi từng em
- Mỗi học sinh được gán một mã số cố định, để biết "em số 7 đã gục đầu được bao lâu".
- Học sinh ngồi cố định theo bàn, nên nhóm còn dùng vị trí chỗ ngồi để giữ mã số không bị nhảy khi một em gục xuống.

### Dữ liệu của nhóm
- Gộp 6 bộ ảnh công khai, tổng 5.230 ảnh, về 3 loại: **dùng điện thoại, gục đầu/ngủ, học bình thường**.
- Chia ba phần: **4.476 ảnh để học**, **469 ảnh để theo dõi lúc học**, **285 ảnh giữ riêng để thi**.
- Nhóm bỏ những nhãn dễ gây nhầm (ví dụ "cúi đầu" gồm cả cúi viết bài) và dọn ảnh gần giống nhau để ảnh thi không lẫn ảnh đã học.
- Mất khoảng 82 phút để dạy trên laptop có card đồ họa RTX 3050.

### Kết quả, nói bằng lời thường
- Trên 285 ảnh chưa từng thấy: **cứ 4 lần mô hình báo thì khoảng 3 lần đúng, cứ 4 hành vi thật thì thấy được khoảng 3** (khoảng 75–80%).
- Điểm yếu nhất là điện thoại: **cứ 10 điện thoại thật thì bỏ sót khoảng 4** (nhỏ, hay bị che).
- Vì vậy hệ thống **không tin vào một mô hình**: còn có khung xương, YOLO tìm điện thoại và các quy tắc dưới đây.
- Bản đầu tự chấm gần 100% nhưng thi với đề dễ (79 ảnh cùng nguồn). Bản hiện tại điểm thấp hơn vì đề khó và thật hơn, nên đáng tin hơn.

## Phần 3. Các quy tắc phát hiện (phần quan trọng nhất)

### Quy tắc 1. Gục đầu xuống bàn
- Máy đo **đầu cao hơn vai bao nhiêu**, rồi chia cho **độ rộng vai**:

  tỉ lệ = (độ cao đầu so với vai) / (độ rộng vai)

- Ngồi thẳng: khoảng 0,5 đến 1.
- Cúi viết bài: vẫn dương, vẫn thấy mặt: **không báo**.
- Nằm gục: nhỏ hơn 0,05 và không thấy mặt (úp mặt xuống bàn): **báo sau 3 giây**.
- **Vì sao chia cho độ rộng vai?** Em ngồi gần trông to, ngồi xa trông nhỏ. Chia cho độ rộng vai thì tỉ lệ không đổi dù gần hay xa, nên dùng chung một con số cho cả lớp.
- **Vì sao thêm điều kiện không thấy mặt?** Để phân biệt úp mặt xuống bàn với cúi đầu đọc bài.

### Quy tắc 2. Dùng điện thoại
- Máy tìm điện thoại trong ảnh.
- Điện thoại chỉ tính là của một em khi nằm **gần cổ tay** của em đó (cách nhỏ hơn 1,1 lần độ rộng vai).
- Để trên bàn mà không ai cầm: **không báo**. Cầm liên tục 2 giây: **báo**.

### Quy tắc 3. Nhắm mắt, ngủ gật
- MediaPipe cho điểm nhắm mắt từ 0 đến 1; từ 0,5 trở lên coi là nhắm.
- Chỉ đo khi mặt đủ lớn. Mặt quá nhỏ thì hệ thống nói "không đủ thông tin" chứ không đoán bừa.
- Nhắm mắt liên tục hoặc nằm gục liên tục 10 giây: **báo ngủ gật**.

### Quy tắc 4. Kiểm tra chéo
- Mô hình học thêm hay nhầm bạn "ngồi cúi nhẹ, tay đặt trên bàn" thành đang ngủ.
- Nếu mô hình báo "ngủ" nhưng khung xương thấy rõ mặt và đầu vẫn cao hơn vai: **bỏ báo**, vì người nằm gục úp mặt thì không thấy mặt.
- Nguyên tắc: **hai nguồn thông tin phải đồng ý với nhau mới báo.**

### Quy tắc 5. Phải đủ lâu mới báo
- Cúi nhặt bút hay liếc điện thoại một giây không phải vi phạm.

  - Dùng điện thoại: 2 giây
  - Gục đầu: 3 giây
  - Ngủ gục / ngủ gật: 10 giây
  - Hút thuốc: 2 giây
  - Đánh nhau: 0,5 giây

- **Thời gian ân hạn 1,5 giây:** mô hình lỡ bỏ sót vài hình thì đồng hồ không quay về 0.
- **Thời gian chờ:** đã báo một em thì 10 giây sau mới báo lại; riêng gục đầu và ngủ gật là 60 giây, để không nhắc liên tục khi em còn đang gục.

### Quy tắc 6. Đánh nhau (hành lang)
- Chỉ nhìn **khung xương, cổ tay của từng người**, không cần mô hình riêng.
- **Cú vung:** cổ tay di chuyển nhanh (hơn 5 lần độ rộng vai mỗi giây).
- **Cú đánh:** cú vung đi vào thân người khác và hướng về người đó.
- **Kết luận đánh nhau:** có từ 3 cú đánh trong 2,5 giây, hoặc hai người đứng sát nhau và cả hai cùng vung tay liên tục (xô đẩy).
- Giơ tay phát biểu, vẫy tay, đưa bút cho bạn chỉ có một cú vung lẻ hoặc không chạm vào người kia: **không báo**.
- Nơi đông người đòi nhiều dấu hiệu hơn.
- **Hạn chế thật thà:** chưa thử trên video đánh nhau thật; đùa nghịch mạnh tay có thể bị báo nhầm.

### Quy tắc 7. Hút thuốc (hành lang)
- Dùng mô hình tìm điếu thuốc. Điếu thuốc rất nhỏ nên mới bắt được khoảng một nửa số ảnh có thuốc, nhưng không báo nhầm trên ảnh bình thường đã thử.
- Là phần yếu nhất, chỉ nên coi là cảnh báo bổ trợ.

### Quy tắc 8. Giữ đúng mã số từng em
- Khi một em gục xuống, hình dáng đổi mạnh nên máy dễ nhầm sang người khác.
- Nhóm dùng **vị trí chỗ ngồi** để giữ mã số ổn định, nhờ đó đồng hồ đếm thời gian không bị ngắt.

### Chỉ số tập trung
- Mỗi em: 100 điểm khi bình thường, 50 khi có dấu hiệu nhưng chưa đủ lâu để báo, 0 khi đang bị cảnh báo. Điểm lớp là trung bình các em.
- 80 trở lên: tốt; 55–79: trung bình; dưới 55: dễ mất tập trung.
- Đây là chỉ số tham khảo do nhóm tự đặt, **chưa kiểm chứng với giáo viên**.

## Phần 4. Phần mềm và cách dùng

- Chạy hoàn toàn trên **một máy của giáo viên/nhà trường**; trang web chỉ mở trên máy đó.
- Nguồn hình: webcam, camera của trường, điện thoại làm camera (quét mã QR), video có sẵn.
- Cảnh báo: khung màu (xanh bình thường, cam có dấu hiệu, đỏ cảnh báo), chuông, giọng đọc tiếng Việt, tùy chọn gửi Telegram.
- Mọi con số (ngưỡng, thời gian) nằm trong tệp cấu hình và chỉnh được trên giao diện.
- Máy yếu: tự dùng mô hình nhẹ hơn, chạy mô hình phụ thưa hơn; mỗi giây chỉ cần xử lí 2–3 hình là đủ vì hành vi kéo dài vài giây.
- Đóng gói thành bộ cài Windows và Ubuntu; cài một lần là dùng.
- Riêng tư: không nhận diện khuôn mặt hay tên, video không rời khỏi máy, có thể tắt lưu ảnh, tự xóa dữ liệu cũ.

## Phần 5. Cái gì là AI, cái gì là quy tắc

- **AI (dùng sẵn):** tìm người và khung xương, tìm điện thoại, xem mắt.
- **AI (nhóm dạy thêm):** nhận ra điện thoại / gục ngủ / học bình thường; nhận ra điếu thuốc.
- **Quy tắc nhóm tự viết:** tỉ lệ đầu–vai, điện thoại gần cổ tay, kiểm tra chéo, thời gian, đánh nhau, giữ mã số, chỉ số tập trung.

## Phần 6. Hạn chế nên tự nói trước

- Chưa thử ở lớp học thật vì cần sự đồng ý của nhà trường, phụ huynh và học sinh.
- Điện thoại nhỏ, giấu dưới gầm bàn thì khó thấy; bàn cuối khó nhận ra vật nhỏ.
- Đánh nhau chưa kiểm chứng trên video thật; hút thuốc còn yếu.
- Chỉ số tập trung chưa kiểm chứng với giáo viên.
- Ảnh công khai phần lớn quay ở nước ngoài, khác lớp học Việt Nam.
- Hướng khắc phục: thu video lớp học Việt Nam có đồng ý, dạy lại, và đo tỉ lệ báo đúng, báo nhầm của cả hệ thống.

## Phần 7. Tự kiểm tra: bạn có trả lời được không?

- Hệ thống làm việc theo mấy bước? Bước nào là phần nhóm tự làm?
- Làm sao phân biệt cúi viết bài với gục đầu ngủ?
- Vì sao chia cho độ rộng vai?
- Điện thoại nằm trên bàn có bị báo không? Vì sao?
- Vì sao hệ thống không báo ngay khi vừa thấy hành vi?
- Kiểm tra chéo là gì, ví dụ?
- Đánh nhau được nhận ra bằng cách nào? Có nhầm với giơ tay không?
- Vì sao điểm mô hình thấp hơn bản đầu mà vẫn nói là tốt hơn?
- Mô hình bỏ sót điện thoại thì hệ thống bù thế nào?
- Dữ liệu từ đâu? Chia ba phần để làm gì?
- Hệ thống có xâm phạm quyền riêng tư không?
- Hạn chế lớn nhất là gì và sẽ làm gì tiếp?
