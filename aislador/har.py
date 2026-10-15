"""Read capture variants without modifying sources or executing their content."""
import base64,json
from pathlib import Path
from urllib.parse import parse_qsl

MAX_FILE=256*1024*1024
MAX_BODY=8*1024*1024


def validate(document):
    if not isinstance(document,dict) or not isinstance(document.get('log'),dict) or not isinstance(document['log'].get('entries'),list):
        raise ValueError('Formato HAR inválido: se requiere log.entries.')
    return document


def load_har(path):
    path=Path(path)
    if path.stat().st_size>MAX_FILE:raise ValueError('El HAR supera el límite de 256 MiB.')
    return validate(json.loads(path.read_text(encoding='utf-8-sig')))


def body_text(content):
    if not isinstance(content,dict) or 'text' not in content:return None,'MISSING_BODY'
    text=content['text']
    if not isinstance(text,str):return None,'INVALID_BODY'
    if len(text)>MAX_BODY:return None,'BODY_LIMIT'
    if content.get('encoding')=='base64':
        try:text=base64.b64decode(text,validate=True).decode('utf-8')
        except (ValueError,UnicodeError):return None,'BINARY_OR_INVALID_BASE64'
    return text,None


def pairs_object(pairs):
    out={}
    for key,value in pairs:
        if key in out:out[key]=out[key]+[value] if isinstance(out[key],list) else [out[key],value]
        else:out[key]=value
    return out


def parse_body(text,mime=''):
    if text is None:return None
    if not text.strip():return ''
    try:return json.loads(text)
    except ValueError:pass
    if ('x-www-form-urlencoded' in mime or ('=' in text and not any(ch in text for ch in '<>\n{}'))):
        out=pairs_object(parse_qsl(text,keep_blank_values=True,max_num_fields=10000))
        if out:return out
    return text


def frames_from(document):
    """Stable references, with log-level representation taking precedence per URL."""
    log=validate(document)['log'];out=[];global_urls=set();used=set()
    direction={'sent':'sent','send':'sent','outgoing':'sent','out':'sent','received':'received','receive':'received','recv':'received','incoming':'received','in':'received'}
    def add(raw,ref,url,connection,late=False):
        if not isinstance(raw,dict):return
        kind=str(raw.get('direction',raw.get('type',''))).lower()
        payload=raw.get('payload',raw.get('payloadData',raw.get('data')))
        if payload is None:return
        out.append({'ref':ref,'url':raw.get('url',url),'connection':str(raw.get('connectionId',connection)),
            'direction':direction.get(kind,kind or 'unknown'),'payload':payload,'encoding':raw.get('encoding'),
            'opcode':raw.get('opcode',1),'timestamp':raw.get('timestamp',raw.get('time')),'late_attach':raw.get('late_attach',late)})
    frames=log.get('_warpWebSockets')
    if isinstance(frames,list):
        for i,frame in enumerate(frames):
            if not isinstance(frame,dict):continue
            url=frame.get('url','');global_urls.add(url)
            add(frame,f'ws:log:{i}',url,url)
    for i,entry in enumerate(log['entries']):
        if not isinstance(entry,dict):continue
        url=(entry.get('request') or {}).get('url','')
        # Firefox and local browser exporters use one of these names.
        source=next((entry[k] for k in ('_webSocketFrames','_webSocketMessages','webSocketMessages') if isinstance(entry.get(k),list)),[])
        # Merge occurrence by occurrence, never dropping a partial alternate view.
        globals_for_url=[f for f in out if f['ref'].startswith('ws:log:') and f['url']==url]
        entries_for_url=sum(isinstance(e,dict) and isinstance(e.get('request'),dict) and e['request'].get('url')==url for e in log['entries'])
        ambiguous=entries_for_url>1 and bool(globals_for_url)
        ids={f['connection'] for f in globals_for_url}
        connection=next(iter(ids)) if len(ids)==1 and not ambiguous else f'entry:{i}:{url}'
        for j,frame in enumerate(source):
            before=len(out)
            add(frame,f'ws:entry:{i}:frame:{j}',url,connection,entry.get('_webSocketLateAttach',False))
            if len(out)==before:continue
            added=out[-1]
            if ambiguous:added['issues']=['AMBIGUOUS_WS_REPRESENTATION'];continue
            match=next((g for g in globals_for_url if g['ref'] not in used
                and all(g.get(k)==added.get(k) for k in ('url','direction','payload','opcode'))
                and (g.get('timestamp') is None or added.get('timestamp') is None or g['timestamp']==added['timestamp'])),None)
            if match:
                used.add(match['ref']);match.setdefault('alternate_refs',[]).append(added['ref']);out.pop()
    return out
