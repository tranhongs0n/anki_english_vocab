@echo off
setlocal enabledelayedexpansion

:: Activate virtual environment
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
)

:: Parse arguments
set MODE=%1
if "%MODE%"=="" set MODE=monitor

:: Start Gemini API server if running monitor or batch
set START_SERVER=0
if "%MODE%"=="monitor" set START_SERVER=1
if "%MODE%"=="batch" set START_SERVER=1

if %START_SERVER%==1 (
    if exist "%~dp0..\gemini-api" (
        echo Starting Gemini WebAPI REST Server...
        start "Gemini API Server" /min cmd /c "cd /d "%~dp0..\gemini-api" && python -m uvicorn app:app --host 127.0.0.1 --port 8000"
        echo Waiting for API server to boot (3s)...
        ping -n 4 127.0.0.1 >nul
    )
)

:: Run Python script
echo Running Vocabulary Tool in '%MODE%' mode...
python "%~dp0script.py" %MODE%

:: Clean up Gemini API server if started
if %START_SERVER%==1 (
    if exist "%~dp0..\gemini-api" (
        echo Cleaning up API server...
        taskkill /fi "windowtitle eq Gemini API Server*" /f /t >nul 2>&1
    )
)

echo Done.
