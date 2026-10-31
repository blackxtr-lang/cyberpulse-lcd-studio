@echo off
chcp 65001 >nul
echo ============================================================================
echo   ⚡ CYBERPULSE STUDIO — YEREL .EXE OLUSTURUCU (H: Diski Onbellekli)
echo ============================================================================
cd /d "%~dp0"

:: H: diski gecici klasorlerini hazirla (C: diski kullanilmaz)
if exist "H:\" (
    if not exist "H:\temp" mkdir "H:\temp"
    if not exist "H:\pip_cache" mkdir "H:\pip_cache"
    if not exist "H:\pyinstaller_work" mkdir "H:\pyinstaller_work"
    set "TEMP=H:\temp"
    set "TMP=H:\temp"
    set "PIP_CACHE_DIR=H:\pip_cache"
    set "WORK_DIR=H:\pyinstaller_work"
) else (
    set "WORK_DIR=%~dp0build_work"
)

set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PYEXE%" set "PYEXE=python.exe"

echo [*] PyInstaller kontrol ediliyor...
"%PYEXE%" -m pip install pyinstaller

echo [*] CyberPulse_Studio.exe derleniyor...
"%PYEXE%" -m PyInstaller --noconfirm --clean --onedir --windowed ^
    --name "CyberPulse_Studio" ^
    --icon "cyberpulse_studio\cyberpulse.ico" ^
    --paths "cyberpulse_studio" ^
    --workpath "%WORK_DIR%" ^
    --distpath "%~dp0dist" ^
    --add-data "cyberpulse_studio\cyberpulse.ico;." ^
    --add-data "cyberpulse_studio\checkmark.png;." ^
    --add-data "cyberpulse_studio\radio_checked.png;." ^
    --hidden-import "i18n" ^
    --hidden-import "case_screen_profiles" ^
    --hidden-import "game_profile_manager" ^
    --hidden-import "hardware_driver" ^
    --hidden-import "sensor_monitor" ^
    --hidden-import "rgb_studio_gui" ^
    "cyberpulse_studio\main_gui.py"

if not exist "%~dp0dist\CyberPulse_Studio\themes" mkdir "%~dp0dist\CyberPulse_Studio\themes"
copy /Y "cyberpulse_studio\cyberpulse.ico" "%~dp0dist\CyberPulse_Studio\" >nul
copy /Y "cyberpulse_studio\checkmark.png" "%~dp0dist\CyberPulse_Studio\" >nul
copy /Y "cyberpulse_studio\radio_checked.png" "%~dp0dist\CyberPulse_Studio\" >nul

echo.
echo [+] TAMAMLANDI! Hazir .exe klasoru: "%~dp0dist\CyberPulse_Studio\CyberPulse_Studio.exe"
pause
