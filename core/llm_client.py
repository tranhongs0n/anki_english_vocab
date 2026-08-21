import os
import json
import time
import urllib.request
try: from aqt import mw
except ImportError: mw = None

_CACHE = None
def get_path(f: str) -> str:
    d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f)

def get_prompt(cat: str, key: str = 'user', **kwargs) -> str:
    global _CACHE
    if _CACHE is None:
        p = get_path('prompts.json')
        try:
            with open(p, 'r', encoding='utf-8-sig') as f: _CACHE = json.load(f)
        except Exception: _CACHE = {}
    tpl = _CACHE.get(cat, {}).get(key, '')
    try: return tpl.format(**kwargs) if (tpl and kwargs) else tpl
    except Exception: return tpl

def get_llm_cfg() -> dict:
    cfg = {'base_url': 'https://api.deepseek.com', 'model': 'deepseek-v4-flash', 'candidate_models': [], 'timeout_seconds': 8.0, 'max_tokens': 300}
    if mw and mw.addonManager:
        cfg.update((mw.addonManager.getConfig('anki_vocab_suite') or {}).get('llm', {}))
    return cfg

def read_env() -> dict:
    c = get_llm_cfg()
    env = {'LLM_API_KEY': '', 'LLM_BASE_URL': c.get('base_url', ''), 'LLM_MODEL': c.get('model', '')}
    p = get_path('.env')
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                for l in f:
                    if '=' in l and not l.strip().startswith('#'):
                        k, v = l.strip().split('=', 1)
                        env[k.strip()] = v.strip()
        except Exception: pass
    return env

def save_env(key: str, base: str, model: str) -> bool:
    b = base.strip().rstrip('/') or get_llm_cfg().get('base_url', '')
    url = b if b.endswith('/chat/completions') else b + '/chat/completions'
    content = f'LLM_API_KEY={key.strip()}\nLLM_BASE_URL={b}\nLLM_API_URL={url}\nLLM_MODEL={model.strip()}\n'
    try:
        with open(get_path('.env'), 'w', encoding='utf-8') as f: f.write(content)
        return True
    except Exception: return False

def _http(url: str, key: str, payload: dict = None, to: float = 8.0) -> tuple[dict, str]:
    headers = {'Content-Type': 'application/json', 'User-Agent': 'AnkiVocab/1.0'}
    if key: headers['Authorization'] = 'Bearer ' + key.strip()
    data = json.dumps(payload).encode('utf-8') if payload else None
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method='POST' if data else 'GET')
        with urllib.request.urlopen(req, timeout=to) as resp:
            return json.loads(resp.read().decode('utf-8')), ''
    except Exception as e: return {}, str(e)

def call_llm(prompt: str, sys: str = '', max_tokens: int = 0, to: float = 0.0) -> tuple[str, str]:
    env, cfg = read_env(), get_llm_cfg()
    b = (env.get('LLM_BASE_URL') or cfg.get('base_url', '')).strip().rstrip('/')
    url = b if b.endswith('/chat/completions') else b + '/chat/completions'
    tokens = max_tokens or cfg.get('max_tokens', 300)
    timeout = to or cfg.get('timeout_seconds', 8.0)
    msgs = ([{'role': 'system', 'content': sys}] if sys else []) + [{'role': 'user', 'content': prompt}]
    
    models = [env.get('LLM_MODEL') or cfg.get('model', 'deepseek-v4-flash')]
    for m in cfg.get('candidate_models', []):
        if m and m not in models: models.append(m)

    last_err = ''
    for model in models:
        payload = {'model': model, 'messages': msgs, 'temperature': 0.0, 'max_tokens': tokens, 'thinking': {'type': 'disabled'}}
        data, err = _http(url, env.get('LLM_API_KEY', ''), payload, timeout)
        if not err and data:
            try:
                msg = data['choices'][0]['message']
                content = (msg.get('content') or msg.get('reasoning_content') or '').strip()
                if content: return content, ''
            except Exception: pass
        last_err = err
    return '', last_err

def ping_llm(key: str, base: str, model: str) -> tuple[bool, str, float]:
    b = (base or get_llm_cfg().get('base_url', '')).strip().rstrip('/')
    url = b if b.endswith('/chat/completions') else b + '/chat/completions'
    t0 = time.time()
    data, err = _http(url, key, {'model': model, 'messages': [{'role': 'user', 'content': 'ping'}], 'max_tokens': 20, 'thinking': {'type': 'disabled'}}, 6.0)
    dur = (time.time() - t0) * 1000
    if not err and data:
        try: return True, data['choices'][0]['message']['content'].strip(), dur
        except Exception: pass
    return False, err or 'Invalid format', dur

def fetch_models(key: str, base: str) -> tuple[list[str], str]:
    if not key: return [], 'No API key'
    b = (base or get_llm_cfg().get('base_url', '')).strip().rstrip('/').replace('/chat/completions', '')
    if b.endswith('/v1'): b = b[:-3]
    data, err = _http(b + '/models', key, None, 8.0)
    return ([i['id'] for i in data.get('data', []) if 'id' in i], '') if (not err and data) else ([], err)