try:
    from aqt import mw
    from aqt.qt import QDialog, QVBoxLayout, QTextEdit, QFont, QShortcut, QKeySequence, QGuiApplication, Qt
except ImportError:
    mw, QVBoxLayout, QTextEdit, QFont, QShortcut, QKeySequence, QGuiApplication, Qt = [None] * 8
    class QDialog:
        def __init__(self, *a, **k): pass

from ..core.deck_utils import get_addon_config

def get_pad_cfg() -> dict:
    return get_addon_config().get('practice_pad', {})

class PracticePadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Practice Pad')
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        cfg = get_pad_cfg()
        self.w, self.h = cfg.get('width', 760), cfg.get('height', 220)
        self.resize(self.w, self.h)
        
        l = QVBoxLayout(self); l.setContentsMargins(0, 0, 0, 0)
        self.text_edit = QTextEdit(self)
        self.text_edit.setStyleSheet('''
            QTextEdit {
                background-color: rgba(24, 24, 27, 0.95);
                color: #f4f4f5;
                border: 1.5px solid #3f3f46;
                border-radius: 12px;
                padding: 16px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-weight: 600;
            }
        ''')
        font = QFont(cfg.get('font_family', 'Segoe UI'), cfg.get('font_size', 32))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.text_edit.setFont(font)
        l.addWidget(self.text_edit)
        
        for key in ('Esc', 'Ctrl+Return'): QShortcut(QKeySequence(key), self).activated.connect(self.hide_pad)
        QShortcut(QKeySequence('Ctrl+L'), self).activated.connect(self.text_edit.clear)

    def hide_pad(self):
        self.text_edit.clear(); self.hide()
        if mw and mw.reviewer and hasattr(mw.reviewer, 'web') and mw.reviewer.web: mw.reviewer.web.setFocus()

    def hideEvent(self, event):
        self.text_edit.clear(); super().hideEvent(event)

    def show_pad(self):
        self.text_edit.clear()
        g = mw.geometry()
        scr = QGuiApplication.screenAt(g.center())
        sg = scr.availableGeometry() if scr else QGuiApplication.primaryScreen().availableGeometry()
        x = max(sg.left() + 10, min(g.x() + (g.width() - self.w) // 2, sg.right() - self.w - 10))
        y = max(sg.top() + 10, min(g.y() + g.height() - self.h - 30, sg.bottom() - self.h - 10))
        self.move(x, y); self.show(); self.raise_(); self.activateWindow(); self.text_edit.setFocus()

_pad = None
def toggle_practice_pad():
    global _pad
    if not mw: return
    if _pad is None: _pad = PracticePadDialog(mw)
    _pad.hide_pad() if _pad.isVisible() else _pad.show_pad()

def clear_practice_pad():
    global _pad
    if _pad: _pad.text_edit.clear()