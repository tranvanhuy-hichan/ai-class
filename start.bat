@echo off
chcp 65001 >nul
cd /d "%~dp0"
title He thong canh bao hanh vi lop hoc
where python >nul 2>nul || (
  echo Chua cai Python. Tai tai https://www.python.org/downloads/ va tick "Add Python to PATH".
  pause & exit /b
)
if not exist .venv\Scripts\python.exe (
  echo [1/2] Lan dau chay: dang tao moi truong va cai thu vien, mat khoang 5-15 phut...
  python -m venv .venv
)
if not exist .venv\installed.txt (
  .venv\Scripts\python -m pip install --upgrade pip
  .venv\Scripts\python -m pip install -r requirements.txt && echo ok> .venv\installed.txt
)
echo [2/2] Dang khoi dong...
.venv\Scripts\python web.py %*
pause
