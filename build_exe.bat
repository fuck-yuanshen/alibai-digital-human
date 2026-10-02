@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=C:\Users\14931\AppData\Local\Programs\Python\Python310\python.exe"
if not exist "%PYTHON%" set "PYTHON=py -3.10"

echo Building Alibai desktop application...
%PYTHON% -m PyInstaller --noconfirm --clean --onedir --windowed ^
  --name Alibai ^
  --add-data "static;static" ^
  --add-data "data\wav2lip_avatar_wzj2cjl\full_imgs\00000000.png;data\wav2lip_avatar_wzj2cjl\full_imgs" ^
  --add-data "config.yml;." ^
  --add-data ".env.example;." ^
  --exclude-module torch ^
  --exclude-module torchvision ^
  --exclude-module torchaudio ^
  --exclude-module tensorflow ^
  --exclude-module pandas ^
  --exclude-module matplotlib ^
  --exclude-module IPython ^
  --exclude-module jupyter ^
  --exclude-module notebook ^
  --exclude-module PyQt5 ^
  --exclude-module PyQt6 ^
  --exclude-module tkinter ^
  launcher.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

copy /Y "settings.json" "dist\Alibai\settings.json" >nul
if errorlevel 1 (
  echo Failed to copy settings.json.
  exit /b 1
)

if exist ".env" (
  copy /Y ".env" "dist\Alibai\.env" >nul
  if errorlevel 1 (
    echo Failed to copy .env.
    exit /b 1
  )
) else (
  echo Warning: .env was not found. LLM and TTS require API keys beside Alibai.exe.
)

echo Build complete: dist\Alibai\Alibai.exe
endlocal
