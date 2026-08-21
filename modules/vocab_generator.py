import re
import json
import time
import queue
import threading
from aqt import mw, gui_hooks
from aqt.utils import tooltip
from ..core.llm_client import call_llm, get_prompt
from ..core.deck_utils import get_deck_id, get_target_model, clean_html_text, extract_word_from_card, move_card_to_deck
from ..core.db_registry import is_gibberish, is_processed, add_processed, add_gibberish

RE_TAG = re.compile(r'<[^>]+>')
RE_THINK = re.compile(r'<think>.*?</think>', re.DOTALL)
RE_ENGLISH = re.compile(r'^[a-zA-Z\s\-]+$')
RE_CJK = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf]')

_word_queue = queue.Queue()
_existing_words = None

def push_word_to_batch(w: str):
    cw = w.strip().lower()
    if is_valid_english(cw) and not is_processed(cw) and not is_gibberish(cw):
        add_processed(cw)
        _word_queue.put(cw)

def is_valid_english(w: str) -> bool:
    return bool(w and len(w) >= 2 and RE_ENGLISH.match(w) and any(c.isalpha() for c in w))

def get_existing_words() -> set:
    global _existing_words
    if _existing_words is None:
        _existing_words = {clean_html_text(RE_TAG.sub('', str(r[0]))).lower() for r in (mw.col.db.all('select sfld from notes') if mw and mw.col else []) if r[0]}
    return _existing_words

def batch_worker(cfg: dict):
    target_deck = cfg.get('decks', {}).get('target_learning', '')
    model_name = cfg.get('note_types', {}).get('default_model', '')
    gen_cfg = cfg.get('vocab_generator', {})
    b_size = gen_cfg.get('batch_size', 10)
    b_timeout = gen_cfg.get('batch_timeout_seconds', 120)

    while True:
        batch = []
        try:
            batch.append(_word_queue.get(timeout=86400))
            t0 = time.time()
            while len(batch) < b_size and (b_timeout - (time.time() - t0)) > 0:
                try: batch.append(_word_queue.get(timeout=max(1, b_timeout - (time.time() - t0))))
                except queue.Empty: break
            
            raw, err = call_llm(get_prompt('vocab_batch', 'user', words=json.dumps(batch)), get_prompt('vocab_batch', 'system'), max_tokens=450, timeout=10.0)
            if not err and raw:
                try:
                    cl = RE_THINK.sub('', raw).strip()
                    s, e = cl.find('['), cl.rfind(']')
                    data = json.loads(cl[s:e+1]) if (s != -1 and e != -1) else None
                except Exception: data = None
                
                if data and isinstance(data, list):
                    exist = get_existing_words()
                    to_add = [{'word': clean_html_text(i[0]).lower(), 'ipa': clean_html_text(i[1]).replace('/', '').strip(), 'meaning': clean_html_text(i[2]), 'example': clean_html_text(i[3]) if len(i) >= 4 else ''}
                              for i in data if isinstance(i, list) and len(i) >= 3 and is_valid_english(clean_html_text(i[0]).lower()) and clean_html_text(i[0]).lower() not in exist and not is_gibberish(clean_html_text(i[0]).lower())]
                    if to_add:
                        def insert():
                            if not mw or not mw.col: return
                            did = get_deck_id(target_deck) if target_deck else (mw.col.decks.all_names_and_ids()[0].id if mw.col.decks.all_names_and_ids() else 1)
                            model = get_target_model(model_name)
                            if not model or not did: return
                            fnames = [f['name'] for f in model['flds']]
                            added = 0
                            for it in to_add:
                                n = mw.col.new_note(model)
                                n.target_deck_id = did
                                if 'Word' in fnames: n['Word'] = it['word']
                                else: n.fields[0] = it['word']
                                if 'IPA' in fnames: n['IPA'] = it['ipa']
                                elif len(fnames) > 1: n.fields[1] = it['ipa']
                                if 'Reference' in fnames: n['Reference'] = it['meaning']
                                elif len(fnames) > 2: n.fields[2] = it['meaning']
                                if 'example' in fnames: n['example'] = it['example']
                                elif 'Example' in fnames: n['Example'] = it['example']
                                try:
                                    mw.col.add_note(n, did)
                                    exist.add(it['word'])
                                    add_processed(it['word'])
                                    added += 1
                                except Exception: pass
                            if added > 0: tooltip(f'+{added} related cards added', period=2000)
                        mw.taskman.run_on_main(insert)
            for _ in batch: _word_queue.task_done()
        except Exception: pass

def update_card_ai(cfg: dict):
    if not mw or not mw.reviewer or not mw.reviewer.card:
        tooltip('No card active.', period=1000)
        return
    card = mw.reviewer.card
    word = extract_word_from_card(card)
    if not is_valid_english(word):
        tooltip(f'\"{word}\" not valid English.', period=1000)
        return
    tooltip(f'Updating \"{word}\"...', period=1200)
    
    def bg():
        raw, err = call_llm(get_prompt('card_update', 'user', word=word), get_prompt('card_update', 'system'), max_tokens=150, timeout=6.0)
        if err or not raw: return None
        try:
            cl = RE_THINK.sub('', raw).strip()
            s, e = cl.find('['), cl.rfind(']')
            data = json.loads(cl[s:e+1]) if (s != -1 and e != -1) else None
            if data and isinstance(data, list) and len(data) >= 3:
                meaning = clean_html_text(data[2])
                if RE_CJK.search(meaning):
                    fix_raw, _ = call_llm(get_prompt('card_update', 'cjk_fallback', meaning=meaning, word=word), max_tokens=60, timeout=4.0)
                    if fix_raw and not RE_CJK.search(fix_raw): meaning = clean_html_text(fix_raw).strip('\"\'[]')
                return {'ipa': clean_html_text(data[1]).replace('/', '').strip(), 'meaning': meaning, 'example': clean_html_text(data[3]) if len(data) >= 4 else ''}
        except Exception: pass
        return None

    def on_done(f):
        res = f.result()
        if not res or not mw or not mw.col: tooltip(f'Update failed for \"{word}\".', period=1500); return
        try:
            note = card.note()
            fnames = list(note.keys())
            if 'IPA' in fnames: note['IPA'] = res['ipa']
            if 'Reference' in fnames: note['Reference'] = res['meaning']
            if 'example' in fnames: note['example'] = res['example']
            elif 'Example' in fnames: note['Example'] = res['example']
            mw.col.update_notes([note])
            r_ipa, r_mean = res['ipa'], res['meaning']
            tooltip(f"{word}: {r_ipa} | {r_mean}", period=2000)
        except Exception as e: tooltip(f'Update error: {e}', period=1500)

    mw.taskman.run_in_background(bg, on_done)

def check_gibberish_ai(cfg: dict):
    if not mw or not mw.reviewer or not mw.reviewer.card:
        tooltip('No card active.', period=1000)
        return
    card = mw.reviewer.card
    word = extract_word_from_card(card)
    deck_other = cfg.get('decks', {}).get('deck_other', '')
    if not is_valid_english(word) or is_gibberish(word):
        actual = move_card_to_deck(card.id, deck_other) if deck_other else 'trash'
        add_gibberish(word)
        tooltip(f'Moved \"{word}\" -> {actual}', period=1200)
        mw.reviewer.nextCard()
        return
    tooltip(f'Checking \"{word}\"...', period=1000)
    
    def on_done(f):
        res = f.result()
        if res.startswith('0') or 'gibberish' in res.lower() or 'invalid' in res.lower():
            actual = move_card_to_deck(card.id, deck_other) if deck_other else 'trash'
            add_gibberish(word)
            tooltip(f'Moved \"{word}\" -> {actual}', period=1200)
            mw.reviewer.nextCard()
        else: tooltip(f'\"{word}\" valid', period=1000)

    mw.taskman.run_in_background(lambda: (call_llm(get_prompt('gibberish_check', 'user', word=word), max_tokens=5, timeout=3.0)[0] or '').strip(), on_done)

def init_vocab_module(cfg: dict):
    if cfg.get('features', {}).get('enable_background_related_vocab', True):
        threading.Thread(target=batch_worker, args=(cfg,), daemon=True).start()
        gui_hooks.reviewer_did_show_question.append(lambda c: push_word_to_batch(extract_word_from_card(c)) if c else None)