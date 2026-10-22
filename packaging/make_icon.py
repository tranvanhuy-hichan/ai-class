"""Vẽ biểu tượng ứng dụng (icon.png cho Linux, icon.ico cho Windows). Không cần file ảnh có sẵn."""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
S = 1024  # vẽ to rồi thu nhỏ cho mịn

img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
# Nền vuông bo góc, chuyển màu tím -> xanh ngọc (giống logo trên web)
grad = Image.new("RGBA", (S, S))
px = grad.load()
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S)
        px[x, y] = (int(109 + (34 - 109) * t), int(106 + (211 - 106) * t), int(254 + (238 - 254) * t), 255)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle((40, 40, S - 40, S - 40), radius=230, fill=255)
img.paste(grad, (0, 0), mask)

# Hình máy quay màu trắng
d = ImageDraw.Draw(img)
w = 46
d.rounded_rectangle((190, 330, 680, 700), radius=70, outline="white", width=w)
d.polygon([(700, 470), (850, 370), (850, 660), (700, 560)], outline="white", width=w)
d.line([(700, 470), (850, 370), (850, 660), (700, 560), (700, 470)], fill="white", width=w, joint="curve")
# Chấm đỏ "đang ghi"
d.ellipse((300, 440, 400, 540), fill=(244, 63, 94, 255))

img = img.resize((256, 256), Image.LANCZOS)
img.save(HERE / "icon.png")
img.save(HERE / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Đã tạo packaging/icon.png và packaging/icon.ico")
