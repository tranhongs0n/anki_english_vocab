@echo off
setlocal enabledelayedexpansion

set CMD=%1
if not "%CMD%"=="" goto parse_arg

:menu
set LLM_PROVIDER=xah
if exist "%~dp0anki-get-related-vocab\.env" (
    for /f "usebackq tokens=1,2 delims==" %%i in ("%~dp0anki-get-related-vocab\.env") do (
        if "%%i"=="LLM_PROVIDER" set LLM_PROVIDER=%%j
    )
)

cls
echo ==================================================
echo             Anki Vocabulary Suite Launcher
echo ==================================================
echo [1] Start All Services (API + Crawler + Vocab)
echo [2] Run End Session Sync and Push to GitHub
echo [3] Clean Duplicate Vocabulary Cards
echo [4] Change LLM Provider (Current: !LLM_PROVIDER!)
echo [5] Exit
echo ==================================================
set /p opt="Choose option (1-5): "
if "%opt%"=="1" goto run_all_services
if "%opt%"=="2" (
    set CMD=end
    goto parse_arg
)
if "%opt%"=="3" (
    set CMD=clean
    goto parse_arg
)
if "%opt%"=="4" goto change_provider
if "%opt%"=="5" exit /b
if "!CMD!"=="" goto menu

:change_provider
cls
echo ==================================================
echo             Select LLM Provider
echo ==================================================
echo [1] Local Gemini API (gemini-api)
echo [2] Google AI Studio (aistudio)
echo [3] xah.io (ckey.vn)
echo [4] Back to Menu
echo ==================================================
set /p prov_opt="Choose option (1-4): "
if "%prov_opt%"=="1" (
    python -c "import os; path = r'%~dp0anki-get-related-vocab\.env'; content = open(path).read() if os.path.exists(path) else ''; new_content = '\n'.join([l for l in content.splitlines() if not l.startswith('LLM_PROVIDER=')]) + '\nLLM_PROVIDER=local\n'; open(path, 'w').write(new_content.strip() + '\n')"
    echo Provider set to 'local'
    pause
)
if "%prov_opt%"=="2" (
    python -c "import os; path = r'%~dp0anki-get-related-vocab\.env'; content = open(path).read() if os.path.exists(path) else ''; new_content = '\n'.join([l for l in content.splitlines() if not l.startswith('LLM_PROVIDER=')]) + '\nLLM_PROVIDER=google\n'; open(path, 'w').write(new_content.strip() + '\n')"
    echo Provider set to 'google'
    pause
)
if "%prov_opt%"=="3" (
    python -c "import os; path = r'%~dp0anki-get-related-vocab\.env'; content = open(path).read() if os.path.exists(path) else ''; new_content = '\n'.join([l for l in content.splitlines() if not l.startswith('LLM_PROVIDER=')]) + '\nLLM_PROVIDER=xah\n'; open(path, 'w').write(new_content.strip() + '\n')"
    echo Provider set to 'xah'
    pause
)
goto menu

:parse_arg
if "%CMD%"=="monitor" (
    goto run_all_services
)
if "%CMD%"=="end" (
    echo Running End Session Sync...
    if exist "%~dp0anki-get-related-vocab\venv\Scripts\activate.bat" (
        call "%~dp0anki-get-related-vocab\venv\Scripts\activate.bat"
    )
    python "%~dp0anki-get-related-vocab\script.py" end
    goto end_arg
)
if "%CMD%"=="clean" (
    echo Cleaning Duplicates...
    if exist "%~dp0anki-get-related-vocab\venv\Scripts\activate.bat" (
        call "%~dp0anki-get-related-vocab\venv\Scripts\activate.bat"
    )
    python "%~dp0anki-get-related-vocab\script.py" clean
    goto end_arg
)
echo Unknown command: %CMD%
echo Valid commands: monitor, end, clean
pause
goto end_arg

:run_all_services
echo Starting Gemini API Server...
start "Gemini API Server" /min cmd /c "cd /d "%~dp0gemini-api" && set PYTHONPATH=src && python -m uvicorn app:app --host 127.0.0.1 --port 8000"

echo Starting Google Image Crawler...
start "Google Image Crawler" /min cmd /c "cd /d "%~dp0crawl-google-image" && npm start"

echo Waiting for servers to boot (3s)...
ping -n 4 127.0.0.1 >nul

echo ==================================================
echo Local Host URLs for access:
echo Gemini API:     http://localhost:8000
echo Image Crawler:  http://localhost:3000
echo ==================================================

echo Starting Vocabulary Tool in monitor mode...
if exist "%~dp0anki-get-related-vocab\venv\Scripts\activate.bat" (
    call "%~dp0anki-get-related-vocab\venv\Scripts\activate.bat"
)
python "%~dp0anki-get-related-vocab\script.py" monitor

echo Cleaning up servers...
taskkill /fi "windowtitle eq Gemini API Server*" /f /t >nul 2>&1
taskkill /fi "windowtitle eq Google Image Crawler*" /f /t >nul 2>&1

:end_arg
if "%1"=="" (
    set CMD=
    pause
    goto menu
)
