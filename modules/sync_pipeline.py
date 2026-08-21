import os
import re
import time
import subprocess
import threading
import html
from collections import defaultdict
try:
    from aqt import mw
    from aqt.utils import tooltip, showInfo
    from aqt.qt import QCoreApplication
except ImportError:
    mw, tooltip, showInfo, QCoreApplication = None, lambda *a, **k: None, lambda *a, **k: None, None
from ..core.deck_utils import clean_html_text
from ..core.db_registry import add_gibberish_batch, export_repo_txt
from .image_tools import process_notes_images

RE_TAG, RE_SPACE = re.compile(r'<[^>]+>'), re.compile(r'\s+')
_running = False

def run_pipeline(cfg: dict):
    global _running
    if _running or not mw or not mw.col: return
    _running = True
    try:
        dump_gibberish_and_suspend(cfg)
        nids = [x[0] for x in mw.col.db.all('select id from notes where flds like \'%<img%\'')]
        if nids: process_notes_images(nids, 'Sync')
        
        repo_dir = cfg.get('features', {}).get('git_repo_path', '') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.exists(os.path.join(repo_dir, '.git')):
            threading.Thread(target=git_push_repo, args=(repo_dir,), daemon=True).start()
        
        try:
            mw.col.db.execute('PRAGMA optimize')
            mw.col.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception: pass
        mw.col.conf['pre_sync_last_run'] = int(time.time())
    finally: _running = False

def dump_gibberish_and_suspend(cfg: dict):
    deck_other = cfg.get('decks', {}).get('deck_other', '')
    if deck_other:
        nids = mw.col.find_notes(f'deck:\"{deck_other}\"')
        if nids:
            id_str = ','.join(map(str, nids))
            words = [clean_html_text(RE_TAG.sub('', str(r[0]).split('\x1f')[0])).lower() for r in mw.col.db.all(f'select flds from notes where id in ({id_str})') if r[0]]
            if words: add_gibberish_batch([w for w in words if w])
            mw.col.remove_notes(nids)
    
    suspend = [d for d in cfg.get('decks', {}).get('suspend_decks', []) if d]
    if suspend:
        cards = mw.col.find_cards(' or '.join([f'deck:\"{d}\"' for d in suspend]))
        if cards: mw.col.sched.suspend_cards(cards)

def git_push_repo(repo_dir: str):
    if not repo_dir or not os.path.exists(repo_dir): return
    flags = 0x08000000 if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
    def run(cmd): return subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True, timeout=10, creationflags=flags)
    try:
        if not run(['git', 'status', '-s']).stdout.strip(): return
        tag = run(['git', 'describe', '--tags', '--abbrev=0']).stdout.strip()
        if tag and tag.startswith('v'):
            p = list(map(int, tag[1:].split('.'))); p[-1] += 1
            new_tag = f'v{p[0]}.{p[1]}.{p[2]}'
        else: new_tag = 'v1.0.0'
        run(['git', 'add', '.'])
        run(['git', 'commit', '-m', f'Release {new_tag}'])
        run(['git', 'tag', '-a', new_tag, '-m', f'Auto {new_tag}'])
        branch = run(['git', 'rev-parse', '--abbrev-ref', 'HEAD']).stdout.strip() or 'main'
        run(['git', 'push', 'origin', branch])
        run(['git', 'push', 'origin', new_tag])
    except Exception: pass

def run_pipeline_and_sync(cfg: dict):
    tooltip('Pipeline running...', period=1000)
    run_pipeline(cfg)
    if mw and hasattr(mw, 'onSync'): mw.onSync()

def run_full_manual_cleanup():
    if not mw or not mw.col: return
    mw.progress.start(title='Full Collection Cleanup', max=3, immediate=True)
    try:
        mw.progress.update(label='1/3: Cleaning IPA...', value=1)
        QCoreApplication.processEvents()
        rows = mw.col.db.all('select id from notes where flds like \'%/%\' or flds like \'%  %\'')
        if rows:
            mods = []
            for r in rows:
                n, chg = mw.col.get_note(r[0]), False
                for k, v in n.items():
                    if isinstance(v, str):
                        nv = RE_SPACE.sub(' ', v.replace('/', '')).strip() if 'ipa' in k.lower() else RE_SPACE.sub(' ', html.unescape(v).replace('\xa0', ' ')).strip()
                        if nv != v: n[k] = nv; chg = True
                if chg: mods.append(n)
            if mods: mw.col.update_notes(mods)

        mw.progress.update(label='2/3: Purging unused media...', value=2)
        QCoreApplication.processEvents()
        res = mw.col.media.check()
        if res.unused:
            mw.col.media.trash_files(list(res.unused))
            mw.col.media.empty_trash()

        mw.progress.update(label='3/3: Deduplicating notes...', value=3)
        QCoreApplication.processEvents()
        w_map = defaultdict(list)
        for nid, sfld in mw.col.db.all('select id, sfld from notes'):
            if sfld:
                w = clean_html_text(RE_TAG.sub('', str(sfld))).lower()
                if w: w_map[w].append(nid)
        to_del = []
        for w, nids in w_map.items():
            if len(nids) > 1:
                id_s = ','.join(map(str, nids))
                c_rows = mw.col.db.all(f'select nid, max(type), max(ivl) from cards where nid in ({id_s}) group by nid')
                scores = {r[0]: (r[1] or 0, r[2] or 0) for r in c_rows}
                to_del.extend(sorted(nids, key=lambda x: scores.get(x, (0, 0)))[:-1])
        if to_del: mw.col.remove_notes(to_del)
        mw.reset()
        showInfo('Cleanup complete.')
    finally: mw.progress.finish()