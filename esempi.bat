@echo off
chcp 65001 >nul
rem Rifa' l'analisi sul set fisso di paper (esempi\set_fisso.yaml).
rem Usa una richiesta al modello per ogni paper. Risultati in esempi\output.
cd /d "%~dp0"
call scripts\ambiente.bat
if errorlevel 1 (
    pause
    exit /b 1
)
"%PYTHON%" -u scripts\rianalizza_set_fisso.py %* > dati\esempi.log 2>&1
type dati\esempi.log
pause
