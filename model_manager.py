"""
LLM Model Manager UI for Anki (Ckey.vn)
Interactive Qt dialog inside Anki to view, filter, select, and prioritize
active models from ckey.vn based on price, success rate, latency (ms), and token volume.
"""

import os
import re
import json
import time
import urllib.request
import threading
from bs4 import BeautifulSoup

try:
    from aqt import mw, gui_hooks
    from aqt.utils import tooltip, showInfo
    from aqt.qt import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
        QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
        QCheckBox, Qt, QAction, QColor, QFont, QCoreApplication
    )
except ImportError:
    mw = None
    gui_hooks = None
    tooltip = print
    showInfo = print
    QDialog = object

DATA_DIR = r"D:\Projects\Anki_Vocab_Suite\data"
MODELS_CACHE_FILE = os.path.join(DATA_DIR, "models_cache.json")
ACTIVE_MODELS_FILE = os.path.join(DATA_DIR, "active_models.json")
STATS_FILE = os.path.join(DATA_DIR, "models_stats.json")

DEFAULT_FALLBACK_MODELS = [
    "mimo-v2.5",
    "nemotron-3-ultra-free",
    "sypham98/qwen3.8-fast",
    "deepseek-v4-flash-free",
    "openai/minimax-m3",
    "qwen3-coder-next",
    "openai/glm-5.2-free",
    "nemotron-3-ultra-550b-a55b",
    "openai/grok-4.5-free",
    "Ntthin/Grok-4.6",
    "Ntthin/grok-4.5_console",
    "mainnewnol/gpt-oss-120b",
    "jjfkphong/grok-4.5",
    "nhatnam201104/deepseek-v4-flash",
    "tuanxedich28/gpt-oss-120b",
    "pthung310106/deepseek-v4-flash0731"
]


def load_local_stats() -> dict:
    """Load local performance stats recorded from actual Anki calls."""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def load_cached_catalog() -> list[dict]:
    """Load full crawled catalog from models_cache.json and merge with local latency stats."""
    models = []
    if os.path.exists(MODELS_CACHE_FILE):
        try:
            with open(MODELS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                models = data.get("models_details", [])
        except Exception:
            pass

    local_stats = load_local_stats()
    for m in models:
        s = local_stats.get(m.get("name", ""), {})
        m["avg_ms"] = s.get("avg_ms", 0.0)
        m["calls_count"] = s.get("total_calls", 0)

    return models


def load_active_models() -> list[str]:
    """Load user's chosen active model sequence."""
    if os.path.exists(ACTIVE_MODELS_FILE):
        try:
            with open(ACTIVE_MODELS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                names = data.get("selected_models", [])
                if names:
                    return names
        except Exception:
            pass

    cached = load_cached_catalog()
    if cached:
        return [m["name"] for m in cached[:15]]
    return DEFAULT_FALLBACK_MODELS


def save_active_models(model_names: list[str]) -> bool:
    """Save selected active model sequence."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        payload = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(model_names),
            "selected_models": model_names
        }
        with open(ACTIVE_MODELS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[!] Error saving active models: {e}")
        return False


def crawl_ckey_catalog(max_pages: int = 20) -> list[dict]:
    """Crawl ckey.vn public catalog for all non-Google models with performance metrics."""
    all_models = []
    seen = set()
    page = 1
    total_pages = max_pages

    while page <= total_pages:
        url = f"https://ckey.vn/ajax/apiai-public-catalog?lang=vi&page={page}&per_page=50&sort=price_low"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                total_pages = min(max_pages, data.get("page_count", max_pages))
                cards_html = data.get("cards_html", "")
                if not cards_html:
                    break

                soup = BeautifulSoup(cards_html, "html.parser")
                cards = soup.find_all("article", class_="apiai-model-card")
                if not cards:
                    break

                for card in cards:
                    model = card.get("data-model", "").strip()
                    copy_btn = card.find(attrs={"data-copy-model": True})
                    name = (copy_btn["data-copy-model"].strip() if copy_btn else model) or model
                    if not name or name in seen:
                        continue

                    family = card.get("data-family", "").lower()
                    supported_paths = card.get("data-supported-paths", "").lower()

                    if "google" in family or "gemini" in name.lower() or "google" in name.lower():
                        continue

                    if supported_paths and "chat/completions" not in supported_paths and "messages" not in supported_paths:
                        continue

                    try:
                        price = float(card.get("data-price", 0))
                    except ValueError:
                        price = 999999.0

                    try:
                        success_rate = float(card.get("data-success", 0))
                    except ValueError:
                        success_rate = 0.0

                    try:
                        requests = int(card.get("data-requests", 0))
                    except ValueError:
                        requests = 0

                    try:
                        tokens = int(card.get("data-tokens", 0))
                    except ValueError:
                        tokens = 0

                    card_text = card.get_text(separator=' ', strip=True)
                    rps_match = re.search(r'Peak\s+RPS\s*(\d+(?:\.\d+)?)\s*/s', card_text, re.IGNORECASE)
                    peak_rps = float(rps_match.group(1)) if rps_match else 0.0
                    tokens_per_req = round(tokens / requests, 1) if requests > 0 else 0.0

                    seen.add(name)
                    all_models.append({
                        "name": name,
                        "price": price,
                        "success_rate": success_rate,
                        "requests": requests,
                        "tokens": tokens,
                        "peak_rps": peak_rps,
                        "tokens_per_req": tokens_per_req,
                        "family": family,
                        "pricing": card.get("data-pricing", "")
                    })
            page += 1
        except Exception as e:
            print(f"[!] Error crawling page {page}: {e}")
            break

    local_stats = load_local_stats()
    for m in all_models:
        s = local_stats.get(m["name"], {})
        m["avg_ms"] = s.get("avg_ms", 0.0)
        m["calls_count"] = s.get("total_calls", 0)

    all_models.sort(key=lambda x: (x["price"], -x["success_rate"], -x["requests"]))

    # Save cache
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        cache_data = {
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models_count": len(all_models),
            "model_names": [m["name"] for m in all_models],
            "models_details": all_models
        }
        with open(MODELS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return all_models


def format_num_abbr(n: float) -> str:
    """Format large numbers like 3.06B, 27.3K."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}" if isinstance(n, int) or n.is_integer() else f"{n:.1f}"


class ModelManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM Model Manager")
        self.resize(1020, 700)

        self.catalog = load_cached_catalog()
        self.active_models = set(load_active_models())
        self.active_order = {name: idx for idx, name in enumerate(load_active_models())}
        self.current_sort = "default"  # "default", "speed", "price", "success", "tokens"

        self.init_ui()
        self.populate_table()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Title and stats header
        header_layout = QHBoxLayout()
        title_label = QLabel("⚡ Active Models", self)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header_layout.addWidget(title_label)

        self.status_label = QLabel(self)
        self.status_label.setStyleSheet("color: #10b981; font-weight: bold;")
        header_layout.addStretch()
        header_layout.addWidget(self.status_label)
        layout.addLayout(header_layout)

        # Search and quick action presets
        tools_layout = QHBoxLayout()
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("🔍 Search models...")
        self.search_input.textChanged.connect(self.filter_table)
        tools_layout.addWidget(self.search_input, stretch=2)

        btn_speed = QPushButton("⚡ Sort Speed", self)
        btn_speed.clicked.connect(self.sort_by_speed)
        tools_layout.addWidget(btn_speed)

        btn_price = QPushButton("💰 Sort Price", self)
        btn_price.clicked.connect(self.sort_by_price)
        tools_layout.addWidget(btn_price)

        btn_succ = QPushButton("🎯 Sort Success", self)
        btn_succ.clicked.connect(self.sort_by_success)
        tools_layout.addWidget(btn_succ)

        btn_tok = QPushButton("📈 Sort Tokens", self)
        btn_tok.clicked.connect(self.sort_by_tokens)
        tools_layout.addWidget(btn_tok)

        btn_free = QPushButton("0₫ Free", self)
        btn_free.clicked.connect(self.select_free_only)
        tools_layout.addWidget(btn_free)

        btn_top15 = QPushButton("Top 15", self)
        btn_top15.clicked.connect(self.select_top_recommended)
        tools_layout.addWidget(btn_top15)

        btn_clear = QPushButton("Clear", self)
        btn_clear.clicked.connect(self.clear_all_selection)
        tools_layout.addWidget(btn_clear)

        btn_refresh = QPushButton("🔄 Refresh", self)
        btn_refresh.setStyleSheet("font-weight: bold;")
        btn_refresh.clicked.connect(self.refresh_from_ckey)
        tools_layout.addWidget(btn_refresh)

        layout.addLayout(tools_layout)

        # Models Table with 8 informative columns
        self.table = QTableWidget(self)
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "Active", "Model Name", "Price (₫)", "Success", "Speed (ms / RPS)", "Total Tokens", "Tokens/Req", "Requests"
        ])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, stretch=1)

        # Bottom buttons: Move Up, Move Down, Save
        btn_box = QHBoxLayout()
        btn_up = QPushButton("⬆️ Up", self)
        btn_up.clicked.connect(self.move_item_up)
        btn_box.addWidget(btn_up)

        btn_down = QPushButton("⬇️ Down", self)
        btn_down.clicked.connect(self.move_item_down)
        btn_box.addWidget(btn_down)

        btn_box.addStretch()

        btn_cancel = QPushButton("Cancel", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Save & Apply", self)
        btn_save.setStyleSheet("background: #2563eb; color: white; font-weight: bold; padding: 6px 18px; border-radius: 6px;")
        btn_save.clicked.connect(self.save_and_apply)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def populate_table(self):
        """Populate table with catalog sorted by active priority first, then chosen sort key."""
        if not self.catalog:
            self.catalog = crawl_ckey_catalog(max_pages=4)

        def sort_key(item):
            name = item["name"]
            is_active = name in self.active_models
            active_rank = (0, self.active_order.get(name, 9999)) if is_active else (1,)

            if self.current_sort == "speed":
                # If avg_ms recorded, prefer fastest (lowest ms), else highest peak RPS
                ms = item.get("avg_ms", 0.0)
                speed_score = ms if ms > 0 else (10000.0 - item.get("peak_rps", 0.0) * 100)
                return active_rank + (speed_score, item.get("price", 9999), -item.get("success_rate", 0))

            elif self.current_sort == "price":
                return active_rank + (item.get("price", 9999), -item.get("success_rate", 0), -item.get("requests", 0))

            elif self.current_sort == "success":
                return active_rank + (-item.get("success_rate", 0), item.get("price", 9999), -item.get("requests", 0))

            elif self.current_sort == "tokens":
                return active_rank + (-item.get("tokens", 0), -item.get("requests", 0))

            # Default: price -> success -> requests
            return active_rank + (item.get("price", 9999), -item.get("success_rate", 0), -item.get("requests", 0))

        sorted_models = sorted(self.catalog, key=sort_key)

        self.table.setRowCount(len(sorted_models))
        for row, m in enumerate(sorted_models):
            name = m["name"]
            is_active = name in self.active_models

            # Col 0: Checkbox
            chk = QCheckBox()
            chk.setChecked(is_active)
            chk.stateChanged.connect(lambda state, n=name: self.on_check_changed(n, state))
            self.table.setCellWidget(row, 0, chk)

            # Col 1: Model Name
            item_name = QTableWidgetItem(name)
            if is_active:
                item_name.setFont(QFont("Arial", weight=QFont.Weight.Bold))
            self.table.setItem(row, 1, item_name)

            # Col 2: Price
            price_val = m.get("price", 0)
            item_price = QTableWidgetItem(f"{price_val:,.0f} ₫" if price_val > 0 else "0 ₫ (FREE)")
            if price_val == 0:
                item_price.setForeground(QColor("#10b981"))
                item_price.setFont(QFont("Arial", weight=QFont.Weight.Bold))
            self.table.setItem(row, 2, item_price)

            # Col 3: Success Rate
            sr = m.get("success_rate", 0.0)
            item_sr = QTableWidgetItem(f"{sr:.1f}%")
            if sr >= 95.0:
                item_sr.setForeground(QColor("#10b981"))
            elif sr < 80.0:
                item_sr.setForeground(QColor("#ef4444"))
            self.table.setItem(row, 3, item_sr)

            # Col 4: Speed (Avg ms or Peak RPS)
            avg_ms = m.get("avg_ms", 0.0)
            peak_rps = m.get("peak_rps", 0.0)
            if avg_ms > 0:
                speed_str = f"⚡ {avg_ms:.0f} ms"
            elif peak_rps > 0:
                speed_str = f"~{peak_rps:.0f} RPS"
            else:
                speed_str = "-"
            item_speed = QTableWidgetItem(speed_str)
            if avg_ms > 0 and avg_ms <= 800:
                item_speed.setForeground(QColor("#10b981"))
            self.table.setItem(row, 4, item_speed)

            # Col 5: Total Tokens
            tokens_val = m.get("tokens", 0)
            item_tok = QTableWidgetItem(format_num_abbr(tokens_val))
            self.table.setItem(row, 5, item_tok)

            # Col 6: Tokens / Req
            tok_per_req = m.get("tokens_per_req", 0.0)
            item_tpr = QTableWidgetItem(format_num_abbr(tok_per_req))
            self.table.setItem(row, 6, item_tpr)

            # Col 7: Requests
            req_cnt = m.get("requests", 0)
            item_req = QTableWidgetItem(f"{req_cnt:,}")
            self.table.setItem(row, 7, item_req)

        self.update_status_count()

    def on_check_changed(self, model_name: str, state: int):
        if state == 2:  # Checked
            self.active_models.add(model_name)
            if model_name not in self.active_order:
                self.active_order[model_name] = max(self.active_order.values(), default=-1) + 1
        else:
            self.active_models.discard(model_name)
            self.active_order.pop(model_name, None)
        self.update_status_count()

    def update_status_count(self):
        self.status_label.setText(f"✓ {len(self.active_models)} models selected")

    def filter_table(self, query: str):
        query = query.strip().lower()
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 1)
            name = name_item.text().lower() if name_item else ""
            self.table.setRowHidden(row, query not in name if query else False)

    def sort_by_speed(self):
        self.current_sort = "speed"
        self.populate_table()

    def sort_by_price(self):
        self.current_sort = "price"
        self.populate_table()

    def sort_by_success(self):
        self.current_sort = "success"
        self.populate_table()

    def sort_by_tokens(self):
        self.current_sort = "tokens"
        self.populate_table()

    def select_free_only(self):
        self.active_models.clear()
        self.active_order.clear()
        for idx, m in enumerate(self.catalog):
            if m.get("price", 0) == 0 and m.get("success_rate", 0) >= 80.0:
                self.active_models.add(m["name"])
                self.active_order[m["name"]] = idx
        self.populate_table()

    def select_top_recommended(self):
        self.active_models.clear()
        self.active_order.clear()
        for idx, m in enumerate(self.catalog[:15]):
            self.active_models.add(m["name"])
            self.active_order[m["name"]] = idx
        self.populate_table()

    def clear_all_selection(self):
        self.active_models.clear()
        self.active_order.clear()
        self.populate_table()

    def move_item_up(self):
        row = self.table.currentRow()
        if row <= 0:
            return
        curr_name = self.table.item(row, 1).text()
        prev_name = self.table.item(row - 1, 1).text()

        c_order = self.active_order.get(curr_name, row)
        p_order = self.active_order.get(prev_name, row - 1)
        self.active_order[curr_name] = min(c_order, p_order) - 1
        self.active_order[prev_name] = max(c_order, p_order)
        self.populate_table()
        self.table.selectRow(max(0, row - 1))

    def move_item_down(self):
        row = self.table.currentRow()
        if row < 0 or row >= self.table.rowCount() - 1:
            return
        curr_name = self.table.item(row, 1).text()
        next_name = self.table.item(row + 1, 1).text()

        c_order = self.active_order.get(curr_name, row)
        n_order = self.active_order.get(next_name, row + 1)
        self.active_order[curr_name] = max(c_order, n_order) + 1
        self.active_order[next_name] = min(c_order, n_order)
        self.populate_table()
        self.table.selectRow(min(self.table.rowCount() - 1, row + 1))

    def refresh_from_ckey(self):
        tooltip("Refreshing...", period=1500)
        self.setEnabled(False)

        def bg_crawl():
            return crawl_ckey_catalog(max_pages=20)

        def on_done(future):
            self.setEnabled(True)
            try:
                self.catalog = future.result()
                self.populate_table()
                tooltip(f"Refreshed ({len(self.catalog)} models)", period=1500)
            except Exception as e:
                showInfo(f"Refresh error: {e}")

        mw.taskman.run_in_background(bg_crawl, on_done)

    def save_and_apply(self):
        if not self.active_models:
            showInfo("Select at least 1 model.")
            return

        ordered_selected = []
        for row in range(self.table.rowCount()):
            name = self.table.item(row, 1).text()
            if name in self.active_models:
                ordered_selected.append(name)

        if save_active_models(ordered_selected):
            tooltip(f"Saved {len(ordered_selected)} models.", period=2000)
            self.accept()
        else:
            showInfo("Save failed.")


def open_model_manager():
    dlg = ModelManagerDialog(mw)
    dlg.exec()


def setup_menu():
    if mw and hasattr(mw, "form") and hasattr(mw.form, "menuTools"):
        action = QAction("⚡ LLM Model Manager...", mw)
        action.triggered.connect(open_model_manager)
        mw.form.menuTools.addAction(action)


if mw and hasattr(mw, "form") and mw.form:
    setup_menu()
elif gui_hooks and hasattr(gui_hooks, "main_window_did_init"):
    gui_hooks.main_window_did_init.append(setup_menu)
