"""Redact credentials, retaining game option ids and monetary evidence."""
import hashlib,re
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode

SECRET=re.compile(r'^(?:(?:launch|play|drops|profile|gamelist|challenges|quests|shop|ne_evo|wrapper)_token|csrfTokenHeaderValue|huid|idv|ida|wstoken|mgckey|ak|access.?key|u|sc|uid|api.?key|client.?secret|session[-_]?(?:uuid|id|key|token)|authorization|proxy.authorization|cookie|set.cookie|password|passwd|secret|secretkey|key|extplayerkey|playerconnect|token|tokenstring|access.?token|refresh.?token|session|sessionid|sessionuuid|sessionkey|sessiontoken|session_id|jsessionid|sid|ssid|jwt|bearer|userid|playerid|player_id|username|email|accountid|fingerprint|deviceid|clientinfo)$',re.I)
CREDENTIAL=re.compile(r"(?i)(\b"+SECRET.pattern.removeprefix("^").removesuffix("$")+r"[\"']?\s*[:=]\s*)[\"']?[^\"'&\s,;}]+")
UUID=re.compile(r'^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$',re.I)
URL=re.compile(r'https?://[^\s"<>]+|wss?://[^\s"<>]+')


def digest(value):return hashlib.sha256(value if isinstance(value,bytes) else str(value).encode('utf-8',errors='replace')).hexdigest()


def safe_url(value):
    try:
        p=urlsplit(value);host=p.hostname or ''
        if p.port:host+=':'+str(p.port)
        query=[]
        for key,v in parse_qsl(p.query,keep_blank_values=True,max_num_fields=10000):
            query.append((key,'[REDACTED]' if SECRET.fullmatch(key) or key.lower() in ('data','auth','s','mgckey') else clean(v)))
        path='/'.join('[ID]' if UUID.fullmatch(part) or len(part)>96 else part for part in p.path.split('/'))
        return urlunsplit((p.scheme,host,path,urlencode(query,doseq=True),''))
    except (ValueError,TypeError):return '[INVALID_URL]'


def clean(value,key=''):
    if SECRET.fullmatch(key):return '[REDACTED]'
    if isinstance(value,dict):return {str(k):clean(v,str(k)) for k,v in value.items()}
    if isinstance(value,list):return [clean(v,key) for v in value]
    if isinstance(value,str):
        if UUID.fullmatch(value):return '[ID:'+digest(value)[:12]+']'
        # JSON serialized inside a transport field is sanitized recursively.
        if value.startswith(('{','[')):
            import json
            try:return clean(json.loads(value))
            except (ValueError,RecursionError):pass
        value=re.sub(r'(?i)Bearer +[a-z0-9._~+/-]+=*','Bearer [REDACTED]',value)
        if value.startswith(('http://','https://','ws://','wss://')):return safe_url(value)
        value=CREDENTIAL.sub(r'\1[REDACTED]',value)
        return value
    return value
