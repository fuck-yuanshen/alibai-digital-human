@echo off
title Digital Human Server - alibai

rem ================= settings =================
rem Python with all dependencies installed
set "PYTHON=C:\Users\14931\AppData\Local\Programs\Python\Python310\python.exe"
set "PORT=8010"
rem ============================================

rem project dir = directory of this bat file
cd /d "%~dp0"
if not exist "main.py" (
    echo [ERROR] main.py not found in %CD%
    echo Keep start.bat inside the project folder.
    pause
    exit /b 1
)

if "%DEEPSEEK_API_KEY%"=="" if not exist ".env" (
    echo [WARNING] DEEPSEEK_API_KEY is not set. Digital-human chat replies will fail until it is configured.
    echo [INFO] Configure DEEPSEEK_API_KEY in .env or in the system environment.
)

if exist "%PYTHON%" (
    set "RUN=%PYTHON% main.py"
) else (
    set "RUN=py -3.10 main.py"
)

rem if server is already running, just open the page
curl -s -o nul "http://127.0.0.1:%PORT%/index.html" 2>nul
if not errorlevel 1 (
    echo [INFO] Server already running, opening page...
    start "" "http://127.0.0.1:%PORT%/index.html"
    timeout /t 3 /nobreak >nul
    exit /b 0
)

echo ==================================================
echo   Digital Human Server (Wav2Lip WebRTC)  port %PORT%
echo   CPU mode startup takes about 40-60 seconds
echo   Browser will open automatically when ready:
echo   http://127.0.0.1:%PORT%/index.html
echo   Close this window to stop the server.
echo ==================================================
echo.

rem hidden helper: open browser once server is ready
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++){try{$r=Invoke-WebRequest -Uri 'http://127.0.0.1:%PORT%/index.html' -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop;if($r.StatusCode -eq 200){Start-Process 'http://127.0.0.1:%PORT%/index.html';exit}}catch{};Start-Sleep 2}"

%RUN%

echo.
echo [INFO] Server exited. If there are errors above, screenshot them.
pause
