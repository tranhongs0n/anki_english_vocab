import base64
import os
import re
from typing import Optional

try:
    from aqt import mw, gui_hooks
    from aqt.utils import tooltip
    from aqt.qt import (
        QDockWidget, QWidget, QVBoxLayout, QWebEngineView, QWebEngineProfile,
        QWebChannel, QObject, pyqtSlot, Qt, QUrl, QFile, QIODevice, QImage
    )
except ImportError:
    mw, gui_hooks, tooltip = None, None, None
    QDockWidget = object
    QWidget, QVBoxLayout, QWebEngineView, QWebEngineProfile = None, None, None, None
    QWebChannel, QObject, pyqtSlot, Qt, QUrl, QFile, QIODevice, QImage = None, None, None, None, None, None, None, None

from ..core.deck_utils import get_addon_config, clean_html
from ..core.media_utils import normalize_image, save_media_webp

RE_NON_WORD = re.compile(r"[^a-zA-Z0-9\s-]")
_DOCK_INSTANCE = None

UBLOCK_STYLE = """
header, #header, #searchform, .RNNXgb, .sfbg, .F1Akfe, .minidiv,
#botstuff, #footcnt, #fbar, footer, .commercial-unit,
.K32tfe, .M8Qgvd, div[role="navigation"], .appbar, #easter-egg,
.LXqFEc, .mJ77Sc, .tAcEof {
  display: none !important;
}
body {
  padding-top: 8px !important;
  background-color: #1a1a1a !important;
  color: #e0e0e0 !important;
  overflow-x: hidden !important;
}
.vimium-img-badge {
  position: absolute !important;
  top: 4px !important;
  left: 4px !important;
  background: #000000 !important;
  color: #ffd700 !important;
  font-family: monospace, sans-serif !important;
  font-size: 13px !important;
  font-weight: 800 !important;
  padding: 2px 6px !important;
  border-radius: 4px !important;
  border: 1.5px solid #ffd700 !important;
  z-index: 2147483647 !important;
  pointer-events: none !important;
  box-shadow: 0 2px 6px rgba(0,0,0,0.8) !important;
}
"""

INJECTED_SCRIPT = """
(function() {
  if (window.__anki_bridge_initialized) return;
  window.__anki_bridge_initialized = true;

  const style = document.createElement('style');
  style.textContent = `__CSS_PLACEHOLDER__`;
  document.head.appendChild(style);

  let pyBridge = null;
  new QWebChannel(qt.webChannelTransport, function(channel) {
    pyBridge = channel.objects.bridge;
  });

  function getVisibleImages() {
    const candidates = Array.from(document.querySelectorAll(
      'div[jsname="figiqf"] img, div.Fp3I9 img, div[data-tbnid] img, img[src*="gstatic.com"], img[src^="data:image"]'
    ));
    const seen = new Set();
    const visible = [];

    for (const img of candidates) {
      if (!img || seen.has(img)) continue;
      const src = img.src || '';
      if (!src || src.startsWith('data:image/svg') || src.includes('favicon')) continue;
      const rect = img.getBoundingClientRect();
      if (rect.width < 50 || rect.height < 50) continue;
      if (rect.bottom < 0 || rect.top > window.innerHeight) continue;
      const style = window.getComputedStyle(img);
      if (style.display === 'none' || style.visibility === 'hidden') continue;

      seen.add(img);
      visible.push({ img, rect });
      if (visible.length >= 9) break;
    }
    return visible;
  }

  function renderBadges() {
    document.querySelectorAll('.vimium-img-badge').forEach(el => el.remove());
    const visible = getVisibleImages();
    visible.forEach((item, idx) => {
      const parent = item.img.parentElement;
      if (!parent) return;
      const prevPos = window.getComputedStyle(parent).position;
      if (prevPos === 'static') parent.style.position = 'relative';

      const badge = document.createElement('div');
      badge.className = 'vimium-img-badge';
      badge.textContent = (idx + 1).toString();
      parent.appendChild(badge);
    });
  }

  function extractBase64(img) {
    const src = img.src || '';
    if (src.startsWith('data:image/')) {
      const comma = src.indexOf(',');
      if (comma !== -1) {
        const ext = src.slice(11, src.indexOf(';')) || 'jpg';
        return { base64: src.slice(comma + 1), ext };
      }
    }
    try {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth || img.width;
      canvas.height = img.naturalHeight || img.height;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(img, 0, 0);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
      return { base64: dataUrl.split(',')[1], ext: 'jpg' };
    } catch {
      return null;
    }
  }

  function selectImageByIndex(index) {
    const visible = getVisibleImages();
    if (index < 0 || index >= visible.length) return;
    const target = visible[index].img;
    const extracted = extractBase64(target);
    if (extracted && pyBridge) {
      pyBridge.onImageSelected(extracted.base64, extracted.ext);
    }
  }

  document.addEventListener('keydown', function(e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
      if (e.key === 'Escape') e.target.blur();
      return;
    }

    const key = e.key;
    if (key >= '1' && key <= '9') {
      e.preventDefault();
      selectImageByIndex(parseInt(key, 10) - 1);
    } else if (key === 'j') {
      e.preventDefault();
      window.scrollBy({ top: 250, behavior: 'smooth' });
    } else if (key === 'k') {
      e.preventDefault();
      window.scrollBy({ top: -250, behavior: 'smooth' });
    } else if (key === '/') {
      e.preventDefault();
      const input = document.querySelector('textarea[name="q"], input[name="q"]');
      if (input) {
        input.style.display = 'block';
        input.focus();
        input.select();
      }
    } else if (key === 'Escape') {
      e.preventDefault();
      if (pyBridge) pyBridge.onCloseRequested();
    }
  });

  document.addEventListener('click', function(e) {
    const img = e.target.closest('img');
    if (!img) return;
    const extracted = extractBase64(img);
    if (extracted && pyBridge) {
      e.preventDefault();
      pyBridge.onImageSelected(extracted.base64, extracted.ext);
    }
  }, true);

  window.addEventListener('scroll', () => setTimeout(renderBadges, 100), { passive: true });
  const observer = new MutationObserver(() => setTimeout(renderBadges, 150));
  observer.observe(document.body, { childList: true, subtree: true });
  setTimeout(renderBadges, 300);
})();
"""

def get_channel_js() -> str:
    f = QFile(":/qtwebchannel/qwebchannel.js")
    if f.open(QIODevice.OpenModeFlag.ReadOnly):
        content = str(f.readAll(), "utf-8")
        f.close()
        return content
    return ""

class ImageBridge(QObject):
    def __init__(self, parent_dock):
        super().__init__()
        self.dock = parent_dock

    @pyqtSlot(str, str)
    def onImageSelected(self, base64_str: str, ext: str):
        if not mw or not mw.reviewer or not mw.reviewer.card:
            if tooltip: tooltip("No active card in reviewer.", period=1200)
            return

        try:
            raw_bytes = base64.b64decode(base64_str)
            qimg = QImage()
            qimg.loadFromData(raw_bytes)
            if qimg.isNull():
                if tooltip: tooltip("Failed to decode image.", period=1200)
                return

            opt = normalize_image(qimg) or qimg
            filename = save_media_webp(opt, prefix="img_")
            if not filename:
                if tooltip: tooltip("Failed to save media.", period=1200)
                return

            card = mw.reviewer.card
            note = card.note()
            cfg = get_addon_config()
            img_field = cfg.get("note_types", {}).get("field_image", "Image")

            if img_field not in note:
                for candidate in ["Image", "Picture", "Img", "Back"]:
                    if candidate in note:
                        img_field = candidate
                        break
                else:
                    img_field = list(note.keys())[-1]

            current = note[img_field]
            img_tag = f'<img src="{filename}">'
            note[img_field] = f"{current}<br>{img_tag}" if current else img_tag

            mw.col.update_notes([note])

            card.load()
            if hasattr(mw.reviewer, "_showQuestion") and mw.reviewer.state == "question":
                mw.reviewer._showQuestion()
            elif hasattr(mw.reviewer, "_showAnswer") and mw.reviewer.state == "answer":
                mw.reviewer._showAnswer()

            if tooltip: tooltip("Image added to card.", period=1200)
            if mw.reviewer.web: mw.reviewer.web.setFocus()
        except Exception as e:
            if tooltip: tooltip(f"Save error: {e}", period=1500)

    @pyqtSlot()
    def onCloseRequested(self):
        if self.dock:
            self.dock.hide()
            if mw and mw.reviewer and mw.reviewer.web:
                mw.reviewer.web.setFocus()

class EmbeddedImageDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Image Search", parent)
        self.setObjectName("EmbeddedImageSearchDock")
        self.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable)

        self.web = QWebEngineView(self)
        self.channel = QWebChannel(self.web.page())
        self.bridge = ImageBridge(self)
        self.channel.registerObject("bridge", self.bridge)
        self.web.page().setWebChannel(self.channel)

        self.channel_js = get_channel_js()
        self.current_query = ""

        self.web.loadFinished.connect(self._on_load_finished)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setWidget(container)

    def _on_load_finished(self, success: bool):
        if not success: return
        js_code = f"{self.channel_js}\n{INJECTED_SCRIPT.replace('__CSS_PLACEHOLDER__', UBLOCK_STYLE.replace(chr(10), ' '))}"
        self.web.page().runJavaScript(js_code)

    def search_word(self, word: str):
        cleaned = RE_NON_WORD.sub("", clean_html(word)).strip()
        if not cleaned or cleaned == self.current_query: return
        self.current_query = cleaned

        js = f"""
        (function() {{{{
          const input = document.querySelector('textarea[name="q"], input[name="q"]');
          const form = document.querySelector('form[action*="/search"]');
          if (input && form) {{{{
            input.value = "{cleaned}";
            form.submit();
          }}}} else {{{{
            window.location.href = "https://www.google.com/search?udm=2&q={cleaned}";
          }}}}
        }}}})();
        """
        self.web.page().runJavaScript(js)

def get_image_dock() -> Optional[EmbeddedImageDock]:
    global _DOCK_INSTANCE
    if not mw or not QWebEngineView: return None
    if _DOCK_INSTANCE is None:
        _DOCK_INSTANCE = EmbeddedImageDock(mw)
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, _DOCK_INSTANCE)
    return _DOCK_INSTANCE

def toggle_image_browser():
    dock = get_image_dock()
    if not dock: return

    if dock.isVisible():
        dock.hide()
        if mw and mw.reviewer and mw.reviewer.web:
            mw.reviewer.web.setFocus()
    else:
        dock.show()
        dock.raise_()
        sync_active_card_image()

def sync_active_card_image():
    dock = get_image_dock()
    if not dock or not dock.isVisible(): return
    if not mw or not mw.reviewer or not mw.reviewer.card: return

    card = mw.reviewer.card
    note = card.note()
    cfg = get_addon_config()
    word_field = cfg.get("note_types", {}).get("field_word", "Word")
    raw_word = note[word_field] if word_field in note else note[list(note.keys())[0]]
    cleaned = RE_NON_WORD.sub("", clean_html(raw_word)).strip()

    if cleaned:
        if not dock.web.url() or dock.web.url().isEmpty() or "google.com" not in dock.web.url().toString():
            dock.current_query = cleaned
            dock.web.setUrl(QUrl(f"https://www.google.com/search?udm=2&q={cleaned}"))
        else:
            dock.search_word(cleaned)
