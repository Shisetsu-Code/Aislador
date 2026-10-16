"""Offline decoding of the observed GPAS Socket.IO 1.x JSON transport.

No commands are executed and no action or purchase count is inferred.
"""
import json
from urllib.parse import urlsplit

EVIDENCE_REVISION = 2


def is_gpas_socket(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    return (host in ('gpas-stg.playtechone.com', 'frontend.playtechhorizon.com') and
            parsed.path.startswith('/socket.io/1/'))


def decode_message(payload):
    if not isinstance(payload, str) or not payload.startswith('3:::'):
        return None
    try:
        value = json.loads(payload[4:])
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def evidence_report(result):
    """Non-executable handoff. Preserve declarations without classifying purchases."""
    codes = set(); configurations = []; rounds = []; unresolved = []; observed = False; bindings = {}
    for event in result['events']:
        if event['provider'] != 'playtech' or event['transport'] != 'websocket':continue
        source = {'ref': event['ref'], 'connection': event['connection'],
                  'game_code': bindings.get(event['connection'])}
        issues = list(event['issues'])
        if 'SERVER_ERROR' in event.get('novelty_reasons',[]):issues.append('SERVER_ERROR')
        if issues:unresolved.append({**source,'issues':list(dict.fromkeys(issues))})
        packet = event.get('data')
        data = packet.get('data') if isinstance(packet, dict) else None
        if not isinstance(data, dict):continue
        observed = True
        kind = data.get('_type', '')
        if kind == 'InitGameSession' and event['direction'] == 'sent':
            code = data.get('gameCode')
            if isinstance(code, str):
                codes.add(code);bindings[event['connection']]=code
        elif kind == 'com.pt.gpas.config.GetGameConfigurationResponse':
            configurations.append({**source, 'data': data.get('data'), 'issues': issues})
        elif kind == 'com.pt.casino.platform.game.GameCommand':
            rounds.append({**source, 'direction': event['direction'], 'issues':issues,
                **{k:data[k] for k in ('betCost','stakeAmount','winAmount','betType','featureType','gameRoundClosed','gameData') if k in data}})
    if not observed:return None
    return {'schema':'aislador/playtech-evidence/v1', 'provider':'playtech',
        'reader_revision':EVIDENCE_REVISION,
        'source_sha256':result['summary']['source_sha256'], 'game_codes':sorted(codes),
        'configurations':configurations, 'rounds':rounds, 'unresolved':unresolved,
        'warnings':result['summary']['warnings'],
        'coverage':'observations_only', 'certifies_game_ok':False}
