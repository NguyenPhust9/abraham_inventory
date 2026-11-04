@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"

if not exist ".env" (
    echo Chua co file .env.
    echo Hay sao chep .env.example thanh .env va dien AppID, ma bao mat.
    exit /b 1
)

"%~dp0venv\Scripts\python.exe" -X utf8 "%~dp0test_amis_stock.py"
exit /b %ERRORLEVEL%
