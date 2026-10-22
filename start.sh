#!/usr/bin/env bash
# Chạy:  ./start.sh   (Linux / macOS)
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "[1/2] Lần đầu chạy: đang tạo môi trường và cài thư viện, mất khoảng 5-15 phút..."
  python3 -m venv .venv
fi
if [ ! -f .venv/installed.txt ]; then
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt && echo ok > .venv/installed.txt
fi
echo "[2/2] Đang khởi động..."
exec .venv/bin/python web.py "$@"
