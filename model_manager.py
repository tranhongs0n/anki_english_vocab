"""
DeepSeek Settings & Model Selector for Anki.
Short, direct, caveman style UI.
"""

import os
import json
import time
import urllib.request
import urllib.error
import threading

try:
    from aqt import mw, gui_hooks
    from aqt.utils import tooltip, showInfo, showWarning
    from aqt.qt import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
        QComboBox, QAction, QFont, Qt, QCheckBox
    )
except ImportError:
    mw = None
    gui_hooks = None
    tooltip = print
    showInfo = print
    showWarning = print
    QDialog = object

ENV_PATHS = [
    r"D:\Projects\Anki_Vocab_Suite\.env",
    os.path.join(os.path.dirname(__file__), ".env")
]

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODELS = ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-flash", "deepseek-v4-pro"]


def read_env() -> dict:
    config = {
        "DEEPSEEK_API_KEY": "",
        "LLM_API_KEY": "",
        "LLM_BASE_URL": DEFAULT_BASE_URL,
        "LLM_MODEL": "deepseek-chat"
    }
    for path in ENV_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            config[k.strip()] = v.strip()
                break
            except Exception:
                pass
    return config


def save_env(api_key: str, base_url: str, model: str) -> bool:
    clean_base = base_url.strip().rstrip("/")
    if not clean_base:
        clean_base = DEFAULT_BASE_URL

    chat_url = f"{clean_base}/chat/completions" if not clean_base.endswith("/chat/completions") else clean_base

    content = (
        f"DEEPSEEK_API_KEY={api_key.strip()}\n"
        f"LLM_API_KEY={api_key.strip()}\n"
        f"LLM_BASE_URL={clean_base}\n"
        f"LLM_API_URL={chat_url}\n"
        f"LLM_MODEL={model.strip()}\n"
    )

    success = False
    for path in ENV_PATHS:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            success = True
        except Exception:
            pass

    sp_env = r"C:\Users\laptop\AppData\Roaming\Anki2\addons21\sync_pipeline\.env"
    try:
        if os.path.exists(os.path.dirname(sp_env)):
            with open(sp_env, "w", encoding="utf-8") as f:
                f.write(content)
    except Exception:
        pass

    return success


def fetch_deepseek_models(api_key: str, base_url: str = DEFAULT_BASE_URL) -> tuple[list[str], str]:
    if not api_key:
        return [], "No API key."

    clean_base = base_url.strip().rstrip("/")
    if "/chat/completions" in clean_base:
        clean_base = clean_base.replace("/chat/completions", "")
    if clean_base.endswith("/v1"):
        clean_base = clean_base[:-3]

    models_url = f"{clean_base}/models"
    req = urllib.request.Request(
        models_url,
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": "AnkiAddon/1.0"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", [])
            model_ids = [item["id"] for item in items if "id" in item]
            if model_ids:
                return model_ids, ""
            return DEFAULT_MODELS, "No model list returned."
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return [], f"HTTP {e.code}: {body[:80]}"
    except Exception as e:
        return [], f"Net err: {e}"


def test_deepseek_chat(api_key: str, base_url: str, model: str) -> tuple[bool, str, float]:
    clean_base = base_url.strip().rstrip("/")
    url = clean_base if clean_base.endswith("/chat/completions") else f"{clean_base}/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key.strip()}",
            "User-Agent": "AnkiAddon/1.0"
        }
    )

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            dur = (time.time() - t0) * 1000
            data = json.loads(resp.read().decode("utf-8"))
            reply = data["choices"][0]["message"]["content"].strip()
            return True, reply, dur
    except urllib.error.HTTPError as e:
        dur = (time.time() - t0) * 1000
        body = e.read().decode("utf-8", errors="replace")
        return False, f"HTTP {e.code}: {body[:80]}", dur
    except Exception as e:
        dur = (time.time() - t0) * 1000
        return False, str(e), dur


class DeepSeekSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚡ DeepSeek Config")
        self.resize(520, 360)

        self.current_config = read_env()
        self.fetched_models = list(DEFAULT_MODELS)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header = QLabel("⚡ DeepSeek Config", self)
        header.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        layout.addWidget(header)

        # Base URL
        layout.addWidget(QLabel("Base URL:", self))
        self.url_input = QLineEdit(self)
        self.url_input.setText(self.current_config.get("LLM_BASE_URL", DEFAULT_BASE_URL))
        self.url_input.setPlaceholderText("https://api.deepseek.com")
        layout.addWidget(self.url_input)

        # API Key
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("API Key:", self))
        key_layout.addStretch()

        self.chk_show_key = QCheckBox("Show", self)
        self.chk_show_key.toggled.connect(self.toggle_show_key)
        key_layout.addWidget(self.chk_show_key)
        layout.addLayout(key_layout)

        key_box = QHBoxLayout()
        self.key_input = QLineEdit(self)
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        existing_key = self.current_config.get("DEEPSEEK_API_KEY") or self.current_config.get("LLM_API_KEY", "")
        self.key_input.setText(existing_key)
        self.key_input.setPlaceholderText("sk-...")
        key_box.addWidget(self.key_input)

        btn_fetch = QPushButton("🔄 Fetch Models", self)
        btn_fetch.setStyleSheet("font-weight: bold; padding: 5px 12px;")
        btn_fetch.clicked.connect(self.on_fetch_models)
        key_box.addWidget(btn_fetch)
        layout.addLayout(key_box)

        # Model Selector
        layout.addWidget(QLabel("Active Model:", self))
        self.model_combo = QComboBox(self)
        self.model_combo.setEditable(True)
        layout.addWidget(self.model_combo)

        saved_model = self.current_config.get("LLM_MODEL", "deepseek-chat")
        self.update_model_combo(self.fetched_models, selected=saved_model)

        # Status
        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(self.status_label)

        layout.addStretch()

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_test = QPushButton("⚡ Ping Test", self)
        btn_test.clicked.connect(self.on_test_connection)
        btn_layout.addWidget(btn_test)

        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Save", self)
        btn_save.setStyleSheet("background: #2563eb; color: white; font-weight: bold; padding: 6px 18px; border-radius: 6px;")
        btn_save.clicked.connect(self.on_save)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

        if existing_key:
            self.on_fetch_models()

    def toggle_show_key(self, checked: bool):
        self.key_input.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def update_model_combo(self, models: list[str], selected: str = ""):
        self.model_combo.clear()
        for m in models:
            self.model_combo.addItem(m)
        if selected:
            idx = self.model_combo.findText(selected)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
            else:
                self.model_combo.addItem(selected)
                self.model_combo.setCurrentText(selected)

    def on_fetch_models(self):
        key = self.key_input.text().strip()
        url = self.url_input.text().strip() or DEFAULT_BASE_URL
        if not key:
            self.status_label.setText("⚠️ Enter key first.")
            return

        self.status_label.setText("Fetching...")
        self.setEnabled(False)

        def bg_work():
            return fetch_deepseek_models(key, url)

        def on_done(future):
            self.setEnabled(True)
            try:
                models, err = future.result()
                if models:
                    self.fetched_models = models
                    curr_selected = self.model_combo.currentText()
                    self.update_model_combo(models, selected=curr_selected or models[0])
                    self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")
                    self.status_label.setText(f"✓ {len(models)} models loaded.")
                else:
                    self.status_label.setStyleSheet("color: #ef4444;")
                    self.status_label.setText(f"Fail: {err}")
            except Exception as e:
                self.status_label.setStyleSheet("color: #ef4444;")
                self.status_label.setText(f"Err: {e}")

        mw.taskman.run_in_background(bg_work, on_done)

    def on_test_connection(self):
        key = self.key_input.text().strip()
        url = self.url_input.text().strip() or DEFAULT_BASE_URL
        model = self.model_combo.currentText().strip()
        if not key:
            showWarning("Enter API Key.")
            return
        if not model:
            showWarning("Select model.")
            return

        self.status_label.setStyleSheet("color: #6b7280;")
        self.status_label.setText(f"Testing {model}...")
        self.setEnabled(False)

        def bg_test():
            return test_deepseek_chat(key, url, model)

        def on_done(future):
            self.setEnabled(True)
            try:
                ok, res, dur = future.result()
                if ok:
                    self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")
                    self.status_label.setText(f"✓ OK ({dur:.0f}ms)")
                    tooltip(f"DeepSeek OK ({dur:.0f}ms)", period=1500)
                else:
                    self.status_label.setStyleSheet("color: #ef4444;")
                    self.status_label.setText(f"Fail: {res}")
            except Exception as e:
                self.status_label.setStyleSheet("color: #ef4444;")
                self.status_label.setText(f"Err: {e}")

        mw.taskman.run_in_background(bg_test, on_done)

    def on_save(self):
        key = self.key_input.text().strip()
        url = self.url_input.text().strip() or DEFAULT_BASE_URL
        model = self.model_combo.currentText().strip() or "deepseek-chat"

        if not key:
            showWarning("Enter API Key.")
            return

        if save_env(key, url, model):
            tooltip(f"Saved: {model}", period=1500)
            self.accept()
        else:
            showWarning("Save failed.")


def open_settings_dialog():
    dlg = DeepSeekSettingsDialog(mw)
    dlg.exec()


def setup_menu():
    if mw and hasattr(mw, "form") and hasattr(mw.form, "menuTools"):
        action = QAction("⚡ DeepSeek Settings...", mw)
        action.triggered.connect(open_settings_dialog)
        mw.form.menuTools.addAction(action)


if mw and hasattr(mw, "form") and mw.form:
    setup_menu()
elif gui_hooks and hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(setup_menu)
