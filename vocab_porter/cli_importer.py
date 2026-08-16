import sys
import re
import html as html_mod
import urllib.request
import json
import argparse
import os
import fitz  # PyMuPDF

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
TARGET_DECK = "English::toeic"
PARENT_DECK_QUERY = "deck:English"
MODEL_NAME = "Concrete Words"

GIBBERISH_FILE = r"D:\Projects\Anki_Vocab_Suite\data\gibberish.txt"

# Only pure-alpha stopwords kept — contractions like "aren't" can never match
# the \b[a-zA-Z]{3,}\b regex, so they were dead code.
STOPWORDS = {
    "about", "above", "after", "again", "against", "all", "and", "any", "are",
    "been", "before", "being", "below", "between", "both", "but",
    "can", "cannot", "could", "did", "does", "doing", "down", "during",
    "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "her", "here", "hers", "herself", "him",
    "himself", "his", "how",
    "into", "its", "itself",
    "more", "most", "myself",
    "nor", "not", "off", "once", "only", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own",
    "same", "she", "should", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these",
    "they", "this", "those", "through", "too", "under", "until",
    "very", "was", "were", "what", "whatever", "when", "where", "which",
    "while", "who", "whom", "why", "with", "would", "you", "your", "yours",
    "yourself", "yourselves",
}


def load_gibberish_words():
    """Load gibberish word list once. Returns a frozenset for immutable reuse."""
    words = set()
    if os.path.exists(GIBBERISH_FILE):
        try:
            with open(GIBBERISH_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w:
                        words.add(w)
            print(f"[+] Loaded {len(words)} gibberish words from '{GIBBERISH_FILE}'.")
        except Exception as e:
            print(f"[!] Warning reading gibberish file: {e}")
    else:
        print("[!] Gibberish file not found, skipping gibberish filtering.")
    return frozenset(words)


def call_anki(action, **params):
    """Call AnkiConnect API. Raises RuntimeError on failure instead of sys.exit."""
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_CONNECT_URL, payload)
    try:
        response = urllib.request.urlopen(req)
        res_data = json.loads(response.read().decode("utf-8"))
        if res_data.get("error"):
            raise RuntimeError(f"AnkiConnect Error ({action}): {res_data['error']}")
        return res_data["result"]
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"AnkiConnect API ({action}): {e}") from e


def call_anki_safe(action, **params):
    """Non-fatal wrapper — returns (result, error_str). Never raises."""
    try:
        return call_anki(action, **params), None
    except RuntimeError as e:
        return None, str(e)


def ensure_target_deck():
    print(f"[*] Ensuring deck '{TARGET_DECK}' exists...")
    call_anki("createDeck", deck=TARGET_DECK)
    print(f"[+] Deck '{TARGET_DECK}' ready.")


def get_existing_word_map():
    print(f"[*] Querying existing notes in parent deck ({PARENT_DECK_QUERY})...")
    note_ids = call_anki("findNotes", query=PARENT_DECK_QUERY)
    print(f"[+] Found {len(note_ids)} total notes in parent deck.")

    word_to_note = {}
    chunk_size = 1000
    for i in range(0, len(note_ids), chunk_size):
        chunk = note_ids[i:i + chunk_size]
        notes_info = call_anki("notesInfo", notes=chunk)
        for note in notes_info:
            fields = note.get("fields", {})
            for field_name in ["Word", "Front"]:
                if field_name in fields:
                    raw_val = fields[field_name].get("value", "")
                    # Align with addon: html.unescape + strip tags
                    val = re.sub(r"<[^>]+>", "", html_mod.unescape(raw_val)).strip().lower()
                    if val:
                        word_to_note[val] = note

    print(f"[+] Indexed {len(word_to_note)} unique words from existing notes.")
    return word_to_note


def extract_pdf_data(pdf_path, gibberish_set, max_pages=None):
    print(f"[*] Reading PDF: {pdf_path}")

    with fitz.open(pdf_path) as doc:
        total_pages = len(doc)
        pages_to_read = total_pages if not max_pages else min(max_pages, total_pages)
        print(f"[*] Processing {pages_to_read} of {total_pages} total pages...")

        full_text_list = [doc[i].get_text() for i in range(pages_to_read)]

    raw_text = " ".join(full_text_list)
    clean_text = re.sub(r"\s+", " ", raw_text)

    raw_sentences = re.split(r"(?<=[.!?])\s+", clean_text)
    sentences = [
        s.strip() for s in raw_sentences
        if len(s.strip()) > 15 and not re.search(r"\.\s*\.\s*\.", s)
    ]

    raw_words = re.findall(r"\b[a-zA-Z]{3,}\b", raw_text)
    unique_words = set()
    filtered_gibberish_count = 0

    for w in raw_words:
        w_lower = w.lower()
        if w_lower in gibberish_set:
            filtered_gibberish_count += 1
            continue
        if w_lower not in STOPWORDS:
            unique_words.add(w_lower)

    print(f"[+] Filtered out {filtered_gibberish_count} gibberish word instances.")
    print(f"[+] Extracted {len(unique_words)} valid unique English words.")

    # Single-pass reverse index: scan each sentence once instead of O(words * sentences)
    word_examples = {}
    for s in sentences:
        s_display = s[:300] + "..." if len(s) > 300 else s
        for token in re.findall(r"\b[a-zA-Z]{3,}\b", s):
            t_low = token.lower()
            if t_low in unique_words and t_low not in word_examples:
                word_examples[t_low] = s_display

    return sorted(unique_words), word_examples


def move_existing_cards(cards_to_move):
    if not cards_to_move:
        return 0
    print(f"[*] Moving {len(cards_to_move)} cards to deck '{TARGET_DECK}'...")
    chunk_size = 500
    moved_count = 0
    for i in range(0, len(cards_to_move), chunk_size):
        chunk = cards_to_move[i:i + chunk_size]
        call_anki("changeDeck", cards=chunk, deck=TARGET_DECK)
        moved_count += len(chunk)
    print(f"[OK] Moved {moved_count} cards to '{TARGET_DECK}'.")
    return moved_count


def update_note_examples(notes_with_examples):
    """Batch-update example fields using AnkiConnect 'multi' action."""
    if not notes_with_examples:
        return
    total = len(notes_with_examples)
    print(f"[*] Updating example fields for {total} notes (batched)...")

    batch_size = 50
    updated = 0
    errors = 0
    for i in range(0, total, batch_size):
        chunk = notes_with_examples[i:i + batch_size]
        actions = [
            {
                "action": "updateNoteFields",
                "params": {"note": {"id": nid, "fields": {"example": ex}}}
            }
            for nid, ex in chunk
        ]
        result, err = call_anki_safe("multi", actions=actions)
        if err:
            print(f"  [!] Batch {i // batch_size + 1} failed: {err}")
            errors += len(chunk)
        else:
            # multi returns a list of results; count non-error entries
            for r in (result or []):
                if r is None or (isinstance(r, dict) and r.get("error") is None):
                    updated += 1
                else:
                    errors += 1

        done = min(i + batch_size, total)
        if done % 200 < batch_size or done == total:
            print(f"  [{done}/{total}]...")

    print(f"[OK] Updated {updated} example sentences ({errors} errors).")


def push_new_words(words_to_add, word_examples):
    if not words_to_add:
        print("[!] No new words to add.")
        return

    print(f"[*] Adding {len(words_to_add)} brand new words to '{TARGET_DECK}'...")
    notes = []
    for word in words_to_add:
        note = {
            "deckName": TARGET_DECK,
            "modelName": MODEL_NAME,
            "fields": {
                "Word": word,
                "IPA": "",
                "Image": "",
                "Reference": "",
                "example": word_examples.get(word, "")
            },
            "options": {
                "allowDuplicate": False,
                "duplicateScope": "deck",
                "duplicateScopeOptions": {
                    "deckName": "English",
                    "checkChildren": True
                }
            }
        }
        notes.append(note)

    results = call_anki("addNotes", notes=notes)
    added_count = sum(1 for r in results if r is not None)
    print(f"[OK] Added {added_count} new notes to '{TARGET_DECK}'!")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="Extract English words & example sentences from PDF and sync with Anki TOEIC deck"
    )
    parser.add_argument("pdf_path", help="Path to input PDF file")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages to process (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Report without executing changes")
    args = parser.parse_args()

    # Load gibberish once
    gibberish_set = load_gibberish_words()

    ensure_target_deck()
    word_to_note = get_existing_word_map()
    candidate_words, word_examples = extract_pdf_data(args.pdf_path, gibberish_set, max_pages=args.max_pages)

    toeic_cards = set(call_anki("findCards", query='deck:"English::toeic"'))
    cards_to_move = []
    notes_to_update_example = []
    new_words_to_add = []

    for word in candidate_words:
        if word in word_to_note:
            note = word_to_note[word]
            n_id = note["noteId"]
            cards = note.get("cards", [])
            ex = word_examples.get(word, "")
            if ex:
                curr_ex = note.get("fields", {}).get("example", {}).get("value", "").strip()
                if not curr_ex:
                    notes_to_update_example.append((n_id, ex))

            for c in cards:
                if c not in toeic_cards:
                    cards_to_move.append(c)
        else:
            new_words_to_add.append(word)

    print("\n--- PRE-RUN VERIFICATION SUMMARY ---")
    print(f"Total Candidate PDF Words (non-gibberish): {len(candidate_words)}")
    print(f"Cards to Move to '{TARGET_DECK}': {len(cards_to_move)}")
    print(f"Existing Notes to Update with 'example' sentence: {len(notes_to_update_example)}")
    print(f"Brand New Words to Create in '{TARGET_DECK}': {len(new_words_to_add)}")

    if args.dry_run:
        print("[!] Dry run complete. No changes made.")
        return

    print("\n[*] Executing updates...")
    move_existing_cards(cards_to_move)
    update_note_examples(notes_to_update_example)
    push_new_words(new_words_to_add, word_examples)


if __name__ == "__main__":
    main()
