"""
Ckey.vn Model Crawler & Optimizer
Fetches latest models from https://ckey.vn/llm-api?sort=price_low,
filters out Google/Gemini models, eliminates low-success-rate/low-request models,
and ranks them by Price (Ascending) -> Success Rate (Descending) -> Request Count (Descending).
"""

import os
import sys
import re
import json
import time
import urllib.request
from bs4 import BeautifulSoup

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "models_cache.json")
DEFAULT_MIN_SUCCESS = 80.0
DEFAULT_MIN_REQUESTS = 50

# Fallback sequence in case internet/ckey catalog is unreachable
HARDCODED_FALLBACKS = [
    "mimo-v2.5",
    "nemotron-3-ultra-free",
    "sypham98/qwen3.8-fast",
    "deepseek-v4-flash-free",
    "Ntthin/Grok-4.6",
    "Ntthin/grok-4.5_console",
    "mainnewnol/gpt-oss-120b",
    "openai/minimax-m3",
    "qwen3-coder-next",
    "openai/glm-5.2-free",
    "nemotron-3-ultra-550b-a55b",
    "openai/grok-4.5-free",
    "jjfkphong/grok-4.5",
    "nhatnam201104/deepseek-v4-flash",
    "tuanxedich28/gpt-oss-120b",
    "pthung310106/deepseek-v4-flash0731"
]


def fetch_ckey_models(max_pages: int = 20) -> list[dict]:
    """Crawl all ckey catalog pages without filter and sort by Price ASC -> Success Rate DESC -> Requests DESC."""
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

                    # STRICT RULE: NEVER USE GOOGLE / GEMINI
                    if "google" in family or "gemini" in name.lower() or "google" in name.lower():
                        continue

                    # Filter out models that don't support standard chat/completions or messages
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

                    # Parse peak RPS from card text (e.g. "Peak RPS 14/s")
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
            print(f"[!] Error crawling ckey page {page}: {e}")
            break

    # Load local latency stats if available
    local_stats = {}
    stats_file = os.path.join(os.path.dirname(CACHE_FILE), "models_stats.json")
    if os.path.exists(stats_file):
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                local_stats = json.load(f)
        except Exception:
            pass

    for m in all_models:
        s = local_stats.get(m["name"], {})
        m["avg_ms"] = s.get("avg_ms", 0.0)
        m["calls_count"] = s.get("total_calls", 0)

    # Rank criteria: Price ASC -> Success Rate DESC -> Requests DESC
    all_models.sort(key=lambda x: (x["price"], -x["success_rate"], -x["requests"]))
    return all_models


def update_models_cache(max_pages: int = 20) -> list[str]:
    """Fetch all models, save to data/models_cache.json, and return list of model names."""
    models = fetch_ckey_models(max_pages=max_pages)
    model_names = [m["name"] for m in models] if models else HARDCODED_FALLBACKS

    cache_data = {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "models_count": len(models),
        "model_names": model_names,
        "models_details": models
    }

    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[OK] Successfully cached {len(model_names)} ranked models to {CACHE_FILE}")
    except Exception as e:
        print(f"[!] Failed to write cache: {e}")

    return model_names


def get_ranked_models(auto_refresh_hours: int = 24) -> list[str]:
    """
    Get ranked model list. Reads from cache if recent, else crawls ckey.vn.
    Falls back to HARDCODED_FALLBACKS on any error.
    """
    if os.path.exists(CACHE_FILE):
        try:
            mtime = os.path.getmtime(CACHE_FILE)
            if (time.time() - mtime) < (auto_refresh_hours * 3600):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    names = data.get("model_names", [])
                    if names:
                        return names
        except Exception:
            pass

    # If cache missing or stale, refresh
    try:
        return update_models_cache()
    except Exception:
        return HARDCODED_FALLBACKS


def format_abbr(n: float) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{n:,.0f}" if isinstance(n, int) or n.is_integer() else f"{n:.1f}"


if __name__ == "__main__":
    print("Crawling ckey.vn for ALL models with Speed & Token metrics...")
    ranked = fetch_ckey_models(max_pages=20)
    print(f"\nFound {len(ranked)} models (non-Google, full metrics):\n")
    print(f"{'#':<3} {'Model Name':<38} {'Price':<7} {'Success':<9} {'Speed/RPS':<11} {'Tokens':<9} {'Tok/Req':<9} {'Requests'}")
    print("-" * 98)
    for idx, m in enumerate(ranked[:35], 1):
        speed_disp = f"{m.get('avg_ms', 0):.0f}ms" if m.get("avg_ms", 0) > 0 else (f"{m.get('peak_rps', 0):.0f}/s" if m.get("peak_rps", 0) > 0 else "-")
        tok_str = format_abbr(m.get("tokens", 0))
        tpr_str = format_abbr(m.get("tokens_per_req", 0))
        print(f"{idx:<3} {m['name']:<38} {m['price']:<7.0f} {m['success_rate']:<8.1f}% {speed_disp:<11} {tok_str:<9} {tpr_str:<9} {m['requests']:<10d}")

    update_models_cache(max_pages=20)
