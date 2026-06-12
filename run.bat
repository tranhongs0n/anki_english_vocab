@echo off
echo Starting Gemini WebAPI REST Server...
start "Gemini API Server" /d "D:\Software\gemini-api" python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload

echo Waiting for API server to boot...
timeout /t 3 /nobreak >nul

echo Starting Vocabulary Extractor Script...
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
) else if exist "%~dp0venv\bin\activate.bat" (
    call "%~dp0venv\bin\activate.bat"
)

python "%~dp0script.py"
pause
