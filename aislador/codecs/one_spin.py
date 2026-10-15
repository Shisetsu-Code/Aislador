"""Known 1Spin4Win messages decoded offline without guessing wire prefixes.

Init CSV contains credentials that field-name sanitizers cannot detect, so
only the public bootstrap metadata is returned. Other strings are retained
only for the known numeric play columns or explicit close message.
"""
import json
import re

MAX_BODY = 8 * 1024 * 1024
_INTEGER = re.compile(r'[0-9]{1,12}')


def decode_message(payload):
    """Decode exact A/u2 envelopes, plain JSON objects, and known keepalives.

    Unknown prefixes and non-object JSON remain opaque (None). A caller must
    still sanitize named credentials such as key in otherwise decoded JSON.
    No column names, stake meaning, or purchase semantics are inferred.
    """
    if not isinstance(payload, (str, bytes)) or len(payload) > MAX_BODY:
        return None
    if isinstance(payload, bytes):
        try:
            payload = payload.decode('utf-8')
        except UnicodeDecodeError:
            return None
    text = payload.strip()
    if text in ('pns', 'A/pns'):
        return {'type': 'keepalive', 'classification': 'keepalive', 'data': text}
    if text.startswith('A/u2'):
        text = text[4:]
    if not text.startswith('{'):
        return None
    try:
        message = json.loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(message, dict):
        return None
    data = message.get('data')
    if not isinstance(data, str):
        return message
    kind = str(message.get('type', ''))
    if kind == '0':
        fields = data.split(',')
        if (len(fields) >= 7 and fields[2].casefold() == 'freeplay'
                and fields[3].strip() and fields[4].strip()):
            message['data'] = dict(zip(('game_name', 'version', 'wallet', 'currency'),
                                       (field.strip() for field in fields[3:7])))
        else:
            message['data'] = '[REDACTED]'
    elif kind == '1':
        fields = data.split(',')
        if len(fields) in (3, 4) and all(_INTEGER.fullmatch(field) for field in fields):
            message['data'] = fields
        else:
            message['data'] = '[REDACTED]'
    elif kind != '3' or data != 'close':
        message['data'] = '[REDACTED]'
    return message
