@echo off

echo Starting Batch Vocabulary Extractor Script...
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
) else if exist "%~dp0venv\bin\activate.bat" (
    call "%~dp0venv\bin\activate.bat"
)

python "%~dp0batch_script.py"
pause
