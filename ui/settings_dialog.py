from aqt import mw
from aqt.utils import tooltip, showWarning
from aqt.qt import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QCheckBox, QTabWidget, QWidget, QFormLayout, QScrollArea, QSpinBox, QDoubleSpinBox
)
from ..core.llm_client import read_env, save_env, ping_llm, fetch_models

SHORTCUTS = [
    ("root_word", "Root Word (F4)"), ("move_to_later", "Move to Later (F5)"),
    ("move_to_other", "Move to Other (F6)"), ("image_cropper", "Image Cropper (F7)"),
    ("practice_pad", "Practice Pad (F8)"), ("update_card_ai", "AI Update Card (F9)"),
    ("check_gibberish_ai", "AI Check Gibberish (F10)"), ("sync_pipeline", "Pipeline & Sync (Ctrl+Y)"),
    ("zoom_in", "Zoom In (Ctrl+=)"), ("zoom_out", "Zoom Out (Ctrl+-)"), ("zoom_reset", "Zoom Reset (Ctrl+0)")
]

class UnifiedSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vocab Suite Settings")
        self.resize(560, 500)
        self.cfg = mw.addonManager.getConfig("anki_vocab_suite") or {}
        self.env_cfg = read_env()
        self.inputs = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        tabs = QTabWidget(self)
        tabs.addTab(self.tab_ai(), "AI Settings")
        tabs.addTab(self.tab_shortcuts(), "Shortcuts")
        tabs.addTab(self.tab_decks(), "Decks & Notes")
        tabs.addTab(self.tab_tuning(), "Tuning & UI")
        layout.addWidget(tabs)

        btn_box = QHBoxLayout()
        btn_cancel, btn_save = QPushButton("Cancel", self), QPushButton("Save All", self)
        btn_cancel.clicked.connect(self.reject)
        btn_save.setStyleSheet("background: #2563eb; color: white; font-weight: bold; padding: 6px 16px; border-radius: 6px;")
        btn_save.clicked.connect(self.on_save)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def tab_ai(self) -> QWidget:
        w, l = QWidget(), QVBoxLayout()
        l.setSpacing(6)
        
        self.inputs['url'] = QLineEdit(self.env_cfg.get("LLM_BASE_URL", "https://api.deepseek.com"), w)
        l.addWidget(QLabel("Base URL:", w))
        l.addWidget(self.inputs['url'])

        k_row = QHBoxLayout()
        k_row.addWidget(QLabel("API Key (LLM_API_KEY):", w))
        chk = QCheckBox("Show", w)
        chk.toggled.connect(lambda c: self.inputs['key'].setEchoMode(QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        k_row.addStretch(); k_row.addWidget(chk)
        l.addLayout(k_row)

        k_box = QHBoxLayout()
        self.inputs['key'] = QLineEdit(self.env_cfg.get("LLM_API_KEY", ""), w)
        self.inputs['key'].setEchoMode(QLineEdit.EchoMode.Password)
        self.inputs['key'].setPlaceholderText("sk-...")
        btn_fetch = QPushButton("Fetch Models", w)
        btn_fetch.clicked.connect(self.on_fetch_models)
        k_box.addWidget(self.inputs['key'])
        k_box.addWidget(btn_fetch)
        l.addLayout(k_box)

        l.addWidget(QLabel("Active Model:", w))
        self.model_combo = QComboBox(w)
        self.model_combo.setEditable(True)
        for m in self.cfg.get("llm", {}).get("candidate_models", []): self.model_combo.addItem(m)
        self.model_combo.setCurrentText(self.env_cfg.get("LLM_MODEL", "deepseek-v4-flash"))
        l.addWidget(self.model_combo)

        self.status = QLabel("", w)
        self.status.setStyleSheet("color: #6b7280; font-size: 11px;")
        l.addWidget(self.status)
        l.addStretch()

        btn_test = QPushButton("Ping Test", w)
        btn_test.clicked.connect(self.on_test_llm)
        l.addWidget(btn_test)
        w.setLayout(l)
        return w

    def tab_shortcuts(self) -> QWidget:
        w, scroll, inner, form = QWidget(), QScrollArea(), QWidget(), QFormLayout()
        scroll.setWidgetResizable(True)
        sc = self.cfg.get("shortcuts", {})
        for k, lbl in SHORTCUTS:
            self.inputs[f'sc_{k}'] = QLineEdit(sc.get(k, ""), inner)
            form.addRow(lbl, self.inputs[f'sc_{k}'])
        inner.setLayout(form)
        scroll.setWidget(inner)
        main_l = QVBoxLayout(w); main_l.addWidget(scroll); w.setLayout(main_l)
        return w

    def tab_decks(self) -> QWidget:
        w, form = QWidget(), QFormLayout(w)
        decks, notes, feat = self.cfg.get("decks", {}), self.cfg.get("note_types", {}), self.cfg.get("features", {})
        fields = [
            ('d_learn', 'Target Learning Deck:', decks.get('target_learning', 'English::00_Learning')),
            ('d_later', 'Later Deck (F5):', decks.get('deck_later', 'English::98_Later')),
            ('d_other', 'Trash Deck (F6/F10):', decks.get('deck_other', 'English::99_Other')),
            ('m_name', 'Note Type Name:', notes.get('default_model', 'Concrete Words')),
            ('f_word', 'Word Field:', notes.get('field_word', 'Word')),
            ('f_ipa', 'IPA Field:', notes.get('field_ipa', 'IPA')),
            ('f_mean', 'Meaning Field:', notes.get('field_meaning', 'Reference')),
            ('f_ex', 'Example Field:', notes.get('field_example', 'example')),
            ('repo', 'Git Backup Path:', feat.get('git_repo_path', ''))
        ]
        for key, lbl, val in fields:
            self.inputs[key] = QLineEdit(str(val), w)
            form.addRow(lbl, self.inputs[key])
        return w

    def tab_tuning(self) -> QWidget:
        w, form = QWidget(), QFormLayout(w)
        img, pad, gen, zm = self.cfg.get("image", {}), self.cfg.get("practice_pad", {}), self.cfg.get("vocab_generator", {}), self.cfg.get("zoom", {})
        
        self.inputs['img_h'] = QSpinBox(w); self.inputs['img_h'].setRange(50, 2000); self.inputs['img_h'].setValue(img.get('target_height', 300))
        self.inputs['img_q'] = QSpinBox(w); self.inputs['img_q'].setRange(1, 100); self.inputs['img_q'].setValue(img.get('webp_quality', 80))
        self.inputs['pad_w'] = QSpinBox(w); self.inputs['pad_w'].setRange(200, 3840); self.inputs['pad_w'].setValue(pad.get('width', 760))
        self.inputs['pad_h'] = QSpinBox(w); self.inputs['pad_h'].setRange(100, 2160); self.inputs['pad_h'].setValue(pad.get('height', 220))
        self.inputs['pad_f'] = QSpinBox(w); self.inputs['pad_f'].setRange(8, 120); self.inputs['pad_f'].setValue(pad.get('font_size', 32))
        self.inputs['b_size'] = QSpinBox(w); self.inputs['b_size'].setRange(1, 50); self.inputs['b_size'].setValue(gen.get('batch_size', 10))
        self.inputs['b_to'] = QSpinBox(w); self.inputs['b_to'].setRange(5, 600); self.inputs['b_to'].setValue(gen.get('batch_timeout_seconds', 120))
        self.inputs['z_step'] = QDoubleSpinBox(w); self.inputs['z_step'].setRange(0.01, 1.0); self.inputs['z_step'].setValue(zm.get('step', 0.1))

        form.addRow("Image Height (px):", self.inputs['img_h'])
        form.addRow("WebP Quality (1-100):", self.inputs['img_q'])
        form.addRow("Pad Width/Height:", self.inputs['pad_w'])
        form.addRow("Pad Height:", self.inputs['pad_h'])
        form.addRow("Pad Font Size:", self.inputs['pad_f'])
        form.addRow("Vocab Batch Size:", self.inputs['b_size'])
        form.addRow("Vocab Timeout (s):", self.inputs['b_to'])
        form.addRow("Zoom Step:", self.inputs['z_step'])
        return w

    def on_fetch_models(self):
        k, u = self.inputs['key'].text().strip(), self.inputs['url'].text().strip()
        if not k: self.status.setText("Enter API key first."); return
        self.status.setText("Fetching..."); self.setEnabled(False)
        def done(f):
            self.setEnabled(True)
            try:
                models, err = f.result()
                if models:
                    self.model_combo.clear()
                    for m in models: self.model_combo.addItem(m)
                    self.status.setText(f"Loaded {len(models)} models.")
                else: self.status.setText(f"Failed: {err}")
            except Exception as e: self.status.setText(f"Error: {e}")
        mw.taskman.run_in_background(lambda: fetch_models(k, u), done)

    def on_test_llm(self):
        k, u, m = self.inputs['key'].text().strip(), self.inputs['url'].text().strip(), self.model_combo.currentText().strip()
        if not k or not m: showWarning("Enter API Key & Model."); return
        self.status.setText(f"Testing {m}..."); self.setEnabled(False)
        def done(f):
            self.setEnabled(True)
            try:
                ok, res, dur = f.result()
                self.status.setText(f"OK ({dur:.0f}ms)" if ok else f"Fail: {res}")
            except Exception as e: self.status.setText(f"Error: {e}")
        mw.taskman.run_in_background(lambda: ping_llm(k, u, m), done)

    def on_save(self):
        save_env(self.inputs['key'].text().strip(), self.inputs['url'].text().strip(), self.model_combo.currentText().strip())
        sc = self.cfg.setdefault("shortcuts", {})
        for k, _ in SHORTCUTS: sc[k] = self.inputs[f'sc_{k}'].text().strip()

        decks = self.cfg.setdefault("decks", {})
        decks.update({'target_learning': self.inputs['d_learn'].text().strip(), 'deck_later': self.inputs['d_later'].text().strip(), 'deck_other': self.inputs['d_other'].text().strip()})

        notes = self.cfg.setdefault("note_types", {})
        notes.update({'default_model': self.inputs['m_name'].text().strip(), 'field_word': self.inputs['f_word'].text().strip(), 'field_ipa': self.inputs['f_ipa'].text().strip(), 'field_meaning': self.inputs['f_mean'].text().strip(), 'field_example': self.inputs['f_ex'].text().strip()})

        self.cfg.setdefault("image", {}).update({'target_height': self.inputs['img_h'].value(), 'webp_quality': self.inputs['img_q'].value()})
        self.cfg.setdefault("practice_pad", {}).update({'width': self.inputs['pad_w'].value(), 'height': self.inputs['pad_h'].value(), 'font_size': self.inputs['pad_f'].value()})
        self.cfg.setdefault("vocab_generator", {}).update({'batch_size': self.inputs['b_size'].value(), 'batch_timeout_seconds': self.inputs['b_to'].value()})
        self.cfg.setdefault("zoom", {})['step'] = self.inputs['z_step'].value()
        self.cfg.setdefault("features", {})['git_repo_path'] = self.inputs['repo'].text().strip()

        mw.addonManager.writeConfig("anki_vocab_suite", self.cfg)
        tooltip("Settings saved.", period=1200)
        self.accept()

def open_settings_dialog(): UnifiedSettingsDialog(mw).exec()