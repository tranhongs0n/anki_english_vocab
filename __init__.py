from aqt import mw, gui_hooks
from aqt.qt import QAction, QShortcut, QKeySequence

from .core.db_registry import init_db_registry
from .ui.practice_pad import toggle_practice_pad, clear_practice_pad
from .ui.settings_dialog import open_settings_dialog
from .modules.move_cards import move_current_card
from .modules.root_words import process_root_word
from .modules.vocab_generator import init_vocab_module, update_card_ai, check_gibberish_ai
from .modules.image_tools import crop_current_card_image, process_notes_images
from .modules.sync_pipeline import run_pipeline, run_pipeline_and_sync
from .modules.zoom_manager import init_zoom, zoom_in, zoom_out, zoom_reset

def get_addon_config() -> dict:
    return mw.addonManager.getConfig(__name__) or {} if (mw and mw.addonManager) else {}

def on_state_shortcuts(state: str, shortcuts: list):
    if state == "review":
        cfg = get_addon_config()
        sc, decks = cfg.get("shortcuts", {}), cfg.get("decks", {})
        binds = [
            ("root_word", lambda: process_root_word(cfg)),
            ("move_to_later", lambda: move_current_card(decks.get("deck_later", ""))),
            ("move_to_other", lambda: move_current_card(decks.get("deck_other", ""))),
            ("image_cropper", crop_current_card_image),
            ("update_card_ai", lambda: update_card_ai(cfg)),
            ("check_gibberish_ai", lambda: check_gibberish_ai(cfg))
        ]
        for name, fn in binds:
            if sc.get(name): shortcuts.append((sc[name], fn))

def setup_global_shortcuts_and_menu():
    if not mw: return
    cfg = get_addon_config()
    sc = cfg.get("shortcuts", {})
    mw._vocab_suite_shortcuts = []
    
    globals_list = [
        ("practice_pad", "F8", toggle_practice_pad),
        ("sync_pipeline", "Ctrl+Y", lambda: run_pipeline_and_sync(cfg)),
        ("zoom_in", "Ctrl+=", zoom_in),
        ("zoom_out", "Ctrl+-", zoom_out),
        ("zoom_reset", "Ctrl+0", zoom_reset)
    ]
    for key, default, fn in globals_list:
        seq = sc.get(key, default)
        if seq:
            s = QShortcut(QKeySequence(seq), mw)
            s.activated.connect(fn)
            mw._vocab_suite_shortcuts.append(s)

    if hasattr(mw, "form") and hasattr(mw.form, "menuTools"):
        act = QAction("Vocab Suite Settings...", mw)
        act.triggered.connect(open_settings_dialog)
        mw.form.menuTools.addAction(act)

def init_addon():
    init_db_registry()
    cfg = get_addon_config()
    init_vocab_module(cfg)
    if cfg.get("features", {}).get("enable_zoom_persist", True): init_zoom()

    if hasattr(gui_hooks, "state_shortcuts_will_change"): gui_hooks.state_shortcuts_will_change.append(on_state_shortcuts)
    elif hasattr(gui_hooks, "reviewer_did_init_shortcuts"): gui_hooks.reviewer_did_init_shortcuts.append(lambda sc, rev: on_state_shortcuts("review", sc))

    gui_hooks.browser_menus_did_init.append(lambda b: b.form.menuEdit.addAction("Square and White BG (WebP)", lambda: process_notes_images(b.selectedNotes(), "Selected")))
    gui_hooks.reviewer_did_show_question.append(lambda c: clear_practice_pad())

    if cfg.get("features", {}).get("enable_pre_sync_pipeline", True):
        gui_hooks.sync_will_start.append(lambda: run_pipeline(cfg))

    if mw and hasattr(mw, "form") and mw.form: setup_global_shortcuts_and_menu()
    else: gui_hooks.main_window_did_init.append(setup_global_shortcuts_and_menu)

init_addon()