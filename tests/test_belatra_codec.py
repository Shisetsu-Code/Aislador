"""Synthetic offline Belatra cases; no captured sessions."""
import base64
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError:
    Cipher = None
try:
    from aislador.codecs import belatra
except ImportError:
    belatra = None

ORIGIN = 'https://demo.bltr-static.com'


def config(secret='synthetic-a', sid='sid-a', origin=ORIGIN):
    value = {'sc': secret, 'user': {'sid': sid}, 'request_crypt': True}
    return {'request': {'url': origin + '/play/demo', 'method': 'GET'},
            'response': {'content': {'mimeType': 'text/html', 'text': '<script>var config = ' + json.dumps(value) + '; window.untrusted();</script>'}}}


def wire(request, response, url=ORIGIN + '/game', form=False):
    return {'request': {'url': url, 'method': 'POST', 'postData': {
        'mimeType': 'application/x-www-form-urlencoded' if form else 'application/json',
        'text': urlencode(request) if form else json.dumps(request)}},
        'response': {'content': {'mimeType': 'application/json', 'text': json.dumps(response)}}}


def encrypt(message, secret='synthetic-a', prefix=b'\xe7\x03\x34\x12\x01\x02\x03\x04'):
    material = (secret.encode() + bytes(16))[:16]
    derive = Cipher(algorithms.AES(material), modes.ECB()).encryptor()
    key = derive.update(material) + derive.finalize()
    crypt = Cipher(algorithms.AES(key), modes.CTR(prefix + bytes(8))).encryptor()
    data = json.dumps(message, ensure_ascii=False).encode()
    return base64.b64encode(prefix + crypt.update(data) + crypt.finalize()).decode()


class BelatraCodecTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(belatra, 'Belatra offline codec must exist')

    def test_missing_config_remains_pending_without_private_issue_data(self):
        result = belatra.decode_entries({'log': {'entries': [wire({'sid': 'private', 'd': 'AA=='}, {'d': 'AA=='})]}})
        self.assertEqual(result['http:0'], {'request': None, 'response': None, 'issues': ['missing_key']})

    def test_multiple_configs_without_binding_are_ambiguous(self):
        entries = [config(), config('synthetic-b', 'sid-b'), wire({'d': 'AA=='}, {'d': 'AA=='})]
        self.assertEqual(belatra.decode_entries({'log': {'entries': entries}})['http:2']['issues'], ['ambiguous_key'])

    def test_wrong_sid_or_origin_cannot_fall_back_to_single_key(self):
        entries = [config(), wire({'sid': 'other', 'd': 'AA=='}, {}), wire({'sid': 'sid-a', 'd': 'AA=='}, {}, url='https://else.example/game')]
        results = belatra.decode_entries({'log': {'entries': entries}})
        self.assertEqual(results['http:1']['issues'], ['missing_key'])
        self.assertEqual(results['http:2']['issues'], ['missing_key'])

    def test_dependency_absence_is_explicit(self):
        entries = [config(), wire({'sid': 'sid-a', 'd': 'AA=='}, {'d': 'AA=='})]
        with patch.object(belatra, 'Cipher', None):
            self.assertEqual(belatra.decode_entries({'log': {'entries': entries}})['http:1']['issues'], ['dependency_missing'])

    def test_config_is_json_only_not_javascript_and_not_exported(self):
        bad = config()
        bad['response']['content']['text'] = '<script>var config = {sc: execute()};</script>'
        entries = [bad, wire({'d': 'AA=='}, {})]
        result = belatra.decode_entries({'log': {'entries': entries}})
        self.assertNotIn('http:0', result)
        self.assertEqual(result['http:1']['issues'], ['missing_key'])

    @unittest.skipIf(Cipher is None, 'cryptography optional')
    def test_nonce_money_roundtrip_for_form_and_json(self):
        request = {'cmd': 'start', 'bet': 1.25, 'nested': {'sid': 'private'}}
        response = {'balance': 123.45, 'win': 2.5, 'currency': '€'}
        for form in [False, True]:
            with self.subTest(form=form):
                entries = [config(), wire({'sid': 'sid-a', 'd': encrypt(request)}, {'d': encrypt(response, prefix=b'87654321')}, form=form)]
                result = belatra.decode_entries({'log': {'entries': entries}})['http:1']
                self.assertEqual(result['request'], {'cmd': 'start', 'bet': 1.25, 'nested': {}})
                self.assertEqual(result['response'], response)
                self.assertEqual(result['issues'], [])

    @unittest.skipIf(Cipher is None, 'cryptography optional')
    def test_session_binding_and_one_bad_side_preserves_good_response(self):
        entries = [config(), config('synthetic-b', 'sid-b'),
                   wire({'sid': 'sid-b', 'd': '!!!'}, {'d': encrypt({'win': 10}, 'synthetic-b')}),
                   wire({'sid': 'sid-a', 'd': encrypt({'cmd': 'enter'})}, {'d': 'AAAA'})]
        result = belatra.decode_entries({'log': {'entries': entries}})
        self.assertEqual(result['http:2']['response'], {'win': 10})
        self.assertEqual(result['http:2']['issues'], ['invalid_request'])
        self.assertEqual(result['http:3']['request'], {'cmd': 'enter'})
        self.assertEqual(result['http:3']['issues'], ['invalid_response'])

    @unittest.skipIf(Cipher is None, 'cryptography optional')
    def test_single_config_origin_binding_without_sid(self):
        entries = [config(), wire({'d': encrypt({'cmd': 'enter'})}, {'d': encrypt({'balance': 50})})]
        self.assertEqual(belatra.decode_entries({'log': {'entries': entries}})['http:1']['request'], {'cmd': 'enter'})

    @unittest.skipIf(Cipher is None, 'cryptography optional')
    def test_invalid_encrypted_json_and_body_limit(self):
        entries = [config(), wire({'sid': 'sid-a', 'd': encrypt('not-object')}, {'d': encrypt({'win': 0})})]
        self.assertEqual(belatra.decode_entries({'log': {'entries': entries}})['http:1']['issues'], ['invalid_request'])
        with patch.object(belatra, 'MAX_BODY', 16):
            self.assertEqual(belatra.decode_entries({'log': {'entries': entries}})['http:1']['issues'], ['invalid_request', 'invalid_response'])


if __name__ == '__main__':
    unittest.main()


class BelatraCaptureVariantsTests(unittest.TestCase):
    @unittest.skipIf(Cipher is None, 'cryptography optional')
    def test_base64_html_config_and_har_form_params(self):
        boot = config()
        content = boot['response']['content']
        content['text'] = base64.b64encode(content['text'].encode()).decode()
        content['encoding'] = 'base64'
        entry = wire({}, {'d': encrypt({'win': 1.5})})
        entry['request']['postData'] = {'mimeType': 'application/x-www-form-urlencoded', 'params': [
            {'name': 'sid', 'value': 'sid-a'}, {'name': 'd', 'value': encrypt({'cmd': 'finish', 'sc': 'private'})}]}
        result = belatra.decode_entries({'log': {'entries': [boot, entry]}})['http:1']
        self.assertEqual(result['request'], {'cmd': 'finish'})
        self.assertEqual(result['response'], {'win': 1.5})
        self.assertEqual(result['issues'], [])

    def test_conflicting_keys_for_exact_same_sid_are_ambiguous(self):
        entries = [config(), config('synthetic-b'), wire({'sid': 'sid-a', 'd': 'AAAA'}, {})]
        self.assertEqual(belatra.decode_entries({'log': {'entries': entries}})['http:2']['issues'], ['ambiguous_key'])

if __name__ == '__main__':
    unittest.main()

