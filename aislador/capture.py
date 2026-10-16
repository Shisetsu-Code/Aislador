"""Fresh demo acquisition, followed by the existing offline isolation pipeline.

The recorder never replays a HAR, clicks controls or submits bets. Raw captures
and the durable queue are private; analysis never implies runtime coverage.
"""
import base64
import json
import time
import sqlite3
import os
from collections import deque
from contextlib import closing, contextmanager
from pathlib import Path
from urllib.parse import urlsplit, urlencode

from .cli import run_extract
from .profiles import get_profiles
from .har import load_har
from .codecs.playtech import EVIDENCE_REVISION
from .sanitize import clean, digest, safe_url


def validate_urls(urls):
    result = []
    for url in urls:
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            raise ValueError('Se requieren URLs HTTP(S) demo sin credenciales incrustadas.')
        if url not in result:result.append(url)
    if not result:raise ValueError('Faltan URLs demo para capturar.')
    return result


def tester_spin_urls(database, provider, limit=5):
    """Read pending catalog entries, interleave known launch engine families.

    Playtech codes are published catalog identifiers, never translated titles.
    Other providers retain the public catalog page; discovery may stop there.
    """
    path = Path(database).resolve()
    if not path.is_file():raise ValueError('No existe la base de Tester-Spin.')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as con:
        rows = con.execute("SELECT slug,url,symbol FROM games WHERE provider=? AND last_status NOT IN ('OK','OK_MANUAL') ORDER BY slug", (provider,)).fetchall()
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        excluded = {r[0] for r in con.execute('SELECT slug FROM catalog_exclusions WHERE provider=?', (provider,))} if 'catalog_exclusions' in tables else set()
    groups = {}
    # Deterministic sampling avoids an alphabetical sweep through similar titles.
    for slug, url, symbol in sorted(rows, key=lambda row: digest(row[0])):
        if slug in excluded:continue
        family = 'public_catalog'
        if provider == 'playtech' and symbol:
            family = 'gpas' if symbol.startswith('gpas_') else 'pop' if symbol.startswith('pop_') else 'ngm'
            url = 'https://cachedownload.playtechone.com/ngmdesktop/casinoclient.html?' + urlencode({'game': symbol, 'preferedmode': 'offline', 'real': '0'})
        groups.setdefault(family, deque()).append(url)
    result = []
    if limit is None:limit=len(rows)
    while len(result) < limit and any(groups.values()):
        for group in groups.values():
            if group and len(result) < limit:result.append(group.popleft())
    return result


def record_demo(url, target, seconds, headed=False):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError('La captura requiere instalar aislador-har[capture] y Chromium de Playwright.') from exc
    frames = []; warnings = []; size = 0; sockets = 0
    def attach_page(page):
        def attach_socket(ws):
            nonlocal sockets
            sockets += 1
            connection = str(sockets) + ':' + digest(ws.url)[:12]
            def frame(direction, payload):
                nonlocal size
                encoded = isinstance(payload, bytes)
                text = base64.b64encode(payload).decode('ascii') if encoded else payload
                if len(frames) >= 20000 or size + len(text) > 64 * 1024 * 1024:
                    if 'WS_CAPTURE_LIMIT' not in warnings:warnings.append('WS_CAPTURE_LIMIT')
                    return
                size += len(text)
                item = {'url': ws.url, 'connectionId': connection, 'direction': direction,
                        'timestamp': time.time(), 'payload': text, 'opcode': 2 if encoded else 1}
                if encoded:item['encoding'] = 'base64'
                frames.append(item)
            ws.on('framesent', lambda payload: frame('sent', payload))
            ws.on('framereceived', lambda payload: frame('received', payload))
        page.on('websocket', attach_socket)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        try:
            context = browser.new_context(record_har_path=str(target), record_har_content='embed', record_har_mode='full')
            context.on('page', attach_page)
            try:
                page = context.new_page()
                try:page.goto(url, wait_until='domcontentloaded', timeout=30000)
                except Exception as exc:warnings.append('NAVIGATION: ' + str(clean(str(exc))))
                page.wait_for_timeout(seconds * 1000)
            finally:context.close()  # Flush all HTTP response bodies before extraction.
        finally:browser.close()
    document = json.loads(target.read_text(encoding='utf-8'))
    document['log']['_warpWebSockets'] = frames
    document['log']['_aisladorCapture'] = {'fresh_session': True, 'actions_sent': [],
        'warnings': warnings, 'scope': 'bootstrap_and_observed_traffic'}
    target.write_text(json.dumps(document), encoding='utf-8')
    return warnings


def _save(path, document):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=True, indent=2), encoding='utf-8')
    temporary.replace(path)


@contextmanager
def _queue_lock(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    with (out/'capture.lock').open('a+b') as lock:
        lock.seek(0,2)
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as exc:raise ValueError('Ya hay una captura usando esta carpeta.') from exc
        try:yield
        finally:
            lock.seek(0)
            if os.name=='nt':msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(lock.fileno(),fcntl.LOCK_UN)


def capture_batch(urls, out, **options):
    with _queue_lock(Path(out).resolve()):return _capture_batch(urls,out,**options)


def _capture_batch(urls, out, *, provider='auto', seconds=12, max_games=5, headed=False, tester_spin_database=None, handoff_data_root=None):
    urls = validate_urls(urls)
    if not 1 <= seconds <= 120 or not 1 <= max_games <= 30:
        raise ValueError('Duración: 1–120 segundos; lote: 1–30 juegos.')
    if provider != 'auto' and provider not in get_profiles():raise ValueError('Proveedor no registrado.')
    out = Path(out).resolve();out.mkdir(parents=True, exist_ok=True)
    state_path = out / 'queue.private.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'schema': 'aislador/capture/v1', 'jobs': {}}
    if state.get('schema') != 'aislador/capture/v1':raise ValueError('Cola incompatible.')
    selected = []; attempted = 0; batch=[]
    for url in urls:
        key = digest(provider + '\0' + url)[:24]
        job = state['jobs'].setdefault(key, {'id': key, 'url': url, 'provider': provider, 'status': 'pending'})
        selected.append(job)
        if job['status'] == 'captured' and Path(job.get('analysis', '')).is_dir():continue
        if attempted >= max_games:continue
        attempted += 1
        batch.append(job)
        raw = out / (key + '.private.har')
        job['status'] = 'capturing';_save(state_path, state)
        try:
            # A saved HAR survives an interrupted/failed analysis; do not recapture it.
            if not raw.exists():
                temporary = out / (key + '.recording.private.har')
                job['warnings'] = record_demo(url, temporary, seconds, headed)
                load_har(temporary)
                temporary.replace(raw)
            job['raw'] = str(raw)
            results = run_extract([raw], provider, out / 'analisis', progress=lambda _: None)
            job['analysis'] = results[0]['output'];job['status'] = 'captured';job.pop('error', None)
            job['handoff_revision']=EVIDENCE_REVISION
        except Exception as exc:
            job['status'] = 'error';job['error'] = clean(str(exc))
        _save(state_path, state)
    families = {}
    for job in state['jobs'].values():
        if job['status'] != 'captured':continue
        if tester_spin_database is not None and job['provider']=='playtech':
            from .handoff import export_playtech_evidence
            # Older saved bundles can be upgraded offline; no new browser session.
            if job.get('handoff_revision')!=EVIDENCE_REVISION:
                job['analysis']=run_extract([job['raw']],job['provider'],out/'analisis',progress=lambda _:None)[0]['output']
                job['handoff_revision']=EVIDENCE_REVISION
            job['handoff']=export_playtech_evidence(job['analysis'],tester_spin_database,
                handoff_data_root or Path(tester_spin_database).resolve().parent)
        patterns = Path(job['analysis']) / 'patrones.json'
        if not patterns.is_file():continue
        for pattern in json.loads(patterns.read_text(encoding='utf-8')):
            row = families.setdefault(pattern['id'], {'provider': pattern['provider'], 'action': pattern['action'],
                'novelty_reasons': pattern['novelty_reasons'], 'captures': [], 'examples': []})
            row['captures'].append(job['id'])
            if len(row['examples']) < 3:row['examples'].append({'capture': job['id'], 'analysis': job['analysis'], 'refs': pattern['examples']})
    _save(out / 'familias.json', families)
    _save(state_path,state)
    visible=batch or selected[:max_games]
    return {'jobs': [{**{k: v for k, v in j.items() if k != 'url'}, 'url': safe_url(j['url'])} for j in visible],
            'pending':sum(j['status']!='captured' for j in selected),
            'families': str(out / 'familias.json'), 'certifies_game_ok': False,
            'scope': 'bootstrap_and_observed_traffic', 'bets_submitted': False}
