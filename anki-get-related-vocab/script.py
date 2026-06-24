import requests
import re
import time
import json
import os
import html
import threading
import argparse
import subprocess
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict

# --- CONFIGURATION ---
load_dotenv()
ANKI_CONNECT_URL = os.getenv("ANKI_CONNECT_URL") or "http://127.0.0.1:8765"
SEARCH_DECK = "English"              
TARGET_DECK = "English::00_Learning" 
GIBBERISH_SOURCE_DECK = "English::99_Other" 
DEFAULT_NOTE_TYPE = "Concrete Words" 
FIELD_WORD = "Word" 
FIELD_IPA = "IPA"   
FIELD_MEANING = "Reference" 
POLL_INTERVAL = 0.2  
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_WORDS_FILE = os.path.join(SCRIPT_DIR, "data", "processed_words.txt")
GIBBERISH_FILE = os.path.join(SCRIPT_DIR, "data", "gibberish.txt")

# LLM Provider Configuration
LLM_API_URL = os.getenv("LLM_API_URL") or "https://api.xah.io/v1/chat/completions"
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("CKEY_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL") or "gpt-5.4-mini"

thread_local = threading.local()
ram_cache_lock = threading.Lock()
processed_lock = threading.Lock()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    return thread_local.session

# --- UTILS ---
def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def log_info(message):
    print(f"[{get_timestamp()}] {message}")

def log_error(message):
    print(f"\033[91m[{get_timestamp()}] {message}\033[0m")

def try_repair_json(content, depth=0):
    if depth > 5:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        if "Expecting value" in str(e):
            pos = e.pos
            next_quote = content.find('"', pos)
            if next_quote != -1:
                prefix = content[max(0, pos-5):pos]
                if ',' in prefix or '[' in prefix:
                    repaired = content[:pos] + '"' + content[pos:]
                    return try_repair_json(repaired, depth + 1)
        return None

def invoke(action, **params):
    requestJson = {'action': action, 'version': 6, 'params': params}
    try:
        response = get_session().post(ANKI_CONNECT_URL, json=requestJson).json()
        if not isinstance(response, dict) or 'error' not in response or 'result' not in response:
            raise Exception('Invalid response from AnkiConnect.')
        if response['error'] is not None:
            raise Exception(response['error'])
        return response['result']
    except requests.exceptions.ConnectionError:
        return None

def build_ram_cache():
    ram_cache = set()
    query = f'"{FIELD_WORD}:*"'
    note_ids = invoke('findNotes', query=query)

    if note_ids:
        batch_size = 500
        for i in range(0, len(note_ids), batch_size):
            batch_ids = note_ids[i:i+batch_size]
            notes_info = invoke('notesInfo', notes=batch_ids)
            if not notes_info:
                continue
            for note in notes_info:
                fields = note.get('fields', {})
                if FIELD_WORD in fields:
                    raw_word = fields[FIELD_WORD]['value']
                    decoded_word = html.unescape(raw_word)
                    clean_word = re.sub(r'<[^>]+>', '', decoded_word).strip().lower()
                    if clean_word:
                        ram_cache.add(clean_word)
    return ram_cache

def load_processed_words():
    words = set()
    for file_path in [PROCESSED_WORDS_FILE, GIBBERISH_FILE]:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                words.update(line.strip().lower() for line in f if line.strip())
    return words

def save_processed_word(word):
    with open(PROCESSED_WORDS_FILE, "a", encoding="utf-8") as f:
        f.write(word.strip().lower() + "\n")

def save_processed_word_threadsafe(word, processed_words):
    with processed_lock:
        if word not in processed_words:
            processed_words.add(word)
            save_processed_word(word)

def add_notes_to_anki(flashcard_data_list, ram_cache):
    notes = []
    imported_words = []

    for item in flashcard_data_list:
        note = {
            "deckName": TARGET_DECK,
            "modelName": DEFAULT_NOTE_TYPE,
            "fields": {
                FIELD_WORD: item['word'],
                FIELD_IPA: item['ipa'],
                FIELD_MEANING: item['meaning']
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "collection"
            },
            "tags": ["auto_generated"]
        }
        notes.append(note)
        imported_words.append(item['word'].lower())

    if notes:
        try:
            can_add_results = invoke('canAddNotes', notes=notes)

            filtered_notes = []
            filtered_words = []

            if can_add_results:
                for i, can_add in enumerate(can_add_results):
                    if can_add:
                        filtered_notes.append(notes[i])
                        filtered_words.append(imported_words[i])
                    else:
                        with ram_cache_lock:
                            ram_cache.add(imported_words[i])
            else:
                filtered_notes = notes
                filtered_words = imported_words

            if not filtered_notes:
                log_info("No new words to add (all were duplicates).")
                return

            result = invoke('addNotes', notes=filtered_notes)

            success_count = 0
            successful_words_list = []

            if result:
                for i, r in enumerate(result):
                    if r is not None:
                        success_count += 1
                        word = filtered_words[i]
                        successful_words_list.append(word)
                        with ram_cache_lock:
                            ram_cache.add(word)

            if success_count > 0:
                log_info(f"Imported {success_count} words successfully:")
                print(f"    -> {successful_words_list}")
            else:
                log_info("No new words imported. (Notes rejected as duplicates)")

        except Exception as e:
            log_error(f"Anki Import Error: {e}")

def generate_flashcard_data(target_word):
    prompt = f'Related words for "{target_word}": US IPA, Vietnamese meaning. Format: [["word", "ipa", "meaning"], ...]. Raw JSON only, no markdown.'
    
    if "api/generate" in LLM_API_URL:
        # Local API format
        try:
            response = get_session().post(
                LLM_API_URL,
                data={
                    "prompt": prompt,
                    "model": LLM_MODEL if LLM_MODEL != "gpt-5.4-mini" else "fbb127bbb056c959",
                    "temporary": True
                }
            )
            response.raise_for_status()
            raw_content = response.json()["text"].strip()
        except Exception as e:
            log_error(f"Local LLM API Error: {e}")
            return []
    else:
        # OpenAI compatibility format
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }
        
        try:
            response = get_session().post(
                LLM_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            raw_content = response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            log_error(f"LLM API Error: {e}")
            return []

    try:
        raw_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
        
        start_index = raw_content.find('[')
        end_index = raw_content.rfind(']')
        
        if start_index != -1 and end_index != -1 and end_index > start_index:
            content = raw_content[start_index:end_index+1]
        else:
            content = raw_content

        try:
            data = json.loads(content.strip())
        except json.JSONDecodeError as e:
            data = try_repair_json(content.strip())
            if data is None:
                log_error(f"JSON Decode Error: {e}")
                log_error(f"Raw Content: {raw_content}")
                return []
        
        formatted_data = []
        for item in data:
            if len(item) >= 3:
                formatted_data.append({
                    'word': item[0].strip().lower(),
                    'ipa': item[1],
                    'meaning': item[2]
                })
            
        return formatted_data
    except Exception as e:
        log_error(f"Response processing error: {e}")
        return []

def process_target_word(target_word, ram_cache):
    with ram_cache_lock:
        ram_cache.add(target_word.lower())

    print(f"\n[{get_timestamp()}] Querying LLM for: '{target_word}'...")
    generated_data = generate_flashcard_data(target_word)
    
    if not generated_data:
        return

    with ram_cache_lock:
        new_flashcards = [
            item for item in generated_data 
            if item['word'] not in ram_cache
        ]
        for item in new_flashcards:
            ram_cache.add(item['word'])
    
    if new_flashcards:
        add_notes_to_anki(new_flashcards, ram_cache)

# --- MONITOR MODE ---
def background_monitor():
    processed_session_words = load_processed_words()
    
    if invoke('version') is None:
        log_error("ERROR: Cannot connect to AnkiConnect. Is Anki running?")
        return
        
    ram_cache = build_ram_cache()
    log_info(f"Cached {len(ram_cache)} existing words.")
    log_info("Monitoring Anki...")
    
    try:
        while True:
            try:
                current_card = invoke('guiCurrentCard')
                
                if current_card and 'fields' in current_card:
                    fields = current_card['fields']
                    if FIELD_WORD in fields:
                        raw_word = fields[FIELD_WORD]['value']
                        decoded_word = html.unescape(raw_word)
                        clean_word = re.sub(r'<[^>]+>', '', decoded_word).strip().lower()
                        
                        if clean_word and clean_word not in processed_session_words:
                            processed_session_words.add(clean_word)
                            save_processed_word(clean_word)
                            threading.Thread(target=process_target_word, args=(clean_word, ram_cache)).start()
                            
            except Exception as e:
                if "Gui review is not currently active" not in str(e):
                    pass
            
            time.sleep(POLL_INTERVAL)
            
    except KeyboardInterrupt:
        print(f"\n[{get_timestamp()}] Stopped.")

# --- CLEAN DUPLICATES MODE ---
def clean_duplicates():
    log_info(f"Scanning notes in deck '{SEARCH_DECK}'...")
    
    note_ids = invoke('findNotes', query=f'"deck:{SEARCH_DECK}"')
    if not note_ids:
        log_info("No notes found.")
        return

    log_info(f"Loading info for {len(note_ids)} notes...")
    notes_info = invoke('notesInfo', notes=note_ids)
    if not notes_info:
        log_info("No note details retrieved.")
        return
    
    word_to_notes = defaultdict(list)
    for note in notes_info:
        fields = note.get('fields', {})
        if FIELD_WORD in fields:
            raw_word = fields[FIELD_WORD]['value']
            clean_word = re.sub(r'<[^>]+>', '', raw_word).strip().lower()
            if clean_word:
                word_to_notes[clean_word].append(note)

    notes_to_delete = []

    for word, notes in word_to_notes.items():
        if len(notes) > 1:
            card_id_to_note_id = {}
            for note in notes:
                for card_id in note['cards']:
                    card_id_to_note_id[card_id] = note['noteId']
            
            cards_info = invoke('cardsInfo', cards=list(card_id_to_note_id.keys()))
            if not cards_info:
                continue
            
            note_scores = {}
            for card in cards_info:
                nid = card['note']
                card_type = card.get('type', 0)
                interval = card.get('interval', 0)
                
                score = (card_type, interval)
                
                if nid not in note_scores or score > note_scores[nid]:
                    note_scores[nid] = score
            
            sorted_notes = sorted(note_scores.keys(), key=lambda x: note_scores[x])
            notes_to_delete.extend(sorted_notes[:-1])
            log_info(f"Duplicate detected: '{word}' ({len(notes)} notes) -> Targeting {len(notes)-1} old/low progress notes for deletion.")

    if notes_to_delete:
        log_info(f"Deleting {len(notes_to_delete)} duplicate notes...")
        invoke('deleteNotes', notes=notes_to_delete)
        log_info("Cleanup complete.")
    else:
        log_info("No duplicates found.")

# --- DUMP GIBBERISH MODE ---
def dump_gibberish():
    log_info(f"Fetching words from deck '{GIBBERISH_SOURCE_DECK}'...")
    
    query = f'"deck:{GIBBERISH_SOURCE_DECK}"'
    note_ids = invoke('findNotes', query=query)
    
    if not note_ids:
        log_info(f"No notes found in deck '{GIBBERISH_SOURCE_DECK}'.")
        return

    words = set()
    notes_info = invoke('notesInfo', notes=note_ids)
    
    if notes_info:
        for note in notes_info:
            fields = note.get('fields', {})
            if FIELD_WORD in fields:
                raw_word = fields[FIELD_WORD]['value']
                decoded_word = html.unescape(raw_word)
                clean_word = re.sub(r'<[^>]+>', '', decoded_word).strip().lower()
                if clean_word:
                    words.add(clean_word)

    log_info(f"Found {len(words)} unique words.")

    existing_words = set()
    if os.path.exists(GIBBERISH_FILE):
        with open(GIBBERISH_FILE, "r", encoding="utf-8") as f:
            existing_words = set(line.strip().lower() for line in f if line.strip())
        log_info(f"Loaded {len(existing_words)} existing words from {GIBBERISH_FILE}.")

    all_words = existing_words.union(words)
    
    with open(GIBBERISH_FILE, "w", encoding="utf-8") as f:
        for word in sorted(list(all_words)):
            f.write(word + "\n")

    log_info(f"Successfully wrote {len(all_words)} words to {GIBBERISH_FILE} ({len(all_words) - len(existing_words)} new words).")


# --- END SESSION MODE ---
def run_git_command(args):
    result = subprocess.run(args, capture_output=True, text=True, shell=True)
    return result

def end_session_process():
    log_info("Starting End Session Process...")
    
    # 1. Dump gibberish
    dump_gibberish()
    
    # 2. Delete cards from English::99_Other deck
    log_info(f"Checking for notes in deck '{GIBBERISH_SOURCE_DECK}'...")
    note_ids = invoke('findNotes', query=f'deck:"{GIBBERISH_SOURCE_DECK}"')
    if note_ids:
        log_info(f"Deleting {len(note_ids)} notes from '{GIBBERISH_SOURCE_DECK}'...")
        invoke('deleteNotes', notes=note_ids)
        log_info("Notes deleted successfully from Anki.")
    else:
        log_info("No notes found to delete.")
        
    # 3. Sync Anki
    log_info("Syncing Anki...")
    invoke('sync')
    log_info("Anki sync completed.")
    
    # 4. Push to Git
    log_info("Checking Git status...")
    status_res = run_git_command(["git", "status", "-s"])
    if not status_res.stdout.strip():
        log_info("No Git changes detected. End session complete.")
        return
        
    tag_res = run_git_command(["git", "describe", "--tags", "--abbrev=0"])
    latest_tag = tag_res.stdout.strip()
    
    if not latest_tag:
        new_tag = "v1.0.0"
    else:
        try:
            version_part = latest_tag.lstrip('v')
            major, minor, patch = map(int, version_part.split('.'))
            new_tag = f"v{major}.{minor}.{patch + 1}"
        except Exception:
            new_tag = "v1.0.0"
            
    log_info(f"Determined next Git version: {new_tag}")
    
    run_git_command(["git", "add", "."])
    commit_res = run_git_command(["git", "commit", "-m", f"Release {new_tag}"])
    log_info(commit_res.stdout.strip())
    
    run_git_command(["git", "tag", "-a", new_tag, "-m", f"Automated version update to {new_tag}"])
    
    branch_res = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = branch_res.stdout.strip() or "main"
    
    log_info(f"Pushing to origin {branch} and tag {new_tag}...")
    run_git_command(["git", "push", "origin", branch])
    run_git_command(["git", "push", "origin", new_tag])
    
    log_info("Git push completed.")
    log_info("End Session Complete.")


# --- MAIN ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Anki Vocabulary Tool")
    parser.add_argument("mode", nargs="?", choices=["monitor", "clean", "dump", "end", "endsession"], default="monitor",
                        help="Operation mode: monitor (default), clean (remove duplicates), dump (dump gibberish), end (end session)")
    args = parser.parse_args()

    if args.mode == "monitor":
        background_monitor()
    elif args.mode == "clean":
        clean_duplicates()
    elif args.mode == "dump":
        dump_gibberish()
    elif args.mode in ("end", "endsession"):
        end_session_process()