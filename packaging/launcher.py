"""Điểm vào của bản đóng gói PyInstaller (file chạy không qua `python -m lophocai`)."""
import sys

from lophocai.desktop.app import main

if __name__ == "__main__":
    sys.exit(main())
