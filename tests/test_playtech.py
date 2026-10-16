import json
import unittest
from aislador.engine import analyze


HOST = 'wss://gpas-stg.playtechone.com/socket.io/1/websocket/demo'


def capture(payloads, url=HOST):
    return {'log': {'entries': [], '_warpWebSockets': [
        {'url': url, 'direction': direction, 'payload': payload}
        for direction, payload in payloads]}}


class PlaytechTests(unittest.TestCase):
    def test_socketio_decodes_and_preserves_choices_and_errors(self):
        data = {'data': {'_type': 'com.pt.casino.platform.game.GameCommand',
                        'gameData': {'choices': [0, 1], 'nextRound': 'PICK'},
                        'betCost': 100, 'token': 'private-value'}, 'correlationId': 'req1'}
        r = analyze(capture([('sent', '3:::' + json.dumps(data))]))
        event = r['events'][0]
        self.assertEqual(event['provider'], 'playtech')
        self.assertEqual(event['action'], data['data']['_type'])
        self.assertEqual(event['data']['data']['gameData']['choices'], [0, 1])
        self.assertNotIn('OPAQUE_WEBSOCKET', event['issues'])
        self.assertNotIn('private-value', json.dumps(r))
        self.assertTrue(r['novelties'])

    def test_controls_removed_but_unknown_and_malformed_retained(self):
        r = analyze(capture([('received', '1::'), ('received', '2::'),
                             ('received', '3:::{bad'), ('received', '7:::failure')]))
        self.assertEqual(len(r['events']), 2)
        self.assertEqual(r['summary']['excluded']['transport_control'], 2)
        self.assertTrue(all('OPAQUE_WEBSOCKET' in e['issues'] for e in r['events']))

    def test_other_providers_are_not_decoded_as_playtech(self):
        r = analyze(capture([('sent', '3:::{"data":{"_type":"X"}}')], 'wss://example.org/socket.io/1/websocket/demo'))
        self.assertIn('OPAQUE_WEBSOCKET', r['events'][0]['issues'])

    def test_frontend_transport_and_domain_boundaries(self):
        payload = [('received', '3:::{"data":{"_type":"NewChoice","options":[1,2]}}')]
        r = analyze(capture(payload, 'wss://frontend.playtechhorizon.com/socket.io/1/websocket/demo'))
        self.assertEqual(r['events'][0]['action'], 'NewChoice')
        for url in ('wss://frontend.playtechhorizon.com.evil.org/socket.io/1/websocket/demo',
                    'wss://gpas-stg.playtechone.com/not-socket'):
            r = analyze(capture(payload, url))
            self.assertIn('OPAQUE_WEBSOCKET', r['events'][0]['issues'])

    def test_interface_assets_only_exact_resources_and_successful_get(self):
        def asset(name, status=200, method='GET'):
            return {'request': {'url': 'https://cachedownload.playtechone.com/res/' + name, 'method': method},
                    'response': {'status': status, 'content': {'mimeType': 'application/json', 'text': '{"option":1}'}}}
        r = analyze({'log': {'entries': [asset('texts_en.jmm'), asset('game.default.jmm'),
            asset('texts_en.jmm', 500), asset('texts_en.jmm', method='POST')]}})
        self.assertEqual(r['summary']['excluded']['ui_translations'], 1)
        self.assertEqual(len(r['events']), 3)
        self.assertIn('HTTP_ERROR', r['events'][1]['issues'])

    def test_correlated_packets_pair_without_losing_server_type(self):
        r = analyze(capture([('sent', '3:::{"correlationId":"q","data":{"_type":"GetGameConfigurationRequest"}}'),
                             ('received', '3:::{"correlationId":"q","data":{"_type":"GetGameConfigurationResponse","costConfiguration":[{"cost":10}]}}')]))
        self.assertEqual(r['events'][0]['paired_ref'], 'ws:log:1')
        self.assertEqual(r['events'][1]['data']['data']['_type'], 'GetGameConfigurationResponse')


if __name__ == '__main__':
    unittest.main()
