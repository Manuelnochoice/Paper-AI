@echo off
chcp 65001 >nul
rem Controlla che tutto funzioni: test automatici, chiavi, fonti e grafo con dati reali.
rem Il risultato viene mostrato e salvato in dati\verifica.log. Non usa quota del modello.
cd /d "%~dp0"
call scripts\ambiente.bat
if errorlevel 1 (
    pause
    exit /b 1
)
echo Eseguo i controlli, serve circa un minuto...
"%PYTHON%" -m pytest -q > dati\verifica.log 2>&1
"%PYTHON%" -u scripts\verifica_configurazione.py >> dati\verifica.log 2>&1
type dati\verifica.log
pause
