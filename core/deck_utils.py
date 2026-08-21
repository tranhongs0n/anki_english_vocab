import re
import html
from aqt import mw

RE_TAG = re.compile(r'<[^>]+>')
RE_SPACE = re.compile(r'\s+')

def clean_html_text(s: str) -> str:
    return RE_SPACE.sub(' ', html.unescape(str(s or '')).replace('\xa0', ' ')).strip()

def get_deck_id(name: str) -> int:
    if not mw or not mw.col or not name: return 0
    decks = {d.name: d.id for d in mw.col.decks.all_names_and_ids()}
    if name in decks: return decks[name]
    nl = name.lower()
    for dname, did in decks.items():
        if dname.lower() == nl or dname.lower().endswith('::' + nl) or nl in dname.lower().split('::'):
            return did
    return mw.col.decks.id(name)

def get_target_model(name: str = ''):
    if not mw or not mw.col: return None
    return mw.col.models.by_name(name) if name else (mw.col.models.all()[0] if mw.col.models.all() else None)

def extract_word_from_card(card, field: str = '') -> str:
    if not card: return ''
    note = card.note()
    val = note[field] if (field and field in note) else next((note[f] for f in ('Word', 'word', 'Vocab', 'vocab', 'Front', 'front') if f in note), note.fields[0] if note.fields else '')
    cleaned = clean_html_text(RE_TAG.sub('', str(val)))
    m = re.findall(r'[a-zA-Z\-]+', cleaned)
    return (m[0] if m else cleaned).strip().lower()

def find_card_by_word(word: str, field: str = ''):
    if not mw or not mw.col: return None, None
    w = word.lower().strip()
    cids = mw.col.find_cards(f'{field}:\"{w}\"' if field else f'\"{w}\"') or mw.col.find_cards(f'\"{w}\"')
    for cid in cids:
        card = mw.col.get_card(cid)
        note = card.note()
        val = note[field] if (field and field in note) else (note.fields[0] if note.fields else '')
        if clean_html_text(RE_TAG.sub('', str(val))).lower() == w:
            return note, cid
    return None, None

def move_card_to_deck(cid: int, deck: str) -> str:
    if not mw or not mw.col or not deck: return ''
    did = get_deck_id(deck)
    name = mw.col.decks.name(did)
    if hasattr(mw.col, 'set_deck'): mw.col.set_deck([cid], did)
    elif hasattr(mw.col.decks, 'set_deck'): mw.col.decks.set_deck([cid], did)
    else:
        c = mw.col.get_card(cid)
        c.did = did
        if hasattr(c, 'odid') and c.odid: c.odid = 0
        mw.col.update_card(c) if hasattr(mw.col, 'update_card') else c.flush()
    return name