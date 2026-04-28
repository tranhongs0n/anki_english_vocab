import requests
from google import genai
from google.genai import types
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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANKI_CONNECT_URL = "http://127.0.0.1:8765"
SEARCH_DECK = "English"              
TARGET_DECK = "English::00_Learning" 
DEFAULT_NOTE_TYPE = "Pronounciation" 
FIELD_WORD = "Word" 
FIELD_IPA = "IPA"   
FIELD_MEANING = "Reference" 
POLL_INTERVAL = 0.2  
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_WORDS_FILE = os.path.join(SCRIPT_DIR, "processed_words.txt")
GIBBERISH_FILE = os.path.join(SCRIPT_DIR, "gibberish.txt")

client = genai.Client(api_key=GEMINI_API_KEY)
session = requests.Session() 

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
    query = '"note:Pronounciation" OR "note:Concrete Words"'
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
        requestJson = {'action': 'addNotes', 'version': 6, 'params': {'notes': notes}}
        try:
            response = session.post(ANKI_CONNECT_URL, json=requestJson).json()
            result = response.get('result', [])
            
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
                print(f"[{get_timestamp()}] Imported {success_count} words successfully:")
                print(f"    ↳ {successful_words}")
            else:
                print(f"[{get_timestamp()}] No new words imported.")
                
        except requests.exceptions.ConnectionError:
            print(f"[{get_timestamp()}] Connection Error during import.")

def generate_flashcard_data(target_word):
    prompt = f"Target word: {target_word}\nGenerate morphologically and etymologically related words. Provide General American IPA and Vietnamese meaning. Format as [['word', 'ipa', 'meaning'], ...]"
    
    try:
        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="You are a speed-optimized vocabulary extractor.",
                response_mime_type="application/json",
                temperature=0.0,
                response_json_schema={
                    "type": "ARRAY",
                    "items": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"}
                    }
                },
                thinking_config=types.ThinkingConfig(thinking_level="MINIMAL")
            )
        )
        data = json.loads(response.text)
        
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
        print(f"[{get_timestamp()}] Error: {e}")
        return []

def get_timestamp():
    return datetime.now().strftime("%H:%M:%S")

def process_target_word(target_word, ram_cache):
    print(f"\n[{get_timestamp()}] Querying Gemini for: '{target_word}'...")
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
        print(f"[{get_timestamp()}] ERROR: Cannot connect to AnkiConnect.")
        return
        
    ram_cache = build_ram_cache()
    ram_cache.update(processed_session_words)
    print(f"[{get_timestamp()}] Cached {len(ram_cache)} existing and filtered words.")
    print(f"[{get_timestamp()}] Monitoring Anki...")
    
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