"""Bộ icon SVG lấy nguyên từ web/index.html (<symbol id="i-...">), vẽ bằng QtSvg theo màu yêu cầu.

  icon_pixmap("video", 18, "#fff")   -> QPixmap
  IconLabel("alert", 16, "bad")      -> QLabel tự đổi màu khi đổi giao diện sáng/tối

Màu có thể là mã "#rrggbb" hoặc tên màu của theme ("muted", "accent", "bad", "text"...).
"""
from functools import lru_cache

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QLabel

from . import theme

ICONS = {
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "x": '<path d="M18 6 6 18M6 6l12 12"/>',
    "trash": '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14M10 11v6M14 11v6"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
            '<rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    "video": '<path d="m16 13 5.2 3.5a.5.5 0 0 0 .8-.4V7.9a.5.5 0 0 0-.8-.4L16 10.5"/>'
             '<rect x="2" y="6" width="14" height="12" rx="2"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "bell": '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    "bell-off": '<path d="M8.7 3A6 6 0 0 1 18 8a21.3 21.3 0 0 0 .6 5"/><path d="M17 17H3s3-2 3-9a4.67 4.67 0 0 1 .3-1.7"/>'
                '<path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/><path d="m2 2 20 20"/>',
    "phone": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M12 18h.01"/>',
    "max": '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    "alert": '<path d="m21.7 18-8-14a2 2 0 0 0-3.5 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.7-3"/><path d="M12 9v4M12 17h.01"/>',
    "down": '<path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/>',
    "smoke": '<path d="M2 16h14v4H2zM18 16v4M22 16v4"/><path d="M18 12c0-2 2-2 2-4s-2-2-2-4"/>',
    "fight": '<path d="m14.5 17.5 3 3 3-3M17.5 20.5V9a3 3 0 0 0-3-3h-1"/><path d="m9.5 6.5-3-3-3 3M6.5 3.5V15a3 3 0 0 0 3 3h1"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M6.3 17.7l-1.4 1.4M19.1 4.9l-1.4 1.4"/>',
    "send": '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    "qr": '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>'
          '<rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM21 14v.01M14 21h.01M17 21h4v-4"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m17 8-5-5-5 5"/><path d="M12 3v12"/>',
    "cam": '<path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/>',
    "power": '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    "flip": '<path d="m8 3-4 4 4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "rotate": '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "play": '<path d="m6 3 14 9-14 9z"/>',
    "gauge": '<path d="m12 14 4-4"/><path d="M3.3 19a10 10 0 1 1 17.4 0"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
}

# hành vi -> tên icon (giống ICON trong index.html)
BEHAVIOR_ICON = {"phone": "phone", "head_down": "down", "sleeping": "moon", "fighting": "fight", "smoking": "smoke"}


def _svg(name, color, stroke):
    inner = ICONS[name]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{inner}</svg>')


@lru_cache(maxsize=512)
def _render(name, size, color, stroke, dpr):
    renderer = QSvgRenderer(QByteArray(_svg(name, color, stroke).encode()))
    pix = QPixmap(int(size * dpr), int(size * dpr))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def _dpr():
    app = QApplication.instance()
    screen = app.primaryScreen() if app else None
    return max(2.0, screen.devicePixelRatio()) if screen else 2.0


def icon_pixmap(name, size=18, color="text", stroke=1.75):
    """QPixmap sắc nét (vẽ ở độ phân giải gấp đôi) của icon `name`."""
    return _render(name, size, theme.resolve(color), stroke, _dpr())


def qicon(name, size=18, color="text"):
    return QIcon(icon_pixmap(name, size, color))


class IconLabel(QLabel):
    """Icon tự vẽ lại khi đổi giao diện sáng/tối (khi dùng tên màu của theme)."""

    def __init__(self, name, size=18, color="muted", parent=None):
        super().__init__(parent)
        self._name, self._size, self._color = name, size, color
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._refresh()
        theme.manager.changed.connect(self._refresh)

    def set_icon(self, name=None, color=None):
        if name:
            self._name = name
        if color:
            self._color = color
        self._refresh()

    def _refresh(self, *_):
        self.setPixmap(icon_pixmap(self._name, self._size, self._color))
