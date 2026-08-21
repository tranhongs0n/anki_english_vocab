import re
import json
import time
from aqt import mw
from aqt.utils import tooltip
from ..core.llm_client import call_llm, get_prompt
from ..core.deck_utils import get_deck_id, get_target_model, extract_word_from_card, find_card_by_word, clean_html_text
from ..core.db_registry import get_root, set_root
from .vocab_generator import push_word_to_batch, get_existing_words

RE_THINK = re.compile(r'<think>.*?</think>', re.DOTALL)
PREFIXES = ('un', 're', 'dis', 'mis', 'over', 'under', 'out', 'pre', 'post', 'anti', 'non', 'de', 'in', 'im')
_last_f4 = 0.0

def strip_suffix(w: str) -> list[str]:
    c = []
    if w.endswith('ying') and len(w) > 5: c.append(w[:-4] + 'y')
    elif w.endswith('ing') and len(w) > 4: c.extend([w[:-3] + 'e', w[:-4] if len(w) > 5 and w[-4] == w[-5] else w[:-3], w[:-3]])
    elif w.endswith(('ied', 'ies')) and len(w) > 4: c.append(w[:-3] + 'y')
    elif w.endswith('ed') and len(w) > 3: c.extend([w[:-2], w[:-2] + 'e', w[:-3] if len(w) > 4 and w[-3] == w[-4] else w[:-2]])
    elif w.endswith('es') and len(w) > 3: c.extend([w[:-2], w[:-1]])
    elif w.endswith('s') and not w.endswith('ss') and len(w) > 3: c.append(w[:-1])
    elif w.endswith('ness') and len(w) > 5: c.append(w[:-4])
    elif w.endswith(('able', 'tion')) and len(w) > 5: c.extend([w[:-4] + 'e', w[:-4]])
    elif w.endswith('ly') and len(w) > 3: c.append(w[:-2])
    elif w.endswith('er') and len(w) > 3: c.extend([w[:-2], w[:-2] + 'e', w[:-3] if len(w) > 4 and w[-3] == w[-4] else w[:-2]])
    return [x for x in c if len(x) >= 2]

def get_candidates(w: str) -> list[str]:
    w = w.lower().strip()
    cands = strip_suffix(w)
    for p in PREFIXES:
        if w.startswith(p) and len(w) > len(p) + 2:
            base = w[len(p):]
            cands.extend([base] + strip_suffix(base))
            break
    cands.append(w)
    seen = set()
    return [c for c in cands if c not in seen and not seen.add(c)]

def transition_card(orig_cid: int, root: str, orig_w: str, deck_later: str, is_new: bool = False):
    if not mw or not mw.reviewer: return
    try:
        did = get_deck_id(deck_later)
        if hasattr(mw.col, 'set_deck'): mw.col.set_deck([orig_cid], did)
    except Exception: pass
    mw.reviewer.nextCard()
    act = 'Created' if is_new else 'Found'
    tooltip(f'{act} \'{root}\'. \'{orig_w}\' -> Later', period=1200)

def process_root_word(cfg: dict):
    global _last_f4
    now = time.time()
    if now - _last_f4 < 0.5: return
    _last_f4 = now

    if not mw or mw.state != 'review' or not mw.reviewer or not mw.reviewer.card:
        tooltip('No card active.', period=1000)
        return

    card = mw.reviewer.card
    orig_cid, orig_did, word = card.id, card.did, extract_word_from_card(card)
    if not word: return

    deck_later = cfg.get('decks', {}).get('deck_later', '')
    target_deck = cfg.get('decks', {}).get('target_learning', '')
    model_name = cfg.get('note_types', {}).get('default_model', '')

    cached = get_root(word)
    if cached:
        if cached == word: tooltip(f'\'{word}\' is root.', period=1000); return
        _, cid = find_card_by_word(cached)
        if cid: transition_card(orig_cid, cached, word, deck_later)
        else: create_and_load(cached, orig_did, word, orig_cid, target_deck, model_name, deck_later)
        return

    exist = get_existing_words()
    cands = get_candidates(word)
    for c in cands:
        if c != word and c in exist:
            _, cid = find_card_by_word(c)
            if cid:
                set_root(word, c)
                transition_card(orig_cid, c, word, deck_later)
                return

    if len(cands) <= 1:
        set_root(word, word)
        tooltip(f'\'{word}\' is root.', period=1000)
        return

    tooltip(f'Root for \'{word}\'...', period=1000)
    snap_w, snap_cid, snap_did, snap_cands = word, orig_cid, orig_did, list(cands)

    def bg():
        raw, err = call_llm(get_prompt('root_word', 'user', word=snap_w), get_prompt('root_word', 'system'), max_tokens=30, timeout=5.0)
        if err or not raw: return ''
        try:
            cl = RE_THINK.sub('', raw).strip()
            s, e = cl.find('{'), cl.rfind('}')
            if s != -1 and e != -1:
                obj = json.loads(cl[s:e+1])
                return clean_html_text(obj.get('root') or obj.get('root_word', '')).lower()
        except Exception: pass
        return ''

    def on_done(f):
        root = f.result() or next((c for c in snap_cands if c != snap_w), snap_w)
        set_root(snap_w, root)
        if root == snap_w: tooltip(f'\'{snap_w}\' is root.', period=1000); return
        _, cid = find_card_by_word(root)
        if cid: transition_card(snap_cid, root, snap_w, deck_later)
        else: create_and_load(root, snap_did, snap_w, snap_cid, target_deck, model_name, deck_later)

    mw.taskman.run_in_background(bg, on_done)

def create_and_load(root: str, did: int, orig_w: str, orig_cid: int, target_deck: str, model_name: str, deck_later: str):
    if not mw or not mw.col: return
    target_did = get_deck_id(target_deck) if target_deck else did
    model = get_target_model(model_name)
    if not model: mw.reviewer.nextCard(); return
    n = mw.col.new_note(model)
    n.target_deck_id = target_did
    fnames = [f['name'] for f in model['flds']]
    if 'Word' in fnames: n['Word'] = root
    else: n.fields[0] = root
    try:
        mw.col.add_note(n, target_did)
        push_word_to_batch(root)
        transition_card(orig_cid, root, orig_w, deck_later, is_new=True)
    except Exception: mw.reviewer.nextCard()