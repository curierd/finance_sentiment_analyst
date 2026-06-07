"""Collect recent Xueqiu comments for every stock listed in
data/sections/laodeng.md and data/sections/CPO.md.

Output: xueqiu_data/raw/2026-06-07/sections.json
"""
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path('C:/Users/sverd/Desktop/finance_sentiment_analyst')
TARGET_DATE = '2026-06-07'
OUT_DIR = ROOT / 'xueqiu_data' / 'raw' / TARGET_DATE
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_FILE = OUT_DIR / 'sections.json'
PARTIAL_FILE = OUT_DIR / 'sections.partial.json'

SECTIONS = {
    'laodeng': [
        'SH510050', 'SH510300', 'SH510500', 'SH518800',
        'SH601398', 'SH601939', 'SH601288', 'SH600036',
        'SH600519', 'SZ000858', 'SZ000568', 'SH600900', 'SH601088',
    ],
    'CPO': [
        'SZ300308', 'SZ300502', 'SZ300394', 'SZ002281',
        'SH515880', 'SH515050', 'SZ159994', 'SZ159695',
        'SZ159507', 'SZ159511', 'SZ159583',
    ],
}

last_request = 0.0


def parse_json_stdout(stdout):
    s = re.sub(r'^Active code page: 65001\s*\r?\n', '', stdout)
    starts = [p for p in (s.find('['), s.find('{')) if p >= 0]
    if starts:
        s = s[min(starts):]
    return json.loads(s)


def run_xueqiu(arg_string, label):
    global last_request
    wait = max(0, 1.25 - (time.monotonic() - last_request))
    if wait:
        time.sleep(wait)
    cmd = f'opencli xueqiu {arg_string} -f json --window background --site-session persistent'
    print(f'[{label}] {cmd}', flush=True)
    last_request = time.monotonic()
    p = subprocess.run(
        cmd, shell=True, text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=240,
    )
    if p.stderr.strip():
        print(f'[{label}] stderr: {p.stderr.strip()[:300]}', flush=True)
    if p.returncode != 0:
        return None, {'returncode': p.returncode, 'stderr': p.stderr}
    try:
        return parse_json_stdout(p.stdout), None
    except Exception as e:
        return None, {'json_error': str(e), 'stdout': p.stdout[:300]}


def save(state):
    PARTIAL_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


state = {
    'target_date': TARGET_DATE,
    'platform': '雪球',
    'sources': ['data/sections/laodeng.md', 'data/sections/CPO.md'],
    'comments': {},
    'errors': [],
    'request_policy': 'sequential opencli xueqiu requests; >=1.25s between requests; no concurrency',
}

total = sum(len(v) for v in SECTIONS.values())
done = 0
for section, symbols in SECTIONS.items():
    for symbol in symbols:
        done += 1
        label = f'{done}/{total} {section}/{symbol}'
        comments, err = run_xueqiu(f'comments {symbol} --limit 30', label)
        if err:
            state['errors'].append({'section': section, 'symbol': symbol, 'error': err})
            state['comments'].setdefault(section, {})[symbol] = []
        else:
            state['comments'].setdefault(section, {})[symbol] = comments if isinstance(comments, list) else []
        save(state)

OUT_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'\nWrote {OUT_FILE}', flush=True)
