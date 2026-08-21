"""
Real-time response time and token metrics tracker for LLM models.
Saves and updates live performance stats in D:\\Projects\\Anki_Vocab_Suite\\data\\models_stats.json.
"""

import os
import json
import time
import threading

STATS_FILE = r"D:\Projects\Anki_Vocab_Suite\data\models_stats.json"
_lock = threading.Lock()
_stats_cache = {}


def load_stats() -> dict:
    global _stats_cache
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                _stats_cache = json.load(f)
                return _stats_cache
        except Exception:
            pass
    return _stats_cache


def save_stats():
    try:
        os.makedirs(os.path.dirname(STATS_FILE), exist_ok=True)
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(_stats_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def record_model_call(model_name: str, duration_ms: float, success: bool = True, tokens: int = 0):
    """Record response time (ms) and success status for an actual model call."""
    if not model_name:
        return

    with _lock:
        load_stats()
        stats = _stats_cache.get(model_name, {
            "total_calls": 0,
            "success_calls": 0,
            "failed_calls": 0,
            "avg_ms": 0.0,
            "min_ms": 999999.0,
            "max_ms": 0.0,
            "last_ms": 0.0,
            "total_tokens": 0,
            "last_used": ""
        })

        stats["total_calls"] += 1
        if success:
            stats["success_calls"] += 1
            dur = round(duration_ms, 1)
            stats["last_ms"] = dur
            stats["min_ms"] = round(min(stats["min_ms"], dur), 1)
            stats["max_ms"] = round(max(stats["max_ms"], dur), 1)
            
            # Cumulative moving average
            n = stats["success_calls"]
            prev_avg = stats["avg_ms"]
            stats["avg_ms"] = round((prev_avg * (n - 1) + dur) / n, 1)
            if tokens > 0:
                stats["total_tokens"] += tokens
        else:
            stats["failed_calls"] += 1

        stats["last_used"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _stats_cache[model_name] = stats
        save_stats()


def get_model_latency(model_name: str) -> float:
    """Return average response time in ms for model, or 0.0 if not yet called."""
    with _lock:
        stats = load_stats().get(model_name)
        if stats and stats.get("success_calls", 0) > 0:
            return stats.get("avg_ms", 0.0)
    return 0.0
