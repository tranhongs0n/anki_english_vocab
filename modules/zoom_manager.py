import os
import json
try:
    from aqt import mw, gui_hooks
except ImportError:
    mw, gui_hooks = None, None

from ..core.deck_utils import get_addon_config

_CFG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'zoom_config.json')

def get_zoom_rules() -> dict:
    return get_addon_config().get('zoom', {}) or {'step': 0.1, 'min': 0.3, 'max': 3.0, 'default': 1.0}

def load_zoom() -> float:
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, 'r', encoding='utf-8') as f: return json.load(f).get('zoom', get_zoom_rules().get('default', 1.0))
    except Exception: pass
    return get_zoom_rules().get('default', 1.0)

def save_zoom(z: float):
    try:
        os.makedirs(os.path.dirname(_CFG_FILE), exist_ok=True)
        with open(_CFG_FILE, 'w', encoding='utf-8') as f: json.dump({'zoom': round(z, 2)}, f)
    except Exception: pass

def apply_target_zoom():
    if not mw: return
    z = load_zoom()
    for view in (getattr(mw, 'deckBrowser', None), getattr(mw, 'reviewer', None)):
        if view and hasattr(view, 'web') and view.web and hasattr(view.web, 'setZoomFactor'):
            try: view.web.setZoomFactor(z)
            except Exception: pass

def zoom_in():
    r = get_zoom_rules()
    save_zoom(min(round(load_zoom() + r.get('step', 0.1), 2), r.get('max', 3.0)))
    apply_target_zoom()

def zoom_out():
    r = get_zoom_rules()
    save_zoom(max(round(load_zoom() - r.get('step', 0.1), 2), r.get('min', 0.3)))
    apply_target_zoom()

def zoom_reset():
    save_zoom(get_zoom_rules().get('default', 1.0))
    apply_target_zoom()

def init_zoom():
    if not gui_hooks: return
    for hook in (getattr(gui_hooks, 'sync_did_finish', None), getattr(gui_hooks, 'reviewer_did_show_question', None), getattr(gui_hooks, 'reviewer_did_show_answer', None)):
        if hook and hasattr(hook, 'append'):
            hook.append(lambda *args: apply_target_zoom())