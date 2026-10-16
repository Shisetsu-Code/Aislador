"""Acquire fresh, passive HARs for new failed Tester-Spin results.

Every result id has its own capture directory. Analysis retries reuse that HAR;
a later failed run of the same title creates a genuinely new capture.
"""
import json
import time
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlencode
from .capture import capture_batch, _queue_lock, _save
from .profiles import get_profiles
from .sanitize import clean


def drain_failures(database,out,*,after_id=0,max_games=3,seconds=12):
    if after_id<0 or not 1<=max_games<=30 or not 1<=seconds<=120:raise ValueError('Límites de captura inválidos')
    out=Path(out).resolve()
    with _queue_lock(out):
        return _drain(database,out,after_id,max_games,seconds)


def _drain(database,out,after_id,max_games,seconds):
    path=out/'failures.private.json'
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema':'aislador/failures/v1','cursor':after_id,'requests':{}}
    if state.get('schema')!='aislador/failures/v1':raise ValueError('Cola de fallos incompatible')
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        con.execute('BEGIN')
        rows=con.execute('''SELECT r.id,r.provider,r.slug,r.game_url,r.symbol,r.status FROM test_results r
            WHERE r.id>? AND r.status IN ('ERROR','PARCIAL') AND NOT EXISTS
            (SELECT 1 FROM test_results n WHERE n.provider=r.provider AND n.slug=r.slug AND n.id>r.id)
            ORDER BY r.id''',(state['cursor'],)).fetchall()
        latest={(provider,slug):identifier for provider,slug,identifier in con.execute('SELECT provider,slug,MAX(id) FROM test_results GROUP BY provider,slug')}
        state['cursor']=max(state['cursor'],con.execute('SELECT COALESCE(MAX(id),0) FROM test_results').fetchone()[0])
    for identifier,provider,slug,url,symbol,status in rows:
        state['requests'].setdefault(str(identifier),{'result_id':identifier,'provider':provider,'slug':slug,
            'url':url,'symbol':symbol,'result_status':status,'status':'pending'})
    _save(path,state)
    processed=[]
    for request in state['requests'].values():
        if request['status'] in ('ready','failed'):continue
        if latest.get((request['provider'],request['slug']))!=request['result_id']:
            request['status']='superseded';continue
        if request['status']=='superseded' or request.get('retry_at',0)>time.time():continue
        if len(processed)>=max_games:break
        processed.append(request['result_id'])
        try:
            provider=request['provider']
            if provider not in get_profiles():raise ValueError('Proveedor sin perfil de análisis')
            url=request['url']
            if provider=='playtech' and request['symbol']:
                url='https://cachedownload.playtechone.com/ngmdesktop/casinoclient.html?'+urlencode({'game':request['symbol'],'preferedmode':'offline','real':'0'})
            result=capture_batch([url],out/'captures'/provider/str(request['result_id']),provider=provider,
                max_games=1,seconds=seconds,tester_spin_database=database)
            job=result['jobs'][0]
            if job['status']!='captured':raise RuntimeError(job.get('error','Captura incompleta'))
            request.update(status='ready',analysis=job['analysis'],raw=job.get('raw'),handoff=job.get('handoff'))
            request.pop('error',None);request.pop('retry_at',None)
        except Exception as exc:
            attempts=request.get('attempts',0)+1
            request.update(status='retry' if attempts<3 else 'failed',attempts=attempts,error=clean(str(exc)),retry_at=time.time()+300)
        _save(path,state)
    _save(path,state)
    review=[{k:v for k,v in r.items() if k not in ('url',)} for r in state['requests'].values() if r['status']!='superseded']
    _save(out/'revision.json',{'schema':'aislador/review-queue/v1','requests':review,'primitive_updates':'manual_review_required','certifies_game_ok':False})
    return {'processed':processed,'pending':sum(r['status'] in ('pending','retry') for r in state['requests'].values()),
            'review_queue':str(out/'revision.json'),'cursor':state['cursor'],'certifies_game_ok':False}


def follow_failures(database,out,*,after_id=0,seconds=12,idle_seconds=5):
    """Short-lived worker. A process-wide folder lock avoids duplicate workers."""
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    with _queue_lock(out/'worker'):
        idle=time.monotonic();summary=None
        while summary is None or summary['pending'] or time.monotonic()-idle<idle_seconds:
            summary=drain_failures(database,out,after_id=after_id,max_games=3,seconds=seconds)
            if summary['processed']:idle=time.monotonic()
            time.sleep(.5)
        return summary
