@echo off
rem Prepara l'ambiente Python (usato da avvia.bat, verifica.bat ed esempi.bat).
rem L'ambiente virtuale sta fuori dalla cartella del progetto, cosi' OneDrive
rem non deve sincronizzare migliaia di file.

set "AMBIENTE=%LOCALAPPDATA%\PaperRadar\venv"
set "PYTHON=%AMBIENTE%\Scripts\python.exe"
set "PYTHONUTF8=1"

rem Windows nasconde le estensioni: un file creato come ".env" spesso si chiama ".env.txt".
if exist ".env.txt" if not exist ".env" ren ".env.txt" ".env"

if exist "%PYTHON%" goto pronto
echo Prima installazione: creo l'ambiente e installo le librerie, serve qualche minuto...
python -m venv "%AMBIENTE%"
if errorlevel 1 goto errore
"%PYTHON%" -m pip install --upgrade pip
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto errore

:pronto
rem Se requirements.txt e' cambiato dall'ultima installazione, aggiorna le librerie.
fc /b requirements.txt "%AMBIENTE%\requirements.installati.txt" >nul 2>&1
if not errorlevel 1 exit /b 0
echo Aggiorno le librerie...
"%PYTHON%" -m pip install -q -r requirements.txt
if errorlevel 1 goto errore
copy /y requirements.txt "%AMBIENTE%\requirements.installati.txt" >nul
exit /b 0

:errore
echo.
echo Installazione non riuscita. Controlla che Python 3.10 o successivo sia installato
echo e aggiunto al PATH, poi riprova.
exit /b 1
