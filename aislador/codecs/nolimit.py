"""Bounded, offline Nolimit RC4/LZW decoding. Session material stays in memory."""
import base64
import binascii
import json
import re
from urllib.parse import parse_qs, urlsplit

MAX_BODY = 8_000_000
CODEC = 'nolimit-rc4-lzw'
HEX = re.compile(r'[0-9a-fA-F]+')


def rc4_hex(key, value):
    """Decode the captured client RC4 hex format, bounded before allocation."""
    if (not isinstance(key, str) or not key or len(key) > MAX_BODY
            or not isinstance(value, str) or len(value) > MAX_BODY * 2
            or len(value) % 2 or not HEX.fullmatch(value)):
        raise ValueError('invalid_frame')
    try:
        keybytes = key.encode('latin1')
        data = bytes.fromhex(value)
    except (ValueError, UnicodeError):
        raise ValueError('invalid_frame') from None
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + keybytes[i % len(keybytes)]) % 256
        box[i], box[j] = box[j], box[i]
    result = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]
        result.append(byte ^ box[(box[i] + box[j]) % 256])
    return result.decode('latin1')


def lzw_decode(value, *, max_output=MAX_BODY):
    """Decode JavaScript UTF-16 LZW codes, checking expansion incrementally."""
    if not isinstance(value, str) or len(value) > max_output:
        raise ValueError('invalid_frame')
    if not value.startswith('lzw:'):
        return value
    raw = value[4:].encode('utf-16-le', errors='surrogatepass')
    codes = [int.from_bytes(raw[i:i + 2], 'little') for i in range(0, len(raw), 2)]
    if not codes or codes[0] >= 256:
        raise ValueError('invalid_frame')
    previous = chr(codes[0])
    result = [previous]
    size = 1
    table = {}
    nextcode = 256
    for code in codes[1:]:
        if code < 256:
            word = chr(code)
        elif code in table:
            word = table[code]
        elif code == nextcode:
            word = previous + previous[0]
        else:
            raise ValueError('invalid_frame')
        size += len(word)
        if size > max_output:
            raise ValueError('invalid_frame')
        result.append(word)
        table[nextcode] = previous + word[0]
        nextcode += 1
        previous = word
    return ''.join(result)


def _text(content, limit=MAX_BODY):
    value = content.get('text', '')
    if not isinstance(value, str) or len(value) > limit * 2:
        raise ValueError('invalid_frame')
    encoding = content.get('encoding')
    if encoding == 'base64':
        value = base64.b64decode(value, validate=True).decode('utf-8')
    elif encoding not in (None, ''):
        raise ValueError('invalid_frame')
    if len(value) > limit:
        raise ValueError('invalid_frame')
    return value


def _websocket_url(url, key):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or parsed.netloc != 'demo.nolimitcity.com'
            or parsed.path != '/EjsGameWeb/gs' or parsed.query or parsed.fragment
            or not isinstance(key, str) or not key or len(key) > MAX_BODY):
        raise ValueError('invalid_bootstrap')
    key.encode('latin1')
    return 'wss://demo.nolimitcity.com/EjsGameWeb/ws/game?data=' + key


def _bootstrap_keys(document):
    keys = {}
    if not isinstance(document, dict):
        return keys
    log = document.get('log')
    entries = log.get('entries', []) if isinstance(log, dict) else []
    if not isinstance(entries, list):
        return keys
    for entry in entries:
        try:
            request = entry['request']
            parsed = urlsplit(request['url'])
            if (request.get('method') != 'POST' or parsed.scheme != 'https'
                    or parsed.netloc != 'demo.nolimitcity.com'
                    or parsed.path != '/EjsFrontWeb/fs' or parsed.query or parsed.fragment):
                continue
            config = json.loads(_text(entry['response']['content']))
            target = _websocket_url(config['url'], config['key'])
            # An ambiguous connection must never silently choose a key.
            if target in keys and keys[target] != config['key']:
                keys[target] = None
            else:
                keys[target] = config['key']
        except (KeyError, TypeError, ValueError, AttributeError, UnicodeError, RecursionError):
            continue
    return keys


def decode_frames(document, frames):
    """Return one result per reference without exporting connection secrets.

    The caller owns sanitization of decoded protocol fields (including IDs).
    A late-attach query key authorizes only the explicitly marked frame.
    """
    keys = _bootstrap_keys(document)
    results = {}
    for frame in frames:
        ref = frame.get('ref')
        result = {'data': None, 'issue': None, 'codec': CODEC}
        results[ref] = result
        try:
            url = frame.get('url', '')
            parsed = urlsplit(url)
            if (parsed.scheme != 'wss' or parsed.netloc != 'demo.nolimitcity.com'
                    or parsed.path != '/EjsGameWeb/ws/game' or parsed.fragment):
                result['issue'] = 'unsupported_connection'
                continue
            key = keys.get(url)
            if key is None and url not in keys and frame.get('late_attach') is True:
                values = parse_qs(parsed.query, keep_blank_values=True).get('data', [])
                if len(values) == 1 and values[0]:
                    key = values[0]
            if not key:
                result['issue'] = 'missing_key'
                continue
            payload = _text({'text': frame.get('payload'), 'encoding': frame.get('encoding')}, MAX_BODY * 2)
            if frame.get('direction') == 'sent':
                text = rc4_hex(key, payload)
                # Historical Tester captures hex-encoded the plaintext first.
                if len(text) % 2 == 0 and HEX.fullmatch(text):
                    text = bytes.fromhex(text).decode('latin1')
            elif frame.get('direction') == 'received':
                text = lzw_decode(payload, max_output=MAX_BODY)
            else:
                raise ValueError('invalid_frame')
            message = json.loads(text)
            if not isinstance(message, (dict, list)):
                raise ValueError('invalid_frame')
            result['data'] = message
        except (ValueError, TypeError, AttributeError, UnicodeError, binascii.Error, RecursionError):
            result['issue'] = 'invalid_frame'
    return results

