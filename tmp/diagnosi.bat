@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
echo == venv == > diagnosi.log
"%LOCALAPPDATA%\PaperRadar\venv\Scripts\python.exe" -u diagnosi.py >> diagnosi.log 2>&1
echo == globale == >> diagnosi.log
python -u diagnosi.py >> diagnosi.log 2>&1
echo == fine == >> diagnosi.log
