@echo off
:: Check if the environment exists
if not exist "venv" (
    echo Virtual environment not found!
    echo Please run 'install_dependencies.bat' first.
    pause
    exit /b
)

:: Activate environment and run script
call venv\Scripts\activate
python video_gui.py

:: Keep window open if it crashes
if %errorlevel% neq 0 pause