"""Known synthetic 1Spin4Win wire shapes, never captured credentials."""
import json
import unittest
from unittest.mock import patch
try:
    from aislador.codecs import one_spin
except ImportError:
    one_spin = None


class OneSpinCodecTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(one_spin, '1Spin4Win offline codec must exist')

    def test_exact_prefix_and_plain_json_preserve_game_fields(self):
        data = {'type': '1', 'data': {'st': 3, 'b': 123.45, 'win': 5}, 'key': 'synthetic-private'}
        for prefix in ('', 'A/u2'):
            self.assertEqual(one_spin.decode_message(prefix + json.dumps(data)), data)

    def test_init_csv_exposes_only_known_public_metadata(self):
        payload = 'A/u2' + json.dumps({'type': '0', 'data': 'private-user,private-session,freeplay,Game,000123,1000.50,EUR,private-tail'})
        self.assertEqual(one_spin.decode_message(payload), {'type': '0', 'data': {'game_name': 'Game', 'version': '000123', 'wallet': '1000.50', 'currency': 'EUR'}})
        self.assertNotIn('private', json.dumps(one_spin.decode_message(payload)))

    def test_unknown_or_short_init_csv_is_redacted(self):
        for data in ['private-user,private-session', 'a,b,unknown,secret,version,999,EUR', 'a,b,freeplay,,version,999,EUR']:
            result = one_spin.decode_message(json.dumps({'type': 0, 'data': data}))
            self.assertEqual(result['data'], '[REDACTED]')

    def test_known_play_csv_keeps_positions_without_column_names(self):
        for data, expected in [('20,2,0', ['20', '2', '0']), ('20,2,0,5', ['20', '2', '0', '5'])]:
            self.assertEqual(one_spin.decode_message('A/u2' + json.dumps({'type': '1', 'data': data}))['data'], expected)

    def test_unknown_csv_and_play_tokens_are_redacted(self):
        for kind, data in [('99', 'private,secret,extra'), ('1', '20,session-token,0'), ('1', '20,2,0,1,private')]:
            self.assertEqual(one_spin.decode_message(json.dumps({'type': kind, 'data': data}))['data'], '[REDACTED]')

    def test_keepalive_is_explicit(self):
        for payload in ['pns', 'A/pns']:
            result = one_spin.decode_message(payload)
            self.assertEqual(result['type'], 'keepalive')
            self.assertEqual(result['classification'], 'keepalive')

    def test_unknown_prefix_and_invalid_shapes_return_none(self):
        for payload in ['B/u2{}', 'junk{"type":"1"}', 'A/u20{}', '[]', '1', 'A/u2{', '', None, b'\xff']:
            with self.subTest(payload=payload):
                self.assertIsNone(one_spin.decode_message(payload))

    def test_size_limit_and_bytes_input(self):
        self.assertEqual(one_spin.decode_message(b'{"type":"3","data":"close"}'), {'type': '3', 'data': 'close'})
        with patch.object(one_spin, 'MAX_BODY', 8):
            self.assertIsNone(one_spin.decode_message('A/u2{"type":"1"}'))
            self.assertIsNone(one_spin.decode_message(b'{"type":"1"}'))


if __name__ == '__main__':
    unittest.main()
