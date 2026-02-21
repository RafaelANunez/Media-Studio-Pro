@echo off
setlocal

:: Define the virtual environment folder name
set "VENV_NAME=venv"

echo ==========================================
echo      Video App Auto-Installer
echo ==========================================

:: 1. Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is NOT installed.
    echo Please install Python from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b
)

:: 2. Create Virtual Environment if it doesn't exist
if not exist "%VENV_NAME%" (
    echo [INFO] Creating virtual environment...
    python -m venv %VENV_NAME%
) else (
    echo [INFO] Virtual environment found.
)

:: 3. Activate Virtual Environment
call %VENV_NAME%\Scripts\activate

:: 4. Upgrade pip
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

:: 5. Install Required Libraries
echo [INFO] Installing Python dependencies...
:: Note: 'tkinterdnd2' is needed for Drag & Drop. 
:: 'python-vlc' is needed for the VLC backend.
:: 'moviepy' is upgraded to ensure support for v2.0+ methods like .resized()
pip install --upgrade customtkinter moviepy Pillow proglog python-vlc tkinterdnd2

echo.
echo ==========================================
echo      Checking External Tools
echo ==========================================

:: 6. Check for FFmpeg (Required for Fast Backend)
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] FFmpeg is NOT found in your system PATH.
    echo The app will work, but "Fast Mode" resizing/trimming will be disabled.
    echo.
    echo Attempting to install FFmpeg via Winget...
    winget install -e --id Gyan.FFmpeg
    if %errorlevel% neq 0 (
        echo [MANUAL ACTION NEEDED] Winget failed or is not installed.
        echo Please download FFmpeg from: https://ffmpeg.org/download.html
        echo and add it to your System Environment PATH.
    ) else (
        echo [SUCCESS] FFmpeg installed! Please restart your terminal.
    )
) else (
    echo [OK] FFmpeg is installed.
)

echo.
:: 7. Check for AI Upscaler (Required for 'Rocket' Tool)
if not exist "realesrgan-ncnn-vulkan.exe" (
    echo [WARNING] AI Upscaler executable not found.
    echo To use the AI Upscaling feature:
    echo   1. Go to: https://github.com/xinntao/Real-ESRGAN/releases
    echo   2. Download "realesrgan-ncnn-vulkan-20220424-windows.zip"
    echo   3. Extract "realesrgan-ncnn-vulkan.exe" into this folder.
) else (
    echo [OK] AI Upscaler found.
)

echo.
:: 8. Check for RIFE Interpolator (Required for 'Smooth/FPS' Tool)
if not exist "rife-ncnn-vulkan.exe" (
    echo [WARNING] RIFE executable not found.
    echo To use the AI Frame Interpolation feature:
    echo   1. Go to: https://github.com/nihui/rife-ncnn-vulkan/releases
    echo   2. Download the latest windows zip.
    echo   3. Extract "rife-ncnn-vulkan.exe" into this folder.
) else (
    echo [OK] RIFE Interpolator found.
)

echo.
echo ==========================================
echo [SUCCESS] Installation checks complete!
echo ==========================================
echo You can now use 'run_app.bat' to start the application.
pause