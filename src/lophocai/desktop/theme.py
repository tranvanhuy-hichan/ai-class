"""Giao diện tối/sáng của app desktop — bảng màu trung tính kiểu ứng dụng desktop.

  theme.manager.set_mode("dark" | "light")   đổi giao diện, phát tín hiệu manager.changed
  theme.c("surface")                         mã màu hiện tại của một token ("#111723"...)
  theme.qcolor("accent", 0x22)               QColor có độ trong suốt (alpha 0-255)
  theme.rgba("bad", 26)                      chuỗi "rgba(r,g,b,a)" dùng trong stylesheet

Widget tự vẽ (ui.py) đọc màu qua các hàm trên và nối manager.changed để vẽ lại; widget thường
chỉ cần đặt objectName/property cho stylesheet toàn cục ở đây (role, card, ...).
"""
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette

DARK = {
    "bg": "#1c1c1e", "surface": "#262629", "surface2": "#2e2e32", "surface3": "#3a3a3f", "border": "#3d3d42",
    "text": "#e8e8ea", "muted": "#9b9ba1", "faint": "#6f6f76",
    "accent": "#3584e4", "accent2": "#62a0ea", "ok": "#33b679", "bad": "#e5484d",
    "phone": "#a855f7", "head": "#f59e0b", "sleep": "#f43f5e", "fight": "#0ea5e9", "smoke": "#84cc16",
    "accent_soft_alpha": 0x30,
}
LIGHT = {**DARK,
         "bg": "#f4f4f5", "surface": "#ffffff", "surface2": "#f6f6f7", "surface3": "#e6e6e9", "border": "#d9d9dd",
         "text": "#1f1f23", "muted": "#66666d", "faint": "#9a9aa1", "accent_soft_alpha": 0x26}

BEHAVIOR_COLOR_TOKEN = {"phone": "phone", "head_down": "head", "sleeping": "sleep", "fighting": "fight", "smoking": "smoke"}
BEHAVIOR_SHORT = {"phone": "Điện thoại", "head_down": "Gục đầu", "sleeping": "Ngủ gục", "fighting": "Đánh nhau", "smoking": "Hút thuốc"}

FONT_FAMILY = "Sans Serif"   # được đặt lại thành font hệ thống trong init()
FONT_PX = 13


def system_mode():
    """Giao diện sáng/tối đang dùng của hệ điều hành ("dark" nếu không biết)."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    try:
        return "light" if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else "dark"
    except Exception:
        return "dark"


class ThemeManager(QObject):
    """pref: lựa chọn của người dùng ("system" | "dark" | "light"); mode: giao diện đang áp dụng ("dark" | "light")."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.pref = "dark"
        self.mode = "dark"
        self.colors = dict(DARK)

    def set_pref(self, pref):
        self.pref = pref if pref in ("system", "dark", "light") else "dark"
        self._resolve()

    def _resolve(self):
        mode = system_mode() if self.pref == "system" else self.pref
        if mode != self.mode or self.colors.get("bg") != (LIGHT if mode == "light" else DARK)["bg"]:
            self.mode = mode
            self.colors = dict(LIGHT if mode == "light" else DARK)
            self.changed.emit()

    def set_mode(self, mode):
        self.set_pref("light" if mode == "light" else "dark")

    def toggle(self):
        self.set_pref("dark" if self.mode == "light" else "light")


manager = ThemeManager()


# ---------------------------------------------------------------- màu
def c(token):
    """Mã màu "#rrggbb" hiện tại của token (hoặc trả lại nguyên nếu đã là mã màu)."""
    if isinstance(token, str) and token.startswith("#"):
        return token
    return manager.colors[token]


resolve = c


def qcolor(token, alpha=None):
    col = QColor(c(token))
    if alpha is not None:
        col.setAlpha(alpha)
    return col


def behavior_color(behavior):
    return c(BEHAVIOR_COLOR_TOKEN.get(behavior, "accent"))


def rgba(token, alpha):
    col = QColor(c(token))
    return f"rgba({col.red()}, {col.green()}, {col.blue()}, {alpha})"


def mix(token_a, token_b, t):
    """Trộn màu a với b theo tỉ lệ t (0..1 = % của b), trả "#rrggbb"."""
    a, b = QColor(c(token_a)), QColor(c(token_b))
    r = round(a.red() + (b.red() - a.red()) * t)
    g = round(a.green() + (b.green() - a.green()) * t)
    bl = round(a.blue() + (b.blue() - a.blue()) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def accent_soft():
    return qcolor("accent", manager.colors["accent_soft_alpha"])


def lighten(token, factor=1.08):
    col = QColor(c(token))
    return col.lighter(int(factor * 100)).name()


# ---------------------------------------------------------------- font
_chevron_cache = {}


def _chevron_png():
    """Mũi tên xổ xuống của ô chọn (QSS chỉ nhận ảnh từ file)."""
    key = manager.mode
    if key in _chevron_cache:
        return _chevron_cache[key]
    from .icons import icon_pixmap
    path = Path(tempfile.gettempdir()) / f"lophocai_chevron_{key}.png"
    icon_pixmap("chevron-down", 14, "muted", 2.2).save(str(path), "PNG")
    _chevron_cache[key] = path.as_posix()
    return _chevron_cache[key]


# ---------------------------------------------------------------- stylesheet
def build_qss():
    k = manager.colors
    return f"""
* {{ font-family: "{FONT_FAMILY}"; font-size: {FONT_PX}px; color: {k['text']}; }}
QMainWindow, QWidget#root {{ background: {k['bg']}; }}
QWidget#side {{ background: {k['surface']}; border-right: 1px solid {k['border']}; }}
QWidget#top {{ background: {k['bg']}; border-bottom: 1px solid {k['border']}; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QWidget#pageHost {{ background: transparent; }}
QLabel {{ background: transparent; }}
QDialog, QMessageBox {{ background: {k['surface']}; }}
QToolTip {{ background: {k['surface3']}; color: {k['text']}; border: 1px solid {k['border']};
           border-radius: 6px; padding: 4px 8px; font-size: 12px; }}

QFrame[card="true"] {{ background: {k['surface']}; border: 1px solid {k['border']}; border-radius: 10px; }}
QFrame[card="true"][alarm="true"] {{ border-color: {k['bad']};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {mix('surface', 'bad', 0.10)}, stop:0.6 {k['surface']}, stop:1 {k['surface']}); }}
QFrame[card="true"][dashed="true"] {{ background: transparent; border: 2px dashed {k['border']}; }}
QFrame[card="true"][dashed="true"]:hover {{ border-color: {k['accent']}; }}
QFrame[inner="true"] {{ background: {k['surface2']}; border: 1px solid {k['border']}; border-radius: 8px; }}
QFrame#foot {{ background: {k['surface2']}; border: none; border-radius: 8px; }}
QFrame[sep="true"] {{ background: {k['border']}; border: none; max-height: 1px; min-height: 1px; }}

QLabel[role="muted"] {{ color: {k['muted']}; }}
QLabel[role="faint"] {{ color: {k['faint']}; }}
QLabel[role="hint"] {{ color: {k['muted']}; font-size: 12.5px; }}
QLabel[role="small"] {{ color: {k['muted']}; font-size: 12px; }}
QLabel[role="h1"] {{ font-size: 20px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: 18px; font-weight: 700; }}
QLabel[role="bold"] {{ font-weight: 600; }}
QLabel[role="th"] {{ color: {k['muted']}; font-size: 12px; font-weight: 500; }}
QLabel[role="kpiValue"] {{ font-size: 26px; font-weight: 700; }}
QLabel[role="kpiValue"][alarm="true"] {{ color: {k['bad']}; }}
QLabel[role="kpiLabel"] {{ color: {k['muted']}; font-size: 12px; }}
QLabel[role="ok"] {{ color: {k['ok']}; font-size: 13px; }}
QLabel[role="err"] {{ color: {k['bad']}; font-size: 13px; }}
QLabel[role="code"] {{ background: {k['surface3']}; border-radius: 5px; padding: 1px 6px; font-size: 12px; font-family: "DejaVu Sans Mono", monospace; }}
QLabel[role="chipText"] {{ color: {k['muted']}; font-size: 13px; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {k['surface2']}; border: 1px solid {k['border']}; border-radius: 6px;
    padding: 6px 10px; min-height: 20px; selection-background-color: {k['accent']}; selection-color: #fff; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {k['accent']}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {k['faint']}; }}
QAbstractSpinBox {{ qproperty-alignment: AlignRight; }}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0; height: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url("{_chevron_png()}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {k['surface']}; border: 1px solid {k['border']}; border-radius: 8px;
    selection-background-color: {rgba('accent', k['accent_soft_alpha'])}; selection-color: {k['text']}; outline: none; padding: 4px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {k['surface3']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {k['faint']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {k['surface3']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {k['faint']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSlider::groove:horizontal {{ height: 4px; background: {k['surface3']}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {k['accent']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {k['accent']}; width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; }}
QSlider[onDark="true"]::groove:horizontal {{ background: rgba(255,255,255,40); }}

QTableWidget {{ background: transparent; border: none; gridline-color: transparent; outline: 0; }}
QTableWidget::item {{ border-top: 1px solid {k['border']}; padding: 6px 10px; }}
QTableWidget::item:selected {{ background: transparent; color: {k['text']}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: transparent; color: {k['muted']}; border: none; padding: 8px 10px;
    font-size: 12px; font-weight: 500; }}
QTableCornerButton::section {{ background: transparent; border: none; }}

QPushButton {{ background: {k['surface2']}; border: 1px solid {k['border']}; border-radius: 6px; padding: 6px 14px; font-weight: 500; }}
QPushButton:hover {{ background: {k['surface3']}; }}
QMenuBar {{ background: {k['surface']}; border-bottom: 1px solid {k['border']}; padding: 2px 6px; }}
QMenuBar::item {{ background: transparent; padding: 5px 10px; border-radius: 5px; }}
QMenuBar::item:selected {{ background: {k['surface3']}; }}
QMenu {{ background: {k['surface']}; border: 1px solid {k['border']}; border-radius: 6px; padding: 4px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {rgba('accent', k['accent_soft_alpha'])}; }}
QMenu::item:disabled {{ color: {k['faint']}; }}
QMenu::separator {{ height: 1px; background: {k['border']}; margin: 4px 6px; }}
QStatusBar {{ background: {k['surface']}; border-top: 1px solid {k['border']}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {k['muted']}; font-size: 12px; padding: 0 6px; }}

QMessageBox QPushButton {{ min-width: 80px; }}
"""


def _palette():
    k = manager.colors
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(k["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(k["text"]))
    p.setColor(QPalette.ColorRole.Base, QColor(k["surface2"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(k["surface"]))
    p.setColor(QPalette.ColorRole.Text, QColor(k["text"]))
    p.setColor(QPalette.ColorRole.Button, QColor(k["surface2"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(k["text"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(k["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(k["surface3"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(k["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(k["faint"]))
    p.setColor(QPalette.ColorRole.Link, QColor(k["accent"]))
    return p


def apply_theme(app):
    """Áp giao diện cho cả ứng dụng. Gọi lại khi đổi sáng/tối."""
    app.setStyle("Fusion")
    font = QFont(FONT_FAMILY)
    font.setPixelSize(FONT_PX)
    app.setFont(font)
    app.setPalette(_palette())
    app.setStyleSheet(build_qss())


def init(app, pref="system"):
    """Khởi tạo lần đầu: nạp font, đặt lựa chọn giao diện, áp stylesheet, tự áp lại khi đổi
    (kể cả khi hệ điều hành đổi sáng/tối lúc đang chọn "Theo hệ thống")."""
    global FONT_FAMILY
    FONT_FAMILY = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont).family()
    manager.pref = pref if pref in ("system", "dark", "light") else "system"
    manager.mode = system_mode() if manager.pref == "system" else manager.pref
    manager.colors = dict(LIGHT if manager.mode == "light" else DARK)
    apply_theme(app)
    manager.changed.connect(lambda: apply_theme(app))
    try:
        app.styleHints().colorSchemeChanged.connect(lambda *_: manager.pref == "system" and manager._resolve())
    except AttributeError:
        pass
