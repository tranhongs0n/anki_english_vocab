#!/bin/bash

# Ensure we are in the project root
cd "$(dirname "$0")"

# 1. Dump 99_Other words to gibberish.txt
echo "--- Dumping 99_Other words ---"
python dump_gibberish.py

# 2. Delete all cards in 99_Other deck
echo "--- Deleting cards from 99_Other deck ---"
python -c "import requests; ANKI_CONNECT_URL = 'http://127.0.0.1:8765'; r = requests.post(ANKI_CONNECT_URL, json={'action': 'findNotes', 'version': 6, 'params': {'query': 'deck:English::99_Other'}}).json(); note_ids = r.get('result', []); [print(f'Deleting {len(note_ids)} notes...'), print('Notes deleted successfully.' if not requests.post(ANKI_CONNECT_URL, json={'action': 'deleteNotes', 'version': 6, 'params': {'notes': note_ids}}).json().get('error') else 'Error deleting notes')] if note_ids else print('No notes found to delete.')"

# 3. Push to GitHub
echo "--- Pushing changes to GitHub ---"
if [[ -f "./push.sh" ]]; then
    chmod +x ./push.sh
    ./push.sh
else
    echo "Error: push.sh not found!"
    exit 1
fi

echo "--- End Session Complete ---"
