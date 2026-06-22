@echo off
setlocal

echo Starting Gemini WebAPI REST Server...
start "Gemini API Server" /min cmd /c "cd /d D:\Software\gemini-api && python -m uvicorn app:app --host 127.0.0.1 --port 8000"

echo Waiting for API server to boot (3s)...
ping -n 4 127.0.0.1 >nul

if "%1"=="batch" (
    echo Starting Batch Vocabulary Extractor Script...
    python "%~dp0batch_script.py"
) else (
    echo Starting Vocabulary Extractor Script...
    python "%~dp0script.py"
)

echo Cleaning up API server...
taskkill /fi "windowtitle eq Gemini API Server*" /f /t >nul 2>&1

echo Done.
