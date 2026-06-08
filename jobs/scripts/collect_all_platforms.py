"""Collect comments from Bilibili, Xiaohongshu, and Xueqiu.

Output:
- comments/bilibili_YYYY-MM-DD.json
- comments/xiaohongshu_YYYY-MM-DD.json
- comments/xueqiu_YYYY-MM-DD.json
- intermediate/  for partial files
"""
import json
import re
import subprocess
import time
import datetime
from pathlib import Path

ROOT = Path('/home/rjh/finance_sentiment_analyst')
TODAY = datetime.date.today().isoformat()
COMMENTS_DIR = ROOT / 'comments'
INTERMEDIATE_DIR = ROOT / 'intermediate'
COMMENTS_DIR.mkdir(parents=True, exist_ok=True)
INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

# Parse Bilibili UP list
BILIBILI_UP_MD = ROOT / 'data' / 'bilibili-finance-up.md'
BILIBILI_UPS = []
BILIBILI_BLACKLIST = []

if BILIBILI_UP_MD.exists():
    md_text = BILIBILI_UP_MD.read_text(encoding='utf-8')
    in_ups = False
    in_blacklist = False
    for line in md_text.split('\n'):
        line = line.strip()
        if line.startswith('## 个人UP主'):
            in_ups = True
            in_blacklist = False
            continue
        if line.startswith('## up黑名单'):
            in_ups = False
            in_blacklist = True
            continue
        if line.startswith('##'):
            in_ups = False
            in_blacklist = False
            continue
        if line.startswith('|') and (in_ups or in_blacklist):
            # Parse table row
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 3 and parts[1] != 'UP主':
                uid = parts[2]
                name = parts[1]
                if uid and uid.isdigit():
                    if in_ups:
                        BILIBILI_UPS.append({'uid': uid, 'name': name})
                    elif in_blacklist:
                        BILIBILI_BLACKLIST.append({'uid': uid, 'name': name})

# Filter out blacklisted UIDs
blacklist_uids = {u['uid'] for u in BILIBILI_BLACKLIST}
BILIBILI_UPS = [u for u in BILIBILI_UPS if u['uid'] not in blacklist_uids]
print(f'Bilibili: {len(BILIBILI_UPS)} UP主, {len(BILIBILI_BLACKLIST)} 黑名单')

# Parse Xueqiu sections
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

# Parse Xiaohongshu UP list
XIAOHONGSHU_UP_MD = ROOT / 'data' / 'xiaohongshu-finance-up.md'
XIAOHONGSHU_UPS = []

if XIAOHONGSHU_UP_MD.exists():
    md_text = XIAOHONGSHU_UP_MD.read_text(encoding='utf-8')
    for line in md_text.split('\n'):
        line = line.strip()
        if line.startswith('|'):
            parts = [p.strip() for p in line.split('|')[1:-1]]
            if len(parts) >= 3 and parts[0] != '博主昵称':
                user_id = parts[1]
                if user_id and user_id != '用户ID':
                    XIAOHONGSHU_UPS.append({'user_id': user_id, 'nickname': parts[0]})

print(f'Xiaohongshu: {len(XIAOHONGSHU_UPS)} 博主')

last_request = 0.0


def parse_json_stdout(stdout):
    s = re.sub(r'^Active code page: 65001\s*\r?\n', '', stdout)
    s = re.sub(r'^.*?CLI output:\s*', '', s, flags=re.DOTALL)
    starts = [p for p in (s.find('['), s.find('{')) if p >= 0]
    if starts:
        s = s[min(starts):]
    try:
        result = json.loads(s)
        # Handle xhs format where data is in result.get('data', {}).get('items', [])
        if isinstance(result, dict) and 'ok' in result and result.get('ok'):
            if 'data' in result and 'items' in result['data']:
                return result['data']['items']
            elif 'data' in result and 'comments' in result['data']:
                return result['data']['comments']
            elif 'data' in result:
                return result['data']
        return result
    except Exception:
        # Try to find JSON object/array with regex
        m = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', s)
        if m:
            result = json.loads(m.group(1))
            if isinstance(result, dict) and 'ok' in result and result.get('ok'):
                if 'data' in result and 'items' in result['data']:
                    return result['data']['items']
                elif 'data' in result and 'comments' in result['data']:
                    return result['data']['comments']
                elif 'data' in result:
                    return result['data']
            return result
        raise


def run_cmd(cmd, label, min_interval=1.1):
    global last_request
    wait = max(0, min_interval - (time.monotonic() - last_request))
    if wait:
        time.sleep(wait)
    print(f'[{label}] {cmd}', flush=True)
    last_request = time.monotonic()
    p = subprocess.run(
        cmd, shell=True, text=True, encoding='utf-8', errors='replace',
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300,
    )
    if p.stderr.strip():
        print(f'[{label}] stderr: {p.stderr.strip()[:400]}', flush=True)
    if p.returncode != 0:
        return None, {'returncode': p.returncode, 'stderr': p.stderr}
    try:
        return parse_json_stdout(p.stdout), None
    except Exception as e:
        return None, {'json_error': str(e), 'stdout': p.stdout[:500]}


def save_state(state, path):
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')


# ------------------------------
# Bilibili collection
# ------------------------------
print('\n--- Starting Bilibili collection ---')
bili_state = {
    'target_date': TODAY,
    'platform': 'B站',
    'sources': ['data/bilibili-finance-up.md'],
    'ups': BILIBILI_UPS,
    'blacklist': BILIBILI_BLACKLIST,
    'videos': [],
    'comments': [],
    'errors': [],
    'request_policy': 'sequential opencli bilibili requests; >=1.1s between requests',
}

BILI_PARTIAL = INTERMEDIATE_DIR / f'bilibili_{TODAY}.partial.json'
BILI_OUT = COMMENTS_DIR / f'bilibili_{TODAY}.json'

for i, up in enumerate(BILIBILI_UPS):
    label = f'Bilibili {i+1}/{len(BILIBILI_UPS)} {up["name"]}'
    # Get UP's recent videos
    videos, err = run_cmd(f'opencli bilibili user-videos {up["uid"]} -f json --window background --site-session persistent', label + ' videos')
    if err:
        bili_state['errors'].append({'up': up, 'type': 'user-videos', 'error': err})
        save_state(bili_state, BILI_PARTIAL)
        continue
    if not isinstance(videos, list):
        videos = []

    # Add videos with up info
    for video in videos:
        video['_up'] = up
    bili_state['videos'].extend(videos)

    # Get comments for each video (only recent 3 videos to avoid being blocked)
    for video in videos[:3]:
        url = video.get('url', '')
        # Extract BV id from URL
        bv_match = re.search(r'/video/(BV[^/]+)', url)
        if not bv_match:
            continue
        bvid = bv_match.group(1)

        comments, err = run_cmd(f'opencli bilibili comments {bvid} -f json --window background --site-session persistent', label + f' comments {bvid}')
        if err:
            bili_state['errors'].append({'up': up, 'video': bvid, 'type': 'comments', 'error': err})
            continue
        if isinstance(comments, list):
            for c in comments:
                c['_up'] = up
                c['_video'] = video
                c['_video_bvid'] = bvid
                bili_state['comments'].append(c)
    save_state(bili_state, BILI_PARTIAL)

save_state(bili_state, BILI_OUT)
print(f'Wrote {BILI_OUT}')


# ------------------------------
# Xueqiu collection
# ------------------------------
print('\n--- Starting Xueqiu collection ---')
xueqiu_state = {
    'target_date': TODAY,
    'platform': '雪球',
    'sources': ['data/sections/laodeng.md', 'data/sections/CPO.md'],
    'sections': SECTIONS,
    'comments': {},
    'errors': [],
    'request_policy': 'sequential opencli xueqiu requests; >=1.25s between requests',
}

XUEQIU_PARTIAL = INTERMEDIATE_DIR / f'xueqiu_{TODAY}.partial.json'
XUEQIU_OUT = COMMENTS_DIR / f'xueqiu_{TODAY}.json'

total = sum(len(v) for v in SECTIONS.values())
done = 0
for section, symbols in SECTIONS.items():
    xueqiu_state['comments'][section] = {}
    for symbol in symbols:
        done += 1
        label = f'Xueqiu {done}/{total} {section}/{symbol}'
        comments, err = run_cmd(f'opencli xueqiu comments {symbol} -f json --window background --site-session persistent', label, min_interval=1.25)
        if err:
            xueqiu_state['errors'].append({'section': section, 'symbol': symbol, 'error': err})
            xueqiu_state['comments'][section][symbol] = []
        else:
            xueqiu_state['comments'][section][symbol] = comments if isinstance(comments, list) else []
        save_state(xueqiu_state, XUEQIU_PARTIAL)

save_state(xueqiu_state, XUEQIU_OUT)
print(f'Wrote {XUEQIU_OUT}')


# ------------------------------
# Xiaohongshu collection
# ------------------------------
print('\n--- Starting Xiaohongshu collection ---')
xhs_state = {
    'target_date': TODAY,
    'platform': '小红书',
    'sources': ['data/xiaohongshu-finance-up.md'],
    'search_keywords': ['股票', 'A股', '基金', '投资', '理财', '财经', '炒股'],
    'notes': [],
    'comments': [],
    'errors': [],
    'request_policy': 'sequential xhs search requests; >=1.1s between requests',
}

XHS_PARTIAL = INTERMEDIATE_DIR / f'xiaohongshu_{TODAY}.partial.json'
XHS_OUT = COMMENTS_DIR / f'xiaohongshu_{TODAY}.json'

for keyword in xhs_state['search_keywords']:
    label = f'Xiaohongshu {keyword}'
    notes, err = run_cmd(f'xhs search "{keyword}" --json', label)
    if err:
        xhs_state['errors'].append({'keyword': keyword, 'type': 'search', 'error': err})
        save_state(xhs_state, XHS_PARTIAL)
        continue

    if isinstance(notes, list):
        for note in notes:
            note['_keyword'] = keyword
        xhs_state['notes'].extend(notes)

    save_state(xhs_state, XHS_PARTIAL)

    # Now try to get comments for up to 3 notes from this search
    notes_to_process = notes[:3] if isinstance(notes, list) else []
    for i, note in enumerate(notes_to_process):
        note_id = note.get('note_id', '') or note.get('id', '')
        if not note_id:
            # Try to extract from url
            url = note.get('url', '')
            if '/discovery/item/' in url:
                note_id = url.split('/discovery/item/')[-1].split('?')[0]

        if not note_id:
            continue

        comments, err2 = run_cmd(f'xhs comments {note_id} --json', f'{label} comments {i+1}')
        if err2:
            xhs_state['errors'].append({'keyword': keyword, 'note_id': note_id, 'type': 'comments', 'error': err2})
            continue

        if isinstance(comments, list):
            for comment in comments:
                comment['_keyword'] = keyword
                comment['_note_id'] = note_id
                comment['_note'] = note
            xhs_state['comments'].extend(comments)

        save_state(xhs_state, XHS_PARTIAL)

save_state(xhs_state, XHS_OUT)
print(f'Wrote {XHS_OUT}')


print('\n--- Collection complete ---')
print(f'Bilibili: {len(bili_state["comments"])} comments from {len(bili_state["videos"])} videos')
xueqiu_count = sum(len(cs) for section in xueqiu_state['comments'].values() for cs in section.values())
print(f'Xueqiu: {xueqiu_count} comments')
print(f'Xiaohongshu: {len(xhs_state["comments"])} comments from {len(xhs_state["notes"])} notes')

