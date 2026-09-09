@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d "%~dp0"

"%~dp0venv\Scripts\python.exe" -X utf8 "%~dp0sync_amis_to_supabase.py"

exit /b %ERRORLEVEL%
