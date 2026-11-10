@echo off
cd /d "%~dp0"
python tools\make_icon.py
python -m PyInstaller --noconfirm --clean --windowed --onedir --name PdfDesk --icon icon.ico --add-data "icon.ico;." ^
  --exclude-module tkinter --exclude-module numpy --exclude-module PIL --exclude-module pandas ^
  --exclude-module matplotlib --exclude-module scipy --exclude-module IPython --exclude-module pytest ^
  main.py
