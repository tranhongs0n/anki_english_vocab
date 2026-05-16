@echo off
setlocal

echo --- Dumping 99_Other words ---
python dump_gibberish.py

echo --- Deleting cards from English::99_Other deck ---
python -c "import requests; ANKI_CONNECT_URL = 'http://127.0.0.1:8765'; r = requests.post(ANKI_CONNECT_URL, json={'action': 'findNotes', 'version': 6, 'params': {'query': 'deck:English::99_Other'}}).json(); note_ids = r.get('result', []); [print(f'Deleting {len(note_ids)} notes...'), print('Notes deleted successfully.' if not requests.post(ANKI_CONNECT_URL, json={'action': 'deleteNotes', 'version': 6, 'params': {'notes': note_ids}}).json().get('error') else 'Error deleting notes')] if note_ids else print('No notes found to delete.')"

echo --- Syncing Anki ---
python -c "import requests; requests.post('http://127.0.0.1:8765', json={'action': 'sync', 'version': 6})"

echo --- Pushing changes to GitHub ---
:: Check for Git Bash specifically to avoid WSL stub
if exist "%ProgramFiles%\Git\bin\bash.exe" (
    "%ProgramFiles%\Git\bin\bash.exe" push.sh
) else if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" (
    "%ProgramFiles(x86)%\Git\bin\bash.exe" push.sh
) else (
    where bash >nul 2>nul
    if %ERRORLEVEL% EQU 0 (
        :: Try bash but check if it's the WSL one
        bash -c "exit" 2>nul
        if %ERRORLEVEL% EQU 0 (
            bash push.sh
        ) else (
            echo Error: Found 'bash' but it seems to be an unconfigured WSL stub.
            echo Please run 'endsession.sh' from Git Bash instead.
            exit /b 1
        )
    ) else (
        echo Error: Bash not found. Please run 'endsession.sh' from Git Bash.
        exit /b 1
    )
)

echo --- End Session Complete ---
pause
