import base64
import json
import unittest
from unittest.mock import patch

try:
    from aislador.codecs import nolimit
except ImportError:
    nolimit = None

HOST = 'https://demo.nolimitcity.com'
WS = 'wss://demo.nolimitcity.com/EjsGameWeb/ws/game?data='


def encrypted(key, text):
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + ord(key[i % len(key)])) % 256
        box[i], box[j] = box[j], box[i]
    i = j = 0
    out = []
    for byte in text.encode('latin1'):
        i = (i + 1) % 256
        j = (j + box[i]) % 256
        box[i], box[j] = box[j], box[i]
        out.append(byte ^ box[(box[i] + box[j]) % 256])
    return bytes(out).hex()


def bootstrap(key='alpha', encoded=False, host=HOST):
    text = json.dumps({'key': key, 'url': HOST + '/EjsGameWeb/gs'})
    content = {'text': text}
    if encoded:
        content = {'text': base64.b64encode(text.encode()).decode(), 'encoding': 'base64'}
    return {'request': {'method': 'POST', 'url': host + '/EjsFrontWeb/fs'},
            'response': {'content': content}}


def frame(ref='a', key='alpha', direction='sent', payload=None, **kwargs):
    result = {'ref': ref, 'url': WS + key, 'connection': WS + key,
              'direction': direction, 'payload': payload if payload is not None else encrypted(key, '{"id":"1","type":"init"}'),
              'encoding': None, 'late_attach': False}
    result.update(kwargs)
    return result


class NolimitCodecTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(nolimit, 'Nolimit offline codec must exist')

    def test_rc4_known_vector_and_limits(self):
        self.assertEqual(nolimit.rc4_hex('Key', 'BBF316E8D940AF0AD3'), 'Plaintext')
        for key, value in [('', 'aa'), ('key', 'x'), ('key', 'a'), ('\u0100', 'aa')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                nolimit.rc4_hex(key, value)
        with patch.object(nolimit, 'MAX_BODY', 2), self.assertRaises(ValueError):
            nolimit.rc4_hex('key', '000000')

    def test_lzw_known_codes_and_expansion_limit(self):
        self.assertEqual(nolimit.lzw_decode('lzw:A' + chr(256) + chr(257)), 'AAAAAA')
        self.assertEqual(nolimit.lzw_decode('{"id":1}'), '{"id":1}')
        for value in ['lzw:', 'lzw:' + chr(256), 'lzw:A' + chr(300)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                nolimit.lzw_decode(value)
        with self.assertRaises(ValueError):
            nolimit.lzw_decode('lzw:A' + chr(256) + chr(257), max_output=6)
        with self.assertRaises(ValueError):
            nolimit.lzw_decode('lzw:A' + chr(256) + chr(257) + chr(258), max_output=8)

    def test_multiple_bootstraps_use_exact_url_keys(self):
        doc = {'log': {'entries': [bootstrap(), bootstrap('beta', encoded=True)]}}
        result = nolimit.decode_frames(doc, [frame(), frame('b', 'beta'), frame('c', direction='received', payload='lzw:{"id":"1"}')])
        self.assertEqual(result['a']['data'], {'id': '1', 'type': 'init'})
        self.assertEqual(result['b']['data'], {'id': '1', 'type': 'init'})
        self.assertEqual(result['c']['data'], {'id': '1'})
        self.assertEqual(result['a']['codec'], 'nolimit-rc4-lzw')
        self.assertIsNone(result['a']['issue'])

    def test_missing_key_is_per_frame_and_query_requires_late_attach(self):
        rows = [frame(), frame('late', late_attach=True), frame('other', key='beta')]
        result = nolimit.decode_frames({}, rows)
        self.assertEqual(result['a']['issue'], 'missing_key')
        self.assertEqual(result['late']['data']['id'], '1')
        self.assertEqual(result['other']['issue'], 'missing_key')

    def test_late_attach_does_not_authorize_other_frames(self):
        result = nolimit.decode_frames({}, [frame('late', late_attach=True), frame()])
        self.assertEqual(result['a']['issue'], 'missing_key')

    def test_untrusted_bootstrap_and_malformed_entries_are_ignored(self):
        doc = {'log': {'entries': [None, {}, bootstrap(host='https://evil.example'), bootstrap(host='https://demo.nolimitcity.com.evil.example')]}}
        self.assertEqual(nolimit.decode_frames(doc, [frame()])['a']['issue'], 'missing_key')

    def test_historical_plaintext_hex_and_base64_frame(self):
        historical = encrypted('alpha', '{"id":"old"}'.encode().hex())
        encoded = base64.b64encode(historical.encode()).decode()
        result = nolimit.decode_frames({'log': {'entries': [bootstrap()]}}, [frame(payload=encoded, encoding='base64')])
        self.assertEqual(result['a']['data'], {'id': 'old'})

    def test_invalid_frames_do_not_abort_valid_frames_or_leak_secrets(self):
        rows = [frame('bad', payload='not-hex'), frame('base64', payload='!!!', encoding='base64'), frame('direction', direction='unknown'), frame()]
        result = nolimit.decode_frames({'log': {'entries': [bootstrap()]}}, rows)
        for ref in ['bad', 'base64', 'direction']:
            self.assertIsNone(result[ref]['data'])
            self.assertEqual(result[ref]['issue'], 'invalid_frame')
        self.assertEqual(result['a']['data']['id'], '1')
        self.assertNotIn('alpha', json.dumps(result))

    def test_plain_json_and_arrays_received_but_scalars_rejected(self):
        rows = [frame('array', direction='received', payload='[{"id":"x"}]'), frame('scalar', direction='received', payload='3')]
        result = nolimit.decode_frames({'log': {'entries': [bootstrap()]}}, rows)
        self.assertEqual(result['array']['data'], [{'id': 'x'}])
        self.assertEqual(result['scalar']['issue'], 'invalid_frame')

    def test_frame_size_limit_and_unrecognized_endpoint(self):
        with patch.object(nolimit, 'MAX_BODY', 16):
            result = nolimit.decode_frames({}, [frame('huge', payload='a' * 33, late_attach=True), frame('foreign', url='wss://evil.example/game')])
        self.assertEqual(result['huge']['issue'], 'invalid_frame')
        self.assertEqual(result['foreign']['issue'], 'unsupported_connection')


if __name__ == '__main__':
    unittest.main()


class NolimitLateAttachBoundaryTests(unittest.TestCase):
    def test_duplicate_query_key_including_blank_is_ambiguous(self):
        row = frame(late_attach=True, url=WS + 'alpha&data=')
        self.assertEqual(nolimit.decode_frames({}, [row])['a']['issue'], 'missing_key')

    def test_invalid_base64_bootstrap_does_not_stop_next_bootstrap(self):
        bad = bootstrap()
        bad['response']['content'] = {'text': '!!!', 'encoding': 'base64'}
        result = nolimit.decode_frames({'log': {'entries': [bad, bootstrap('beta')]}}, [frame(), frame('beta', 'beta')])
        self.assertEqual(result['a']['issue'], 'missing_key')
        self.assertEqual(result['beta']['data'], {'id': '1', 'type': 'init'})

    def test_invalid_lzw_does_not_abort_following_frame(self):
        rows = [frame('bad', direction='received', payload='lzw:' + chr(500)), frame()]
        result = nolimit.decode_frames({'log': {'entries': [bootstrap()]}}, rows)
        self.assertEqual(result['bad']['issue'], 'invalid_frame')
        self.assertEqual(result['a']['data']['id'], '1')

if __name__ == '__main__':
    unittest.main()

