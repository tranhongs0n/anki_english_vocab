@echo off
rem Activate the virtual environment and run the script
if exist "%~dp0venv\Scripts\activate.bat" (
    call "%~dp0venv\Scripts\activate.bat"
) else if exist "%~dp0venv\bin\activate.bat" (
    call "%~dp0venv\bin\activate.bat"
)

python script.py
