@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Dang khoi dong Abraham Inventory...
echo Giu cua so nay mo trong khi su dung website.
echo Dia chi: http://127.0.0.1:5000
echo.
venv\Scripts\python.exe app.py
echo.
echo May chu da dung. Nhan phim bat ky de dong cua so.
pause >nul
