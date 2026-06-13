import requests
import re
import time
import json
import os
import html
import threading
import random
from datetime import datetime
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

# --- CONFIGURATION ---
load_dotenv()
ANKI_CONNECT_URL = "http://127.0.0.1:8765"
SEARCH_DECK = "English"              
TARGET_DECK = "English::00_Learning" 
DEFAULT_NOTE_TYPE = "Concrete Words" 
FIELD_WORD = "Word" 
FIELD_IPA = "IPA"   
FIELD_MEANING = "Reference" 
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_WORDS_FILE = os.path.join(SCRIPT_DIR, "processed_words.txt")
GIBBERISH_FILE = os.path.join(SCRIPT_DIR, "gibberish.txt")

# LLM Provider Configuration
LLM_API_URL = "https://api.xah.io/v1/chat/completions"
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("CKEY_API_KEY")
LLM_MODEL = "gpt-5.4-mini"

thread_local = threading.local()

def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
    return thread_local.session

ram_cache_lock = threading.Lock()
processed_lock = threading.Lock()

def save_processed_word_threadsafe(word, processed_words):
    with processed_lock:
        if word not in processed_words:
            processed_words.add(word)
            save_processed_word(word)

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
                print(f"    ↳ {successful_words_list}")
            else:
                log_info("No new words imported. (Notes rejected as duplicates)")

        except Exception as e:
            log_error(f"Anki Import Error: {e}")

def generate_flashcard_data(target_word):
    prompt = f'Related words for "{target_word}": US IPA, Vietnamese meaning. Format: [["word", "ipa", "meaning"], ...]. Raw JSON only, no markdown.'
    
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
        
        # Strip any reasoning block if returned anyway
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
        if not isinstance(e, json.JSONDecodeError):
            log_error(f"LLM API Error: {e}")
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

def get_all_words_to_process():
    query = f'deck:"{SEARCH_DECK}"'
    note_ids = invoke('findNotes', query=query)
    words = []
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
                    if clean_word and clean_word not in words:
                        words.append(clean_word)
    return words

def worker(word, ram_cache, processed_words, counter, total_count):
    try:
        # Short sleep to stagger thread start slightly
        time.sleep(random.uniform(0.05, 0.2))
        
        # Increment counter thread-safely
        with processed_lock:
            counter[0] += 1
            current_num = counter[0]
            
        log_info(f"[{current_num}/{total_count}] Processing target word: '{word}'...")
        process_target_word(word, ram_cache)
        save_processed_word_threadsafe(word, processed_words)
    except Exception as e:
        log_error(f"Error processing '{word}': {e}")

def batch_process():
    if invoke('version') is None:
        log_error("ERROR: Cannot connect to AnkiConnect. Is Anki running?")
        return
        
    ram_cache = build_ram_cache()
    log_info(f"Cached {len(ram_cache)} existing words in Anki.")
    
    processed_words = load_processed_words()
    log_info(f"Loaded {len(processed_words)} already processed words from files.")
    
    words_to_process = get_all_words_to_process()
    log_info(f"Found {len(words_to_process)} target words in deck '{SEARCH_DECK}'.")
    
    # Filter to process list
    to_do = [w for w in words_to_process if w not in processed_words]
    total_to_do = len(to_do)
    log_info(f"Need to process {total_to_do} new words.")
    
    if total_to_do == 0:
        log_info("All words already processed. Exiting.")
        return
        
    counter = [0]
    
    log_info("Starting multi-threaded execution (10 threads concurrently)...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(worker, word, ram_cache, processed_words, counter, total_to_do)
            for word in to_do
        ]
        
        # Wait for all threads to complete
        for future in futures:
            try:
                future.result()
            except Exception as e:
                log_error(f"Thread execution failed: {e}")
                
    log_info(f"Batch processing completed. Processed {total_to_do} new words.")

if __name__ == "__main__":
    batch_process()
