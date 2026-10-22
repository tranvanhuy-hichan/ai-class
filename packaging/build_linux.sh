#!/usr/bin/env bash
# Build bộ cài Ubuntu/Debian (.deb) và bản nén (.tar.gz).
#   ./packaging/build_linux.sh            (dùng .venv-build có PyTorch bản CPU)
# Kết quả: dist/lophocai_<phiên bản>_amd64.deb  và  dist/LopHocAI-linux-x64.tar.gz
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${VERSION:-1.0.0}"
PY="${PY:-.venv-build/bin/python}"

echo "==> Tạo biểu tượng"
"$PY" packaging/make_icon.py

echo "==> Đóng gói bằng PyInstaller (mất vài phút)"
"$PY" -m PyInstaller packaging/lophocai.spec --noconfirm --clean --distpath dist --workpath build

echo "==> Tạo gói .deb"
PKG=build/deb
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/opt/lophocai" "$PKG/usr/bin" "$PKG/usr/share/applications" \
         "$PKG/usr/share/icons/hicolor/256x256/apps"
cp -a dist/LopHocAI/. "$PKG/opt/lophocai/"
cp packaging/icon.png "$PKG/usr/share/icons/hicolor/256x256/apps/lophocai.png"
cat > "$PKG/usr/bin/lophocai" <<'EOF'
#!/bin/sh
exec /opt/lophocai/LopHocAI "$@"
EOF
chmod 755 "$PKG/usr/bin/lophocai"
cat > "$PKG/usr/share/applications/lophocai.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Lớp học AI
Comment=Cảnh báo hành vi bất thường của học sinh trong lớp học
Exec=lophocai
Icon=lophocai
Terminal=false
StartupWMClass=LopHocAI
Categories=Education;
EOF
SIZE=$(du -sk "$PKG/opt" | cut -f1)
cat > "$PKG/DEBIAN/control" <<EOF
Package: lophocai
Version: $VERSION
Architecture: amd64
Maintainer: tranvanhuy-hichan <tranvanhuy064206@gmail.com>
Installed-Size: $SIZE
Depends: libgl1, libglib2.0-0t64 | libglib2.0-0
Recommends: pulseaudio-utils
Section: education
Priority: optional
Homepage: https://github.com/tranvanhuy-hichan/ai-class
Description: Lop hoc AI - canh bao hanh vi bat thuong cua hoc sinh
 Nhan dien hoc sinh dung dien thoai, guc dau xuong ban, ngu gat tu webcam,
 camera IP hoac camera dien thoai, canh bao bang giong noi tieng Viet.
 Chay hoan toan tren may, khong gui video ra ngoai.
EOF
dpkg-deb --root-owner-group --build "$PKG" "dist/lophocai_${VERSION}_amd64.deb"

echo "==> Tạo bản nén .tar.gz"
tar -C dist -czf dist/LopHocAI-linux-x64.tar.gz LopHocAI

ls -lh dist/*.deb dist/*.tar.gz
echo "Xong. Cài:  sudo apt install ./dist/lophocai_${VERSION}_amd64.deb"
