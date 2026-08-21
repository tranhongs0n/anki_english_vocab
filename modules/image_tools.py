import os
import re
import time
try:
    from aqt import mw
    from aqt.utils import tooltip
    from aqt.qt import QDialog
except ImportError:
    mw, tooltip, QDialog = None, lambda *a, **k: None, None
from ..core.media_utils import normalize_image, save_media_webp
from ..ui.image_cropper import ImageCropDialog

RE_IMG_SRC = re.compile(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE)

def crop_current_card_image():
    if not mw or not mw.reviewer or not mw.reviewer.card:
        tooltip("No card active.", period=1000)
        return
    note = mw.reviewer.card.note()
    img_field, img_src = None, None
    for k, v in note.items():
        if isinstance(v, str) and "<img" in v:
            m = RE_IMG_SRC.search(v)
            if m:
                img_field, img_src = k, m.group(1)
                break
    if not img_src:
        tooltip("No image.", period=1000)
        return
    if img_src.startswith("http://") or img_src.startswith("https://"):
        tooltip("Remote image. Sync first.", period=1200)
        return
    img_path = os.path.join(mw.col.media.dir(), img_src)
    if not os.path.exists(img_path):
        tooltip("Image file missing.", period=1200)
        return
    dlg = ImageCropDialog(img_path, parent=mw)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        cropped = dlg.get_cropped_image()
        opt = normalize_image(cropped)
        new_name = save_media_webp(opt)
        if new_name:
            note[img_field] = RE_IMG_SRC.sub(f'<img src="{new_name}">', note[img_field], count=1)
            mw.col.update_notes([note])
            if mw.reviewer and mw.reviewer.card and mw.reviewer.card.id == mw.reviewer.card.id:
                mw.reviewer.card.load()
                if hasattr(mw.reviewer, '_showQuestion') and mw.reviewer.state == 'question':
                    mw.reviewer._showQuestion()
                elif hasattr(mw.reviewer, '_showAnswer') and mw.reviewer.state == 'answer':
                    mw.reviewer._showAnswer()
            tooltip("Cropped.", period=1000)

def process_notes_images(note_ids, prefix="Batch"):
    if not note_ids or not mw or not mw.col:
        tooltip("No notes selected.", period=1500)
        return
    mw.progress.start(title=f"[{prefix}] Optimizing Images", immediate=True)
    try:
        id_str = ",".join(map(str, note_ids))
        rows = mw.col.db.all(f"select id, flds from notes where id in ({id_str}) and flds like '%<img%'")
        img_map, tasks = {}, []
        for nid, flds in rows:
            for m in RE_IMG_SRC.finditer(flds):
                src = m.group(1)
                if not src.startswith("http") and not src.startswith("data:") and src not in img_map:
                    img_map[src] = None
                    tasks.append((src, os.path.join(mw.col.media.dir(), src)))

        converted_count = 0
        for idx, (src, p) in enumerate(tasks):
            mw.progress.update(label=f"Scanning {idx+1}/{len(tasks)}...", value=idx, max=len(tasks))
            opt = normalize_image(p)
            if opt is not None:
                new_name = save_media_webp(opt)
                img_map[src] = new_name if new_name else src
                if new_name and new_name != src:
                    converted_count += 1
            else:
                img_map[src] = src

        changed_notes = []
        if converted_count > 0:
            for nid, flds in rows:
                try: note = mw.col.get_note(nid)
                except Exception: continue
                chg = False
                for k, v in note.items():
                    if isinstance(v, str) and "<img" in v:
                        def repl(match):
                            nonlocal chg
                            s = match.group(1)
                            if s in img_map and img_map[s] and img_map[s] != s:
                                chg = True
                                return f'<img src="{img_map[s]}">'
                            return match.group(0)
                        nv = RE_IMG_SRC.sub(repl, v)
                        if nv != v:
                            note[k] = nv
                            chg = True
                if chg:
                    changed_notes.append(note)
            if changed_notes:
                mw.col.update_notes(changed_notes)
                mw.reset()

        skipped_count = len(tasks) - converted_count
        tooltip(f"Converted {converted_count} imgs, skipped {skipped_count} optimal ({len(changed_notes)} notes updated).", period=2500)
    finally:
        mw.progress.finish()