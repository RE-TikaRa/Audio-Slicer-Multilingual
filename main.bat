@echo off
setlocal
cd /d "%~dp0"
uv run python scripts\slicer-gui.py
pause