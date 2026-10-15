"""Data-driven provider identities; catalog presence does not prove protocol."""
import json,re
from functools import lru_cache
from importlib.resources import files
from urllib.parse import urlsplit

@lru_cache(maxsize=1)
def get_profiles():
    document=json.loads(files('aislador').joinpath('profiles.json').read_text(encoding='utf-8'))
    return {row['key']:row for row in document['profiles']}


def detect_provider(url,payload=None):
    path=urlsplit(url).path;host=(urlsplit(url).hostname or '').lower();scores=[]
    for key,p in get_profiles().items():
        score=0
        for domain in p.get('hosts',[]):
            if host==domain or host.endswith('.'+domain):score=max(score,2)
        if score and any(re.search(rule,path,re.I) for rule in p.get('endpoint_patterns',[])):score+=3
        if host in ('games.evolution.com','playin.com') and any(re.search(rule,path,re.I) for rule in p.get('shared_host_endpoint_patterns',[])):score=5
        # Shared Evolution/Playin hosts have no provider authority.
        if host in ('games.evolution.com','playin.com') and score<5:score=0
        if score:scores.append((score,key))
    if not scores:return None
    scores.sort(reverse=True)
    return scores[0][1] if len(scores)==1 or scores[0][0]>scores[1][0] else None
