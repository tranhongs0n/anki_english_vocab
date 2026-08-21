import os
import json
import time
import sqlite3
import threading

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'vocab_registry.sqlite')
_gibberish, _processed, _roots, _pending = set(), set(), {}, []
_lock = threading.Lock()
_timer = None

def get_db():
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5.0)
    conn.executescript('''
        PRAGMA journal_mode = WAL;
        PRAGMA synchronous = NORMAL;
        CREATE TABLE IF NOT EXISTS vocab_registry (word TEXT PRIMARY KEY, status TEXT NOT NULL, target TEXT, created_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_status ON vocab_registry(status);
    ''')
    return conn

def load_all_to_memory():
    global _gibberish, _processed, _roots
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT word, status, target FROM vocab_registry')
    g, p, r = set(), set(), {}
    for w, status, target in cur.fetchall():
        if status == 'gibberish': g.add(w)
        elif status == 'processed': p.add(w)
        elif status == 'root': r[w] = target or w
    conn.close()
    with _lock: _gibberish, _processed, _roots = g, p, r

def _flush():
    global _pending, _timer
    with _lock:
        if not _pending: return
        batch, _pending, _timer = list(_pending), [], None
    try:
        conn = get_db()
        conn.executemany('INSERT INTO vocab_registry VALUES (?, ?, ?, ?) ON CONFLICT(word) DO UPDATE SET status=excluded.status, target=excluded.target', batch)
        conn.commit()
        conn.close()
    except Exception: pass

def _schedule(item):
    global _timer
    with _lock:
        _pending.append(item)
        if _timer is None:
            _timer = threading.Timer(1.5, _flush)
            _timer.daemon = True
            _timer.start()

def is_gibberish(w: str) -> bool:
    with _lock: return w.strip().lower() in _gibberish

def is_processed(w: str) -> bool:
    with _lock: return w.strip().lower() in _processed

def get_root(w: str) -> str:
    with _lock: return _roots.get(w.strip().lower())

def add_gibberish(w: str):
    cw = w.strip().lower()
    if cw:
        with _lock: _gibberish.add(cw)
        _schedule((cw, 'gibberish', None, int(time.time())))

def add_gibberish_batch(words: list[str]):
    now = int(time.time())
    with _lock:
        for w in words:
            cw = w.strip().lower()
            if cw:
                _gibberish.add(cw)
                _pending.append((cw, 'gibberish', None, now))
    _flush()

def add_processed(w: str):
    cw = w.strip().lower()
    if cw:
        with _lock: _processed.add(cw)
        _schedule((cw, 'processed', None, int(time.time())))

def set_root(w: str, root: str):
    cw, cr = w.strip().lower(), root.strip().lower()
    if cw and cr:
        with _lock: _roots[cw] = cr
        _schedule((cw, 'root', cr, int(time.time())))

def export_repo_txt(repo_dir: str):
    if not repo_dir or not os.path.exists(repo_dir): return
    _flush()
    data_dir = os.path.join(repo_dir, 'data')
    os.makedirs(data_dir, exist_ok=True)
    with _lock: g, p, r = sorted(_gibberish), sorted(_processed), dict(_roots)
    try:
        with open(os.path.join(data_dir, 'gibberish.txt'), 'w', encoding='utf-8') as f:
            for w in g: f.write(w + '\n')
        with open(os.path.join(data_dir, 'processed_words.txt'), 'w', encoding='utf-8') as f:
            for w in p: f.write(w + '\n')
        with open(os.path.join(data_dir, 'root_cache.json'), 'w', encoding='utf-8') as f:
            json.dump(r, f, ensure_ascii=False, indent=2)
    except Exception: pass

def init_db_registry():
    threading.Thread(target=load_all_to_memory, daemon=True).start()