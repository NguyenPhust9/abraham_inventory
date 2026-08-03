@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

cd /d C:\Users\PC\Desktop\Inventory_bike\abraham_inventory

C:\Users\PC\Desktop\Inventory_bike\abraham_inventory\venv\Scripts\python.exe -X utf8 C:\Users\PC\Desktop\Inventory_bike\abraham_inventory\sync_amis_to_supabase.py

exit /b %ERRORLEVEL%