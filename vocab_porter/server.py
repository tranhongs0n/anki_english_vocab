import os
import re
import html as html_mod
import json
import urllib.request
import traceback
import base64
import hashlib
import asyncio
from typing import List, Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import fitz  # PyMuPDF
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

ANKI_CONNECT_URL = "http://127.0.0.1:8765"
DEFAULT_TARGET_DECK = "English::toeic"
DEFAULT_PARENT_DECK_QUERY = "deck:English"
MODEL_NAME = "Concrete Words"
GIBBERISH_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "gibberish.txt")
ENV_FILE = os.path.join(os.path.dirname(__file__), "..", ".env")
OCR_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "ocr_cache")

# Tested & verified working fallback chain for Vision OCR
VISION_MODELS_CHAIN = [
    "thanhnhan9023/claude-opus-4-8-china",
    "thanhnhan9023/claude-sonnet-5-kiro",
    "pthung310106/Minimax-M3",
    "26479061/claude-haiku-4.5",
    "devdoclang/deepseek-v4-pro"
]

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

app = FastAPI(title="Anki Vocab Porter API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_env_vars() -> Dict[str, str]:
    vars_dict = {}
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        vars_dict[k.strip()] = v.strip()
        except Exception as e:
            print(f"[!] Error loading .env: {e}")
    return vars_dict

def load_gibberish_words() -> frozenset:
    words = set()
    if os.path.exists(GIBBERISH_FILE):
        try:
            with open(GIBBERISH_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    w = line.strip().lower()
                    if w:
                        words.add(w)
        except Exception as e:
            print(f"[!] Error reading gibberish file: {e}")
    return frozenset(words)

def call_anki(action: str, **params) -> Any:
    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
    req = urllib.request.Request(ANKI_CONNECT_URL, payload)
    try:
        response = urllib.request.urlopen(req, timeout=10)
        res_data = json.loads(response.read().decode("utf-8"))
        if res_data.get("error"):
            raise RuntimeError(f"AnkiConnect Error ({action}): {res_data['error']}")
        return res_data["result"]
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"AnkiConnect API ({action}): {e}") from e

def call_anki_safe(action: str, **params) -> tuple[Any, Optional[str]]:
    try:
        return call_anki(action, **params), None
    except Exception as e:
        return None, str(e)

def get_page_cache_path(pdf_hash: str, page_idx: int) -> str:
    cache_folder = os.path.join(OCR_CACHE_DIR, pdf_hash)
    os.makedirs(cache_folder, exist_ok=True)
    return os.path.join(cache_folder, f"page_{page_idx:04d}.txt")

def call_single_page_ocr_with_fallback(b64_img: str, api_key: str, api_url: str) -> tuple[str, str]:
    """Tries models in VISION_MODELS_CHAIN in sequence with auto-fallback on error."""
    last_err = ""
    for model_name in VISION_MODELS_CHAIN:
        payload = {
            "model": model_name,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract all English text accurately from this scanned page. Transcribe passages, questions, and options verbatim. Output raw plain text only."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                ]
            }],
            "temperature": 0.0
        }

        req = urllib.request.Request(
            api_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                res_json = json.loads(res.read().decode("utf-8"))
                txt = res_json["choices"][0]["message"]["content"]
                if "can't view images" not in txt.lower() and "don't see any image" not in txt.lower() and len(txt) > 50:
                    return txt, model_name
        except Exception as e:
            last_err = f"{model_name}: {e}"
            continue

    raise RuntimeError(f"All vision models failed. Last error: {last_err}")

def extract_text_and_sentences(raw_text: str, max_lines: Optional[int] = None):
    if max_lines and max_lines > 0:
        lines = raw_text.splitlines()[:max_lines]
        raw_text = "\n".join(lines)

    clean_text = re.sub(r"\s+", " ", raw_text)
    raw_sentences = re.split(r"(?<=[.!?])\s+", clean_text)
    sentences = [
        s.strip() for s in raw_sentences
        if len(s.strip()) > 15 and not re.search(r"\.\s*\.\s*\.", s)
    ]
    return raw_text, sentences

def analyze_words(
    raw_text: str,
    sentences: List[str],
    target_deck: str = DEFAULT_TARGET_DECK,
    parent_query: str = DEFAULT_PARENT_DECK_QUERY,
    enable_gibberish: bool = True,
    enable_stopwords: bool = True
):
    gibberish_set = load_gibberish_words() if enable_gibberish else frozenset()
    raw_words = re.findall(r"\b[a-zA-Z]{3,}\b", raw_text)
    
    unique_words = set()
    gibberish_count = 0
    stopwords_count = 0
    
    for w in raw_words:
        w_lower = w.lower()
        if enable_gibberish and w_lower in gibberish_set:
            gibberish_count += 1
            continue
        if enable_stopwords and w_lower in STOPWORDS:
            stopwords_count += 1
            continue
        unique_words.add(w_lower)

    word_examples = {}
    for s in sentences:
        s_display = s[:300] + "..." if len(s) > 300 else s
        for token in re.findall(r"\b[a-zA-Z]{3,}\b", s):
            t_low = token.lower()
            if t_low in unique_words and t_low not in word_examples:
                word_examples[t_low] = s_display

    anki_connected = False
    word_to_note = {}
    toeic_card_ids = set()
    error_msg = None

    try:
        note_ids = call_anki("findNotes", query=parent_query)
        anki_connected = True
        
        chunk_size = 1000
        for i in range(0, len(note_ids), chunk_size):
            chunk = note_ids[i:i + chunk_size]
            notes_info = call_anki("notesInfo", notes=chunk)
            for note in notes_info:
                fields = note.get("fields", {})
                for field_name in ["Word", "Front"]:
                    if field_name in fields:
                        raw_val = fields[field_name].get("value", "")
                        val = re.sub(r"<[^>]+>", "", html_mod.unescape(raw_val)).strip().lower()
                        if val:
                            word_to_note[val] = note

        target_cards = call_anki("findCards", query=f'deck:"{target_deck}"')
        toeic_card_ids = set(target_cards or [])
    except Exception as e:
        error_msg = str(e)
        print(f"[!] Anki lookup notice: {e}")

    items = []
    cards_to_move = []
    notes_to_update_example = []
    new_words_to_add = []

    for word in sorted(unique_words):
        example_sent = word_examples.get(word, "")
        if word in word_to_note:
            note = word_to_note[word]
            n_id = note["noteId"]
            cards = note.get("cards", [])
            curr_ex = note.get("fields", {}).get("example", {}).get("value", "").strip()
            
            unmoved_cards = [c for c in cards if c not in toeic_card_ids]
            
            if unmoved_cards:
                status = "move_to_deck"
                cards_to_move.extend(unmoved_cards)
            else:
                status = "already_in_deck"

            if example_sent and not curr_ex:
                notes_to_update_example.append((n_id, example_sent))

            items.append({
                "word": word,
                "status": status,
                "note_id": n_id,
                "cards": cards,
                "example": example_sent,
                "has_existing_example": bool(curr_ex)
            })
        else:
            status = "brand_new"
            new_words_to_add.append({"word": word, "example": example_sent})
            items.append({
                "word": word,
                "status": status,
                "note_id": None,
                "cards": [],
                "example": example_sent,
                "has_existing_example": False
            })

    stats = {
        "total_extracted": len(unique_words),
        "cards_to_move": len(cards_to_move),
        "notes_to_update_example": len(notes_to_update_example),
        "brand_new_words": len(new_words_to_add),
        "gibberish_filtered": gibberish_count,
        "stopwords_filtered": stopwords_count,
        "anki_connected": anki_connected,
        "anki_error": error_msg
    }

    return {
        "stats": stats,
        "items": items,
        "cards_to_move": cards_to_move,
        "notes_to_update_example": [{"note_id": nid, "example": ex} for nid, ex in notes_to_update_example],
        "new_words_to_add": new_words_to_add
    }

class ParseTextRequest(BaseModel):
    text: str
    target_deck: str = DEFAULT_TARGET_DECK
    parent_deck: str = DEFAULT_PARENT_DECK_QUERY
    enable_gibberish: bool = True
    enable_stopwords: bool = True
    max_lines: Optional[int] = None

class SyncAnkiRequest(BaseModel):
    target_deck: str = DEFAULT_TARGET_DECK
    cards_to_move: List[int] = []
    notes_to_update_example: List[Dict[str, Any]] = []
    words_to_add: List[Dict[str, str]] = []
    dry_run: bool = False

@app.get("/api/status")
def get_status():
    try:
        version = call_anki("version")
        decks = call_anki("deckNames")
        models = call_anki("modelNames")
        env_vars = load_env_vars()
        api_key = env_vars.get("LLM_API_KEY") or env_vars.get("CKEY_API_KEY")
        return {
            "connected": True,
            "version": version,
            "decks": decks or [],
            "models": models or [],
            "gibberish_count": len(load_gibberish_words()),
            "default_target_deck": DEFAULT_TARGET_DECK,
            "vision_model": VISION_MODELS_CHAIN[0],
            "fallback_models": VISION_MODELS_CHAIN[1:],
            "has_llm_vision": bool(api_key)
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "version": None,
            "decks": [],
            "models": [],
            "gibberish_count": len(load_gibberish_words()),
            "default_target_deck": DEFAULT_TARGET_DECK,
            "has_llm_vision": False
        }

@app.post("/api/parse-text")
def parse_text_endpoint(req: ParseTextRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Input text cannot be empty.")
    
    raw_text, sentences = extract_text_and_sentences(req.text, max_lines=req.max_lines)
    result = analyze_words(
        raw_text=raw_text,
        sentences=sentences,
        target_deck=req.target_deck,
        parent_query=req.parent_deck,
        enable_gibberish=req.enable_gibberish,
        enable_stopwords=req.enable_stopwords
    )
    return result

@app.post("/api/parse-file-stream")
async def parse_file_stream_endpoint(
    file: UploadFile = File(...),
    target_deck: str = Form(DEFAULT_TARGET_DECK),
    parent_deck: str = Form(DEFAULT_PARENT_DECK_QUERY),
    enable_gibberish: bool = Form(True),
    enable_stopwords: bool = Form(True),
    page_range: Optional[str] = Form(None),
    ocr_mode: str = Form("auto")  # "auto", "pure_text", "force_ocr"
):
    content_bytes = await file.read()
    filename = file.filename or "unknown"
    ext = os.path.splitext(filename)[1].lower()
    pdf_hash = hashlib.md5(content_bytes).hexdigest()[:12]

    async def event_generator():
        try:
            yield f"data: {json.dumps({'event': 'log', 'message': f'Received file: {filename} ({len(content_bytes)//1024} KB) | Mode: {ocr_mode}', 'type': 'info'})}\n\n"
            
            full_text_list = []
            used_ocr = False

            if ext in [".pdf", ".epub", ".mobi", ".fb2", ".xps"]:
                with fitz.open(stream=content_bytes, filetype=ext.lstrip(".")) as doc:
                    total_pages = len(doc)
                    
                    target_page_indices = []
                    if page_range and page_range.strip():
                        parts = page_range.split(",")
                        for part in parts:
                            part = part.strip()
                            if "-" in part:
                                start, end = part.split("-", 1)
                                s_idx = max(0, int(start) - 1)
                                e_idx = min(total_pages, int(end))
                                target_page_indices.extend(range(s_idx, e_idx))
                            elif part.isdigit():
                                idx = int(part) - 1
                                if 0 <= idx < total_pages:
                                    target_page_indices.append(idx)
                        target_page_indices = sorted(list(set(target_page_indices)))
                    else:
                        target_page_indices = list(range(total_pages))

                    results_map = {}
                    pages_to_ocr = []

                    # 1. Inspect each target page individually
                    for p_idx in target_page_indices:
                        native_txt = doc[p_idx].get_text().strip()
                        
                        if ocr_mode == "pure_text":
                            results_map[p_idx] = native_txt
                        elif ocr_mode == "force_ocr":
                            pages_to_ocr.append(p_idx)
                        else:
                            # "auto" mode: if page has selectable text (>25 chars), extract directly!
                            if len(native_txt) > 25:
                                results_map[p_idx] = native_txt
                                yield f"data: {json.dumps({'event': 'log', 'message': f'[Page {p_idx + 1}] Selectable text extracted directly ({len(native_txt)} chars, 0s)', 'type': 'info'})}\n\n"
                            else:
                                pages_to_ocr.append(p_idx)

                    # 2. If there are image-only pages that require OCR
                    if pages_to_ocr and ocr_mode != "pure_text":
                        used_ocr = True
                        yield f"data: {json.dumps({'event': 'log', 'message': f'Running Vision OCR on {len(pages_to_ocr)} image-only pages...', 'type': 'warn'})}\n\n"
                        
                        env_vars = load_env_vars()
                        api_key = env_vars.get("LLM_API_KEY") or env_vars.get("CKEY_API_KEY")
                        api_url = env_vars.get("LLM_API_URL", "https://api.xah.io/v1/chat/completions")

                        pages_to_fetch = []
                        for p_idx in pages_to_ocr:
                            cache_file = get_page_cache_path(pdf_hash, p_idx)
                            if os.path.exists(cache_file):
                                try:
                                    with open(cache_file, "r", encoding="utf-8") as f:
                                        results_map[p_idx] = f.read()
                                        yield f"data: {json.dumps({'event': 'log', 'message': f'[Page {p_idx + 1}] Loaded from local cache (0s)', 'type': 'info'})}\n\n"
                                except Exception:
                                    pages_to_fetch.append(p_idx)
                            else:
                                pages_to_fetch.append(p_idx)

                        if pages_to_fetch:
                            yield f"data: {json.dumps({'event': 'log', 'message': f'Calling Vision API for {len(pages_to_fetch)} uncached image pages (5 workers)...', 'type': 'info'})}\n\n"
                            
                            def worker(idx):
                                page = doc[idx]
                                pix = page.get_pixmap(dpi=120)
                                b64 = base64.b64encode(pix.tobytes("jpeg")).decode("utf-8")
                                txt, used_model = call_single_page_ocr_with_fallback(b64, api_key, api_url)
                                cache_f = get_page_cache_path(pdf_hash, idx)
                                try:
                                    with open(cache_f, "w", encoding="utf-8") as cf:
                                        cf.write(txt)
                                except Exception:
                                    pass
                                return idx, txt, used_model

                            loop = asyncio.get_event_loop()
                            with ThreadPoolExecutor(max_workers=5) as pool:
                                futures = [loop.run_in_executor(pool, worker, idx) for idx in pages_to_fetch]
                                completed_count = len(target_page_indices) - len(pages_to_fetch)
                                
                                for f in asyncio.as_completed(futures):
                                    try:
                                        p_idx, txt, used_model = await f
                                        results_map[p_idx] = txt
                                        completed_count += 1
                                        pct = int((completed_count / len(target_page_indices)) * 100)
                                        yield f"data: {json.dumps({'event': 'progress', 'completed': completed_count, 'total': len(target_page_indices), 'percent': pct})}\n\n"
                                        yield f"data: {json.dumps({'event': 'log', 'message': f'[Page {p_idx + 1}] Transcribed {len(txt)} chars via {used_model}', 'type': 'success'})}\n\n"
                                    except Exception as err:
                                        yield f"data: {json.dumps({'event': 'log', 'message': f'[!] Page OCR error: {err}', 'type': 'error'})}\n\n"

                    full_text_list = [results_map.get(i, "") for i in target_page_indices]

                raw_text = " ".join(full_text_list)
            else:
                raw_text = content_bytes.decode("utf-8", errors="ignore")

            if not raw_text.strip():
                yield f"data: {json.dumps({'event': 'error', 'message': 'No text extracted from file.'})}\n\n"
                return

            yield f"data: {json.dumps({'event': 'log', 'message': f'Extracted {len(raw_text)} total characters. Tokenizing & querying Anki database...', 'type': 'info'})}\n\n"

            raw_text, sentences = extract_text_and_sentences(raw_text)
            result = analyze_words(
                raw_text=raw_text,
                sentences=sentences,
                target_deck=target_deck,
                parent_query=parent_deck,
                enable_gibberish=enable_gibberish,
                enable_stopwords=enable_stopwords
            )
            result["filename"] = filename
            result["filesize"] = len(content_bytes)
            result["used_ocr"] = used_ocr
            result["pages_processed"] = len(target_page_indices) if 'target_page_indices' in locals() else 1

            yield f"data: {json.dumps({'event': 'complete', 'data': result})}\n\n"

        except Exception as e:
            traceback.print_exc()
            yield f"data: {json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.post("/api/sync-anki")
def sync_anki_endpoint(req: SyncAnkiRequest):
    logs = []
    
    if req.dry_run:
        logs.append("[DRY-RUN] Verification complete. No mutations performed on Anki.")
        return {
            "success": True,
            "dry_run": True,
            "cards_moved": len(req.cards_to_move),
            "examples_updated": len(req.notes_to_update_example),
            "words_added": len(req.words_to_add),
            "logs": logs
        }

    try:
        call_anki("createDeck", deck=req.target_deck)
        logs.append(f"[OK] Target deck '{req.target_deck}' ready.")

        moved_count = 0
        if req.cards_to_move:
            chunk_size = 500
            for i in range(0, len(req.cards_to_move), chunk_size):
                chunk = req.cards_to_move[i:i + chunk_size]
                call_anki("changeDeck", cards=chunk, deck=req.target_deck)
                moved_count += len(chunk)
            logs.append(f"[OK] Moved {moved_count} cards to '{req.target_deck}'.")

        updated_examples = 0
        example_errors = 0
        if req.notes_to_update_example:
            batch_size = 50
            for i in range(0, len(req.notes_to_update_example), batch_size):
                chunk = req.notes_to_update_example[i:i + batch_size]
                actions = [
                    {
                        "action": "updateNoteFields",
                        "params": {"note": {"id": item["note_id"], "fields": {"example": item["example"]}}}
                    }
                    for item in chunk if item.get("note_id") and item.get("example")
                ]
                res, err = call_anki_safe("multi", actions=actions)
                if err:
                    example_errors += len(chunk)
                    logs.append(f"[!] Example batch update notice: {err}")
                else:
                    for r in (res or []):
                        if r is None or (isinstance(r, dict) and r.get("error") is None):
                            updated_examples += 1
                        else:
                            example_errors += 1
            logs.append(f"[OK] Updated {updated_examples} example sentences ({example_errors} errors).")

        added_notes = 0
        if req.words_to_add:
            notes = []
            for item in req.words_to_add:
                w = item.get("word", "").strip()
                if not w:
                    continue
                notes.append({
                    "deckName": req.target_deck,
                    "modelName": MODEL_NAME,
                    "fields": {
                        "Word": w,
                        "IPA": "",
                        "Image": "",
                        "Reference": "",
                        "example": item.get("example", "")
                    },
                    "options": {
                        "allowDuplicate": False,
                        "duplicateScope": "deck",
                        "duplicateScopeOptions": {
                            "deckName": "English",
                            "checkChildren": True
                        }
                    }
                })

            res = call_anki("addNotes", notes=notes)
            added_notes = sum(1 for r in (res or []) if r is not None)
            logs.append(f"[OK] Added {added_notes} new notes to '{req.target_deck}'.")

        return {
            "success": True,
            "dry_run": False,
            "cards_moved": moved_count,
            "examples_updated": updated_examples,
            "words_added": added_notes,
            "logs": logs
        }
    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "logs": logs + [f"[FATAL] Sync failed: {str(e)}"]
        }

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    print(f"[*] Starting Anki Vocab Porter Web App on http://127.0.0.1:8766 ...")
    uvicorn.run(app, host="127.0.0.1", port=8766, log_level="info")
