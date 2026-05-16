import requests
import re
import time
import json
import os
import html
import threading
from datetime import datetime
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
CKEY_API_KEY = os.getenv("CKEY_API_KEY")
CKEY_API_URL = "https://ckey.vn/v1/chat/completions"
CKEY_MODEL = "minimax-m2.5"
ANKI_CONNECT_URL = "http://127.0.0.1:8765"
SEARCH_DECK = "English"              
TARGET_DECK = "English::00_Learning" 
DEFAULT_NOTE_TYPE = "Concrete Words" 
FIELD_WORD = "Word" 
FIELD_IPA = "IPA"   
FIELD_MEANING = "Reference" 
POLL_INTERVAL = 0.2  
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_WORDS_FILE = os.path.join(SCRIPT_DIR, "processed_words.txt")

session = requests.Session() 

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
        response = session.post(ANKI_CONNECT_URL, json=requestJson).json()
        if len(response) != 2 or 'error' not in response or 'result' not in response:
            raise Exception('Invalid response from AnkiConnect.')
        if response['error'] is not None:
            raise Exception(response['error'])
        return response['result']
    except requests.exceptions.ConnectionError:
        return None

def build_ram_cache():
    ram_cache = set()
    query = f'"note:{DEFAULT_NOTE_TYPE}"'
    note_ids = invoke('findNotes', query=query)
    
    if note_ids:
        notes_info = invoke('notesInfo', notes=note_ids)
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
            result = invoke('addNotes', notes=notes)
            
            success_count = 0
            successful_words = []
            
            if result:
                for i, r in enumerate(result):
                    if r is not None:
                        success_count += 1
                        word = imported_words[i]
                        successful_words.append(word)
                        ram_cache.add(word)
                        
            if success_count > 0:
                log_info(f"Imported {success_count} words successfully:")
                print(f"    ↳ {successful_words}")
            else:
                log_info("No new words imported. (Notes rejected as duplicates)")
                
        except Exception as e:
            log_error(f"Anki Import Error: {e}")

def generate_flashcard_data(target_word):
    system_instruction = "You are a speed-optimized vocabulary extractor. Output raw JSON only. Do not wrap in markdown blocks. Ensure all strings are properly quoted with double quotes."
    prompt = f"Target word: {target_word}\nGenerate morphologically and etymologically related words. Provide General American IPA and Vietnamese meaning. Format strictly as a JSON array of arrays: [['word', 'ipa', 'meaning'], ...]"
    
    headers = {
        "Authorization": f"Bearer {CKEY_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": CKEY_MODEL,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 2000
    }
    
    try:
        response = session.post(CKEY_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        
        raw_content = response.json()['choices'][0]['message']['content'].strip()
        
        # Robust JSON extraction: Find the first '[' and last ']'
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
    print(f"\n[{get_timestamp()}] Querying LLM for: '{target_word}'...")
    generated_data = generate_flashcard_data(target_word)
    
    if not generated_data:
        return

    ram_cache.add(target_word.lower())
    
    new_flashcards = [
        item for item in generated_data 
        if item['word'] not in ram_cache
    ]
    
    if new_flashcards:
        add_notes_to_anki(new_flashcards, ram_cache)

def background_monitor():
    processed_session_words = load_processed_words()
    
    if invoke('version') is None:
        log_error("ERROR: Cannot connect to AnkiConnect.")
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

if __name__ == "__main__":
    background_monitor()