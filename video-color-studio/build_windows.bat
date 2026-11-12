@echo off
setlocal
cd /d "%~dp0.."
py -3.11 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
if exist dist rmdir /s /q dist
pyinstaller --noconfirm --clean --windowed --name "KHIETTRAN Video Color Studio" --collect-all PySide6 app.py
if exist runtime\ffmpeg xcopy /E /I /Y runtime\ffmpeg "dist\KHIETTRAN Video Color Studio\runtime\ffmpeg"
echo Build output: dist\KHIETTRAN Video Color Studio\KHIETTRAN Video Color Studio.exe
