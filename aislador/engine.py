"""Capture isolation: preserve evidence, group repetitions, surface unknowns."""
import base64,collections,hashlib,json,re
from pathlib import Path
from urllib.parse import urlsplit,parse_qsl
from .har import validate,body_text,parse_body,frames_from,MAX_BODY,pairs_object
from .profiles import get_profiles,detect_provider
from .sanitize import clean,safe_url,digest
from .codecs.playtech import is_gpas_socket,decode_message as decode_gpas_message

TELEMETRY=('google-analytics.com','googletagmanager.com','posthog.com','sentry.io','doubleclick.net','vitals.vercel-insights.com','analytics.nolimitcity.com','analytics.google.com')
SIGNAL=re.compile(r'action|command|mode|phase|next|select|choice|option|feature|buy|purchase|ante|extra|gamble|collect|balance|stake|bet|win|price|cost|error|multiplier|counter|remain',re.I)
ENUM=re.compile(r'^(?:action|command|cmd|type|mode|nextMode|phase|state|featureName|selectedIndex|playExtraSpin|playerSelectedExtraSpin|gambleCollected)$',re.I)
COMMON={'id','type','status','code','success','error','message','balance','win','action','command','content','game'}


def _get(value,path):
    for key in path.split('.'):
        if not isinstance(value,dict) or key not in value:return None
        value=value[key]
    return value


def _fields(value,prefix='',depth=0):
    if depth>40:return
    if isinstance(value,dict):
        for k,v in value.items():
            path=(prefix+'.' if prefix else '')+str(k)
            yield path
            yield from _fields(v,path,depth+1)
    elif isinstance(value,list):
        for v in value:yield from _fields(v,prefix+'.*',depth+1)


def _signals(value,prefix='',enums_only=False,depth=0):
    if depth>40:return {}
    out={}
    if isinstance(value,dict):
        for key,item in value.items():
            path=(prefix+'.' if prefix else '')+str(key)
            if (ENUM if enums_only else SIGNAL).search(str(key)) and not isinstance(item,(dict,list)):
                out[path]=item
            elif not enums_only and SIGNAL.search(str(key)) and isinstance(item,list) and len(item)<=64:
                out[path]=item
            out.update(_signals(item,path,enums_only,depth+1))
    elif isinstance(value,list):
        for i,item in enumerate(value):out.update(_signals(item,prefix+f'.{i}',enums_only,depth+1))
    return out


def _domains(value,prefix='',depth=0):
    if depth>40:return {}
    out={}
    if isinstance(value,dict):
        for key,item in value.items():
            path=(prefix+'.' if prefix else '')+str(key)
            if isinstance(item,list) and re.search(r'option|choice|allowed|available|featureBuy|betLevels',str(key),re.I):
                out[path]=item
            else:out.update(_domains(item,path,depth+1))
    elif isinstance(value,list):
        for i,item in enumerate(value):out.update(_domains(item,prefix+f'.{i}',depth+1))
    return out


def _action(profile,request,url):
    if is_gpas_socket(url):
        value=_get(request,'data._type')
        if isinstance(value,str):return value
    paths=(['content.type'] if profile.get('key')=='nolimit_city' else [])+profile.get('action_paths',[])+['content.type','action','command','cmd','type','method']
    for path in dict.fromkeys(paths):
        value=_get(request,path)
        if isinstance(value,(str,int)) and not isinstance(value,bool):return str(value)
    query=dict(parse_qsl(urlsplit(url).query,keep_blank_values=True))
    for path in paths:
        value=_get(query,path)
        if value is not None:return str(value)
    return urlsplit(url).path.rstrip('/').rsplit('/',1)[-1] or 'unknown'


def _asset_kind(entry):
    req=entry.get('request') or {};res=entry.get('response') or {};content=res.get('content') or {}
    url=req.get('url','');host=(urlsplit(url).hostname or '').lower();mime=content.get('mimeType','').lower()
    # Known errors and anything with a request body stay visible.
    if res.get('status',200)>=400:return None
    if any(host==h or host.endswith('.'+h) for h in TELEMETRY) or urlsplit(url).path.startswith('/_vercel/insights/') or urlsplit(url).path=='/cdn-cgi/rum' or (host=='showcase.evo-games.com' and urlsplit(url).path=='/log'):return 'telemetry'
    if req.get('method','GET').upper() not in ('GET','HEAD') or req.get('postData'):return None
    if any(part in mime for part in ('javascript','ecmascript')) or urlsplit(url).path.endswith(('.js','.mjs')):return 'client_script'
    path=urlsplit(url).path
    if host=='cachedownload.playtechone.com' and re.search(r'/(?:dt_)?texts_[A-Za-z_-]+\.jmm$',path):return 'ui_translations'
    if host=='playin.com' and (path in ('/api/games','/api/studios','/api/announcements') or path.startswith('/_next/data/')):return 'catalog_context'
    if re.search(r'/translations/[^/]+\.json$',path) or path=='/messages/messages.json':return 'ui_translations'
    if path.endswith(('.fnt','.mustache','.atlas','.shapes.txt')):return 'ui_template'
    if path.endswith('.wasm'):return 'client_binary'
    if host=='fonts.googleapis.com':return 'visual_or_binary'
    if re.search(r'/resources/sounds/[^/]+\.json$',path):return 'audio_manifest'
    if 'html' in mime:return 'page_context'
    if re.search(r'/(?:localizations|translate|i18n)/[^/]+\.json$',path):return 'ui_translations'
    if 'json' in mime:
        text,issue=body_text(content)
        value=parse_body(text,mime) if issue is None else None
        if isinstance(value,dict) and set(value)=={'sounds'} and re.search(r'\.(?:ogg|mp3)\.json$',path):return 'audio_manifest'
        atlas={'frames','meta','animations'}
        spine={'skeleton','bones','slots','skins','events','animations','ik','transform','path','physics','constraints'}
        if isinstance(value,dict) and ((set(value)<=atlas and isinstance(value.get('frames'),(dict,list)) and isinstance(value.get('meta'),dict) and 'image' in value['meta']) or (set(value)<=spine and all(k in value for k in ('skeleton','bones','animations')))):return 'visual_json'
    if mime.startswith(('image/','audio/','video/','font/')) or any(x in mime for x in ('font',)):return 'visual_or_binary'
    if urlsplit(url).path.lower().endswith(('.png','.webp','.jpg','.jpeg','.gif','.woff','.woff2','.ttf','.mp3','.ogg','.mp4','.css')) and 'json' not in mime:return 'visual_or_binary'
    return None


def _profile(provider,url,payload):
    key=provider if provider!='auto' else ('playtech' if is_gpas_socket(url) else detect_provider(url,payload))
    return key or 'unknown',get_profiles().get(key,{})


def _server_error(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if str(key).lower() in ('error','errorcode','error_code','errors') and item not in (None,False,0,'','0',[],{},'OK','ok'):return True
            if str(key).lower()=='success' and item is False:return True
            if str(key).lower()=='status' and isinstance(item,str) and item.lower() in ('error','failed','failure'):return True
            if _server_error(item):return True
    elif isinstance(value,list):return any(_server_error(item) for item in value)
    return False


def _classify(event,profile,knowledge):
    reasons=[]
    if event.get('issues'):reasons.extend(event['issues'])
    if event['provider']=='unknown':reasons.append('UNKNOWN_PROVIDER')
    if profile.get('protocol_status')=='catalog_only':reasons.append('PROTOCOL_NOT_LEARNED')
    known=set(profile.get('known_fields',[]))|COMMON
    unknown=[];bodies=[]
    if event['transport']=='http':
        bodies=[('request',event['request']['body']),('response',event['response']['body'])]
    else:bodies=[('message',event['data'])]
    fields=[];enums={};signals={};domains={}
    for side,body in bodies:
        if event['provider']=='hacksaw' and isinstance(body,dict) and body.get('statusCode') not in (None,0,'0'):reasons.append('SERVER_ERROR')
        if _server_error(body):reasons.append('SERVER_ERROR')
        for field in set(_fields(body)):
            fields.append(side+':'+field)
            if field not in known:unknown.append(side+':'+field)
        domains.update({side+':'+k:v for k,v in _domains(body).items()})
        enums.update({side+':'+k:v for k,v in _signals(body,enums_only=True).items()})
        signals.update({side+':'+k:v for k,v in _signals(body).items()})
    if unknown:reasons.append('UNKNOWN_FIELDS')
    action=event['action'];actions=profile.get('known_actions',[])
    if action not in actions:reasons.append('UNKNOWN_ACTION')
    phases={str(v) for k,v in enums.items() if k.rsplit('.',1)[-1].lower() in ('mode','nextmode','phase','state')}
    if phases-set(profile.get('known_phases',[])):reasons.append('UNKNOWN_PHASE')
    event['signals']=signals
    event['unknown_fields']=sorted(set(unknown))
    signature={'provider':event['provider'],'transport':event['transport'],'direction':event.get('direction'),
        'action':action,'fields':sorted(set(fields)),'enums':enums,'domains':domains,'status':(event.get('response') or {}).get('status')}
    event['pattern']=digest(json.dumps(signature,sort_keys=True,ensure_ascii=True))
    event['pattern_signature']=signature
    # Manual shape review can suppress structural novelty, never failures/opacity.
    if event['pattern'] in knowledge:
        reasons=[r for r in reasons if r not in ('UNKNOWN_FIELDS','UNKNOWN_ACTION','UNKNOWN_PHASE')]
        event['reviewed_pattern']=True
    event['novelty_reasons']=list(dict.fromkeys(reasons))
    event['classification']='novel' if reasons else 'known'


def _preview(value,depth=0):
    if depth>3:return {'type':type(value).__name__,'detail':'Ver evento completo'}
    if isinstance(value,dict):return {k:_preview(v,depth+1) for k,v in list(value.items())[:12]}
    if isinstance(value,list):return {'type':'list','length':len(value),'example':[_preview(v,depth+1) for v in value[:4]]}
    if isinstance(value,str) and len(value)>180:return {'type':'text','length':len(value),'sha256':digest(value)}
    return value


def _sample(event):
    values={}
    for label in event['unknown_fields'][:40]:
        side,path=label.split(':',1)
        body=event.get('data') if side=='message' else event.get(side,{}).get('body')
        if '*' not in path:values[label]=_preview(_get(body,path))
    return {'ref':event['ref'],'signals':{k:_preview(v) for k,v in list(event['signals'].items())[:80]},'unknown_values':values}


def _pair_ws(events):
    pending={};last={}
    for event in events:
        if event['transport']!='websocket':continue
        data=event.get('data');identifier=data.get('id') if isinstance(data,dict) else None
        if isinstance(data,dict) and is_gpas_socket(event['url']):identifier=data.get('correlationId')
        if isinstance(identifier,(str,int)):
            key=(event['connection'],str(identifier))
            if event['direction']=='sent':
                if key in pending:event['issues'].append('DUPLICATE_REQUEST_ID')
                else:pending[key]=event
            elif event['direction']=='received':
                request=pending.pop(key,None)
                if request:
                    event['paired_ref']=request['ref'];request['paired_ref']=event['ref']
                    event['action']=request['action']
        if event['direction']=='received' and isinstance(data,dict):
            current=_signals(data,enums_only=True);previous=last.get(event['connection'],{})
            event['transitions']=[{'field':key,'before':previous[key],'after':value} for key,value in current.items() if key in previous and previous[key]!=value]
            last[event['connection']]=current
        event.setdefault('transitions',[])
    for request in pending.values():request['issues'].append('UNANSWERED_REQUEST')


def analyze(document,*,provider='auto',knowledge=None,source_name='',source_sha256=''):
    validate(document)
    if provider!='auto' and provider not in get_profiles():raise ValueError('Proveedor no registrado: '+provider)
    knowledge=set(knowledge or []);events=[];context=[];excluded=collections.Counter();warnings=[]
    entries=document['log']['entries']
    acquisition=document['log'].get('_aisladorCapture')
    if isinstance(acquisition,dict):
        warnings.extend('CAPTURE:'+str(clean(w)) for w in acquisition.get('warnings',[]) if isinstance(w,str))
        warnings.append('BOOTSTRAP_CAPTURE_NOT_GAMEPLAY_COVERAGE')
    belatra={}
    try:
        from .codecs.belatra import decode_entries
        belatra=decode_entries(document)
    except ImportError:pass
    for i,entry in enumerate(entries):
        if not isinstance(entry,dict):warnings.append('INVALID_ENTRY:'+str(i));continue
        req=entry.get('request') or {};res=entry.get('response') or {};url=req.get('url','');kind=_asset_kind(entry);ref=f'http:{i}'
        # The HTTP upgrade is a transport context, not a second game action.
        if res.get('status')==101 or urlsplit(url).scheme in ('ws','wss'):
            context.append({'ref':ref,'kind':'websocket_upgrade','url':safe_url(url)});continue
        if kind:
            excluded[kind]+=1
            raw=(res.get('content') or {}).get('text')
            item={'ref':ref,'kind':kind,'url':safe_url(url),'mime':(res.get('content') or {}).get('mimeType'),
                'bytes':len(raw.encode('utf-8',errors='replace')) if isinstance(raw,str) else None,'sha256':digest(raw) if raw is not None else None}
            if kind=='client_script' and isinstance(raw,str):
                item['action_offsets']=[{'offset':m.start(),'token':m.group()} for m in list(re.finditer(r'zeroBet\(|pickAndClickBet\(|gambleBet\(|playExtraSpin|playerSelectedExtraSpin|selectedIndex',raw))[:60]]
            context.append(item);continue
        post=req.get('postData') or {};request_text,request_issue=body_text(post)
        if isinstance(post.get('params'),list) and request_text is None:
            request_body=pairs_object((p['name'],p.get('value','')) for p in post['params'] if isinstance(p,dict) and 'name' in p);request_issue=None
        else:request_body=parse_body(request_text,post.get('mimeType',''))
        content=res.get('content') or {};response_text,response_issue=body_text(content)
        response_body=parse_body(response_text,content.get('mimeType',''))
        issues=[]
        if post and request_issue:issues.append('REQUEST_'+request_issue)
        if response_issue:issues.append('MISSING_RESPONSE_BODY' if response_issue=='MISSING_BODY' else 'RESPONSE_'+response_issue)
        if res.get('status',200)>=400:issues.append('HTTP_ERROR')
        if res.get('status')==0:issues.append('HTTP_INCOMPLETE')
        codec=belatra.get(ref)
        if codec:
            request_body=codec.get('request') if codec.get('request') is not None else request_body
            response_body=codec.get('response') if codec.get('response') is not None else response_body
            issues.extend('BELATRA_'+issue.upper() for issue in codec.get('issues',[]))
        key,profile=_profile(provider,url,request_body)
        if isinstance(response_body,str) and response_body:issues.append('OPAQUE_RESPONSE')
        if isinstance(request_body,dict) and isinstance(request_body.get('d'),str) or isinstance(response_body,dict) and isinstance(response_body.get('d'),str):issues.append('OPAQUE_ENCRYPTED_ENVELOPE')
        event={'ref':ref,'transport':'http','provider':key,'url':safe_url(url),'action':_action(profile,request_body,url),
            'request':{'method':req.get('method','GET'),'query':pairs_object(parse_qsl(urlsplit(url).query,keep_blank_values=True)),'body':request_body},
            'response':{'status':res.get('status'),'body':response_body},'issues':issues}
        events.append(clean(event))
    frames=frames_from(document)
    nlframes=[frame for frame in frames if (urlsplit(frame['url']).hostname or '')=='demo.nolimitcity.com']
    from .codecs.nolimit import decode_frames
    decoded=decode_frames(document,nlframes) if nlframes else {}
    for frame in frames:
        url=frame['url'];key,profile=_profile(provider,url,{})
        result=decoded.get(frame['ref']);issues=list(frame.get('issues',[]));payload=frame['payload'];data=None
        if is_gpas_socket(url) and isinstance(payload,str) and payload in ('1::','2::'):
            excluded['transport_control']+=1
            context.append({'ref':frame['ref'],'kind':'transport_control','url':safe_url(url),'direction':frame['direction'],'control':payload})
            continue
        if result:
            data=result['data']
            if result['issue']:issues.append('NOLIMIT_'+result['issue'].upper())
        elif isinstance(payload,str) and len(payload)<=MAX_BODY:
            if frame.get('encoding')=='base64':
                try:payload=base64.b64decode(payload,validate=True).decode('utf-8')
                except (ValueError,UnicodeError):payload=None
            if payload is not None:
                if is_gpas_socket(url):data=decode_gpas_message(payload)
                if data is None:
                    try:data=json.loads(payload)
                    except (ValueError,TypeError):pass
        if data is None and key=='1spin4win':
            from .codecs.one_spin import decode_message
            data=decode_message(payload)
        if data is None:issues.append('OPAQUE_WEBSOCKET')
        if frame['direction'] not in ('sent','received'):issues.append('UNKNOWN_DIRECTION')
        events.append(clean({'ref':frame['ref'],'transport':'websocket','provider':key,'url':safe_url(url),
            'connection':'connection:'+digest(frame['connection']+'\0'+url)[:12],'direction':frame['direction'],'opcode':frame.get('opcode'),
            'alternate_refs':frame.get('alternate_refs',[]),'action':_action(profile,data,url),'data':data,'opaque_sha256':digest(payload) if data is None else None,
            'opaque_bytes':len(str(payload)) if data is None else None,'issues':issues}))
    _pair_ws(events)
    connections={}
    for event in events:
        if event['transport']!='websocket':continue
        row=connections.setdefault(event['connection'],{'provider':event['provider'],'messages':0,'initialization_observed':False})
        row['messages']+=1
        data=event.get('data')
        if isinstance(data,dict) and (data.get('type')=='init' or data.get('init')=='ok' or isinstance(data.get('content'),dict) and data['content'].get('type')=='init'):
            row['initialization_observed']=True
    for key,row in connections.items():
        if row['provider']=='nolimit_city' and not row['initialization_observed']:warnings.append('MISSING_INIT:'+key)
    patterns={};novelties=[]
    for event in events:
        profile=get_profiles().get(event['provider'],{})
        _classify(event,profile,knowledge)
        pattern=patterns.setdefault(event['pattern'],{'id':event['pattern'],'provider':event['provider'],'action':event['action'],
            'count':0,'examples':[],'samples':[],'novelty_reasons':[],'unknown_fields':event['unknown_fields'],'signature':event['pattern_signature']})
        pattern['count']+=1
        if len(pattern['examples'])<3:
            pattern['examples'].append(event['ref']);pattern['samples'].append(_sample(event))
        pattern['novelty_reasons']=sorted(set(pattern['novelty_reasons'])|set(event['novelty_reasons']))
    for pattern in patterns.values():
        if pattern['novelty_reasons']:novelties.append(pattern)
    summary={'schema':'aislador/v1','source':clean(source_name),'source_sha256':source_sha256,
        'provider_override':provider,'providers':dict(collections.Counter(e['provider'] for e in events)),
        'http_entries':len(entries),'websocket_frames':len(frames),'events':len(events),'patterns':len(patterns),
        'novel_patterns':len(novelties),'known_patterns':len(patterns)-len(novelties),'excluded':dict(excluded),
        'connections':connections,'opaque_events':sum(any('OPAQUE' in x for x in e['issues']) for e in events),'warnings':warnings,
        'certifies_game_ok':False,'network_used':False,'source_modified':False}
    return {'summary':summary,'events':events,'novelties':novelties,'patterns':list(patterns.values()),'context':context}


def markdown(result):
    s=result['summary'];lines=['# Aislador',f"Captura: {s['source'] or '(en memoria)'}",'',
        f"{s['events']} eventos; {s['patterns']} patrones; {s['novel_patterns']} patrones por revisar.",
        f"Proveedores: {', '.join(s['providers']) or 'sin detectar'}.",
        f"Recursos retirados del informe: {sum(s['excluded'].values())}. Mensajes opacos: {s['opaque_events']}.",
        '', '## Novedades','']
    for p in result['novelties'][:80]:
        lines.append(f"- {p['provider']} / {p['action']}: {', '.join(p['novelty_reasons'])}; {p['count']} eventos; referencias: {', '.join(p['examples'])}.")
    if len(result['novelties'])>80:lines.append('Más patrones en novedades.ndjson.')
    lines+=['','Los eventos íntegros sanitizados están en eventos.ndjson. Los recursos y scripts se referencian en contexto.json.',
        'Conocido significa formato reconocido; este análisis no prueba que el juego funcione ni que se recorrieran todas las opciones.','']
    return '\n'.join(lines)


def write_bundle(result,destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=False)
    for filename,value in (('resumen.json',result['summary']),('patrones.json',result['patterns']),('contexto.json',result['context'])):
        (destination/filename).write_text(json.dumps(value,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    for filename,key in (('eventos.ndjson','events'),('novedades.ndjson','novelties')):
        with (destination/filename).open('w',encoding='utf-8') as stream:
            for row in result[key]:stream.write(json.dumps(row,ensure_ascii=True)+'\n')
    (destination/'resumen.md').write_text(markdown(result),encoding='utf-8')
    from .codecs.playtech import evidence_report
    report=evidence_report(result)
    if report is not None:
        (destination/'protocol-evidence.json').write_text(json.dumps(clean(report),ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    return destination
