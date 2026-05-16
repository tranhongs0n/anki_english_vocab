import requests
import json
import os
import re
import html
from datetime import datetime

# --- CONFIGURATION ---
ANKI_CONNECT_URL = "http://127.0.0.1:8765"
SOURCE_DECK = "English::99_Other"
FIELD_WORD = "Word"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
GIBBERISH_FILE = os.path.join(SCRIPT_DIR, "gibberish.txt")

session = requests.Session()

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log_info(message):
    print(f"[{get_timestamp()}] {message}")

def log_error(message):
    print(f"\033[91m[{get_timestamp()}] {message}\033[0m")

def invoke(action, **params):
    requestJson = {'action': action, 'version': 6, 'params': params}
    try:
        response = session.post(ANKI_CONNECT_URL, json=requestJson).json()
        if len(response) != 2 or 'error' not in response or 'result' not in response:
            raise Exception('Invalid response from AnkiConnect.')
        if response['error'] is not None:
            raise Exception(response['error'])
        return response['result']
    except requests.exceptions.ConnectionError:
        log_error("Failed to connect to AnkiConnect. Is Anki running?")
        return None
    except Exception as e:
        log_error(f"Error: {e}")
        return None

def dump_gibberish():
    log_info(f"Fetching words from deck '{SOURCE_DECK}'...")
    
    query = f'"deck:{SOURCE_DECK}"'
    note_ids = invoke('findNotes', query=query)
    
    if not note_ids:
        log_info(f"No notes found in deck '{SOURCE_DECK}'.")
        return

    words = set()
    notes_info = invoke('notesInfo', notes=note_ids)
    
    if notes_info:
        for note in notes_info:
            fields = note.get('fields', {})
            if FIELD_WORD in fields:
                raw_word = fields[FIELD_WORD]['value']
                decoded_word = html.unescape(raw_word)
                # Strip HTML tags
                clean_word = re.sub(r'<[^>]+>', '', decoded_word).strip().lower()
                if clean_word:
                    words.add(clean_word)

    log_info(f"Found {len(words)} unique words.")

    # Load existing words from gibberish.txt
    existing_words = set()
    if os.path.exists(GIBBERISH_FILE):
        with open(GIBBERISH_FILE, "r", encoding="utf-8") as f:
            existing_words = set(line.strip().lower() for line in f if line.strip())
        log_info(f"Loaded {len(existing_words)} existing words from {GIBBERISH_FILE}.")

    # Merge
    all_words = existing_words.union(words)
    
    # Write back
    with open(GIBBERISH_FILE, "w", encoding="utf-8") as f:
        for word in sorted(list(all_words)):
            f.write(word + "\n")

    log_info(f"Successfully wrote {len(all_words)} words to {GIBBERISH_FILE} ({len(all_words) - len(existing_words)} new words).")

if __name__ == "__main__":
    dump_gibberish()
