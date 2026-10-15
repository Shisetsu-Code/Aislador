"""Offline Belatra envelope decoding from captured JSON bootstrap evidence.

No JavaScript, network, replay, or session configuration is exported. AES is
optional; lack of cryptography leaves encrypted entries explicitly pending.
"""
import base64
import json
import re
from urllib.parse import urlencode, urlsplit

from aislador.har import body_text, parse_body

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    Cipher = algorithms = modes = None

MAX_BODY = 8 * 1024 * 1024
_CONFIG = re.compile(r'\bvar\s+config\s*=\s*')


def _working_aes_key(secret):
    if Cipher is None:
        raise ImportError('dependency_missing')
    if not isinstance(secret, str) or not secret or len(secret) > MAX_BODY:
        raise ValueError('invalid_key')
    material = (secret.encode('utf-8') + bytes(16))[:16]
    encryptor = Cipher(algorithms.AES(material), modes.ECB()).encryptor()
    return encryptor.update(material) + encryptor.finalize()


def _crypt_bytes(data, secret, prefix):
    if not isinstance(data, bytes) or len(data) > MAX_BODY or len(prefix) != 8:
        raise ValueError('invalid_payload')
    key = _working_aes_key(secret)
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    out = bytearray()
    for counter, offset in enumerate(range(0, len(data), 16)):
        stream = encryptor.update(prefix + counter.to_bytes(8, 'big'))
        out.extend(a ^ b for a, b in zip(data[offset:offset + 16], stream))
    encryptor.finalize()
    return bytes(out)


def _decrypt_payload(encoded, secret):
    if not isinstance(encoded, str) or len(encoded) > MAX_BODY:
        raise ValueError('invalid_payload')
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) < 8:
        raise ValueError('invalid_payload')
    return _crypt_bytes(raw[8:], secret, raw[:8]).decode('utf-8')


def _configurations(entries):
    configs = []
    decoder = json.JSONDecoder()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            url = urlsplit(entry['request']['url'])
            if url.scheme not in ('https', 'http') or not url.netloc or url.username:
                continue
            origin = (url.scheme, url.netloc)
            content = (entry.get('response') or {}).get('content')
            text, issue = body_text(content)
            if issue or not text or 'var' not in text:
                continue
            for marker in _CONFIG.finditer(text):
                try:
                    config, _ = decoder.raw_decode(text, marker.end())
                    secret = config['sc']
                    sid = config['user']['sid']
                    if (isinstance(secret, str) and secret and len(secret) <= MAX_BODY
                            and isinstance(sid, str) and sid):
                        record = (origin, '/game', sid, secret)
                        if record not in configs:
                            configs.append(record)
                except (ValueError, TypeError, KeyError, RecursionError):
                    continue
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return configs


def _parsed(content):
    if isinstance(content, dict) and 'text' not in content and isinstance(content.get('params'), list):
        params = content['params']
        if len(params) > 10000:
            return None
        if any(not isinstance(item, dict) or not isinstance(item.get('name'), str)
               or not isinstance(item.get('value'), str) for item in params):
            return None
        if sum(len(item['name']) + len(item['value']) for item in params) > MAX_BODY:
            return None
        content = {'mimeType': 'application/x-www-form-urlencoded',
                   'text': urlencode([(item['name'], item['value']) for item in params])}
    text, issue = body_text(content)
    if issue:
        return None
    try:
        return parse_body(text, content.get('mimeType', ''))
    except (ValueError, TypeError, RecursionError):
        return None


def _select_key(configs, url, request):
    try:
        parsed = urlsplit(url)
        candidates = [record for record in configs
                      if record[0] == (parsed.scheme, parsed.netloc)
                      and record[1] == parsed.path and not parsed.fragment]
    except (ValueError, TypeError):
        return None, 'missing_key'
    if isinstance(request, dict) and 'sid' in request:
        sid = request['sid']
        if not isinstance(sid, str):
            return None, 'ambiguous_key'
        candidates = [record for record in candidates if record[2] == sid]
    if not candidates:
        return None, 'missing_key'
    # Multiple sessions remain ambiguous even when they happen to share a key.
    if len(candidates) != 1:
        return None, 'ambiguous_key'
    return candidates[0][3], None


def _without_session(value):
    if isinstance(value, dict):
        return {key: _without_session(item) for key, item in value.items()
                if key.lower() not in ('sid', 'sc')}
    if isinstance(value, list):
        return [_without_session(item) for item in value]
    return value


def _decode_side(value, secret):
    if not isinstance(value, dict):
        raise ValueError('invalid_payload')
    if 'd' in value:
        value = json.loads(_decrypt_payload(value['d'], secret))
    if not isinstance(value, (dict, list)):
        raise ValueError('invalid_payload')
    return _without_session(value)


def decode_entries(document):
    """Return decoded sides only for entries with an encrypted d envelope.

    Binding is the captured HTML origin and observed /game endpoint plus an
    exact SID if present. Without a SID only one configuration may match.
    Decoded game fields still require the caller's general sanitization.
    """
    log = document.get('log', {}) if isinstance(document, dict) else {}
    entries = log.get('entries', []) if isinstance(log, dict) else []
    if not isinstance(entries, list):
        return {}
    configs = _configurations(entries)
    results = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        request = entry.get('request') or {}
        response = entry.get('response') or {}
        if not isinstance(request, dict) or not isinstance(response, dict):
            continue
        req_value = _parsed(request.get('postData'))
        res_value = _parsed(response.get('content'))
        if not any(isinstance(value, dict) and 'd' in value for value in (req_value, res_value)):
            continue
        result = {'request': None, 'response': None, 'issues': []}
        results[f'http:{index}'] = result
        secret, issue = _select_key(configs, request.get('url', ''), req_value)
        if issue:
            result['issues'].append(issue)
            continue
        if Cipher is None:
            result['issues'].append('dependency_missing')
            continue
        for side, value in (('request', req_value), ('response', res_value)):
            try:
                result[side] = _decode_side(value, secret)
            except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                result['issues'].append('invalid_' + side)
    return results

