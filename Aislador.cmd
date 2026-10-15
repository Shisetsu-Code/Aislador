@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
  py -3 -m aislador gui
) else (
  python -m aislador gui
)
if errorlevel 1 pause
