#!/usr/bin/env bash
# Cài Lớp học AI cho riêng tài khoản đang dùng, KHÔNG cần sudo.
#   ./packaging/install_user.sh            cài từ dist/LopHocAI (sau khi build)
#   ./packaging/install_user.sh --remove   gỡ cài đặt
set -euo pipefail
cd "$(dirname "$0")/.."
APP="$HOME/.local/opt/lophocai"
BIN="$HOME/.local/bin/lophocai"
DESKTOP="$HOME/.local/share/applications/lophocai.desktop"
ICON="$HOME/.local/share/icons/hicolor/256x256/apps/lophocai.png"

if [ "${1:-}" = "--remove" ]; then
  rm -rf "$APP" "$BIN" "$DESKTOP" "$ICON"
  echo "Đã gỡ. Dữ liệu (nhật ký, ảnh) vẫn còn ở ~/.local/share/LopHocAI, xoá tay nếu muốn."
  exit 0
fi

[ -x dist/LopHocAI/LopHocAI ] || { echo "Chưa build. Chạy ./packaging/build_linux.sh trước."; exit 1; }
rm -rf "$APP"
mkdir -p "$APP" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
cp -a dist/LopHocAI/. "$APP/"
ln -sf "$APP/LopHocAI" "$BIN"
cp packaging/icon.png "$ICON"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=Lớp học AI
Comment=Cảnh báo hành vi bất thường của học sinh trong lớp học
Exec=$APP/LopHocAI
Icon=lophocai
Terminal=false
StartupWMClass=LopHocAI
Categories=Education;
EOF
update-desktop-database "$(dirname "$DESKTOP")" 2>/dev/null || true
echo "Đã cài. Mở 'Lớp học AI' trong menu ứng dụng, hoặc chạy lệnh: lophocai"
