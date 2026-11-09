@echo off
rem Double-click to start the Dragonwilds helper. Keep this window open while playing; errors show here.
cd /d "%~dp0"
".venv\Scripts\python.exe" helper.py
if errorlevel 1 pause
