import requests
from collections import defaultdict
import re

# --- CONFIGURATION ---
ANKI_CONNECT_URL = "http://localhost:8765"
DECK_NAME = "English"
FIELD_WORD = "Word"

def invoke(action, **params):
    requestJson = {'action': action, 'version': 6, 'params': params}
    try:
        response = requests.post(ANKI_CONNECT_URL, json=requestJson).json()
        if len(response) != 2 or 'error' not in response or 'result' not in response:
            raise Exception('Invalid response from AnkiConnect.')
        if response['error'] is not None:
            raise Exception(response['error'])
        return response['result']
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to AnkiConnect.")
        return None

def clean_duplicates():
    print(f"Scanning notes in deck '{DECK_NAME}'...")
    
    note_ids = invoke('findNotes', query=f'"deck:{DECK_NAME}"')
    if not note_ids:
        print("No notes found.")
        return

    print(f"Loading info for {len(note_ids)} notes...")
    notes_info = invoke('notesInfo', notes=note_ids)
    
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
            
            note_scores = {}
            for card in cards_info:
                nid = card['note']
                # Safely get 'type' and 'interval', defaulting to 0 if missing
                card_type = card.get('type', 0)
                interval = card.get('interval', 0)
                
                score = (card_type, interval)
                
                if nid not in note_scores or score > note_scores[nid]:
                    note_scores[nid] = score
            
            sorted_notes = sorted(note_scores.keys(), key=lambda x: note_scores[x])
            
            notes_to_delete.extend(sorted_notes[:-1])
            
            print(f"Duplicate detected: '{word}' ({len(notes)} notes) -> Targeting {len(notes)-1} old/low progress notes for deletion.")

    if notes_to_delete:
        print(f"Deleting {len(notes_to_delete)} duplicate notes...")
        invoke('deleteNotes', notes=notes_to_delete)
        print("Cleanup complete.")
    else:
        print("No duplicates found.")

if __name__ == "__main__":
    clean_duplicates()