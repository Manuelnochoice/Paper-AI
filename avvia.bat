@echo off
chcp 65001 >nul
rem Avvia Paper Radar su Windows con un doppio clic.
cd /d "%~dp0"
call scripts\ambiente.bat
if errorlevel 1 (
    pause
    exit /b 1
)
if not exist ".env" echo ATTENZIONE: manca il file .env con le chiavi API. Vedi README.md.

echo Avvio Paper Radar su http://localhost:8501 - chiudi questa finestra per fermarlo.
start "" cmd /c "timeout /t 6 >nul & start http://localhost:8501"
"%PYTHON%" -m streamlit run app.py --server.headless true
