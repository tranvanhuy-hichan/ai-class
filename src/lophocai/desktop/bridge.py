"""Chuyển khung hình OpenCV (BGR) sang QImage để hiển thị. Việc lấy khung theo nhịp cố định nằm ở LivePage
(QTimer gọi cam.latest_bgr()), không phát signal cho từng khung camera sinh ra."""
import cv2
from PySide6.QtGui import QImage


def bgr_to_qimage(frame):
    """numpy BGR -> QImage RGB888, sao chép dữ liệu vì buffer gốc có thể bị worker ghi đè ngay sau đó."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
