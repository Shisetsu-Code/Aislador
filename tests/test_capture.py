import json
import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from aislador.capture import capture_batch, validate_urls


class CaptureTests(unittest.TestCase):
    def recorder(self, url, target, seconds, headed):
        document = {'log': {'entries': [{'request': {'method': 'GET', 'url': url},
            'response': {'status': 200, 'content': {'mimeType': 'application/json',
                'text': '{"options":[1,2],"balance":100}'}}}],
            '_warpWebSockets': [{'url': 'wss://gpas-stg.playtechone.com/socket.io/1/websocket/test',
                'direction': 'received', 'payload': '3:::{"data":{"_type":"Options","choices":[0,1]}}'}]}}
        target.write_text(json.dumps(document), encoding='utf-8')
        return []

    def test_capture_extract_and_resume_without_recapturing(self):
        with tempfile.TemporaryDirectory() as td:
            with patch('aislador.capture.record_demo', side_effect=self.recorder) as record:
                first = capture_batch(['https://demo.example/game'], Path(td), seconds=1)
                second = capture_batch(['https://demo.example/game'], Path(td), seconds=1)
            self.assertEqual(record.call_count, 1)
            self.assertEqual(first['jobs'][0]['status'], 'captured')
            self.assertEqual(second['jobs'][0]['status'], 'captured')
            report = Path(first['jobs'][0]['analysis'])
            self.assertTrue((report / 'novedades.ndjson').exists())
            self.assertIn('choices', (report / 'eventos.ndjson').read_text())
            self.assertTrue(Path(td, 'familias.json').exists())
            self.assertFalse(first['certifies_game_ok'])

    def test_failed_capture_does_not_stop_other_urls(self):
        def record(url, *args):
            if url.endswith('bad'):raise RuntimeError('navigation failed')
            return self.recorder(url, *args)
        with tempfile.TemporaryDirectory() as td, patch('aislador.capture.record_demo', side_effect=record):
            r = capture_batch(['https://demo.example/bad', 'https://demo.example/good'], Path(td), seconds=1)
            self.assertEqual([j['status'] for j in r['jobs']], ['error', 'captured'])

    def test_raw_capture_reused_after_analysis_failure(self):
        with tempfile.TemporaryDirectory() as td, patch('aislador.capture.record_demo', side_effect=self.recorder) as record:
            with patch('aislador.capture.run_extract', side_effect=ValueError('analysis failed')):
                r = capture_batch(['https://demo.example/game'], Path(td), seconds=1)
            self.assertEqual(r['jobs'][0]['status'], 'error')
            r = capture_batch(['https://demo.example/game'], Path(td), seconds=1)
            self.assertEqual(record.call_count, 1)
            self.assertEqual(r['jobs'][0]['status'], 'captured')

    def test_interrupted_recording_is_not_reused_as_complete_har(self):
        with tempfile.TemporaryDirectory() as td:
            def interrupted(url, target, *args):
                target.write_text('{incomplete', encoding='utf-8')
                raise RuntimeError('browser closed')
            with patch('aislador.capture.record_demo', side_effect=interrupted):
                r=capture_batch(['https://demo.example/game'],Path(td),seconds=1)
                self.assertEqual(r['jobs'][0]['status'],'error')
            with patch('aislador.capture.record_demo',side_effect=self.recorder) as record:
                r=capture_batch(['https://demo.example/game'],Path(td),seconds=1)
                self.assertEqual(r['jobs'][0]['status'],'captured')
                record.assert_called_once()

    def test_bootstrap_limit_and_capture_warnings_are_visible(self):
        from aislador.engine import analyze
        r=analyze({'log':{'entries':[],'_aisladorCapture':{'warnings':['WS_CAPTURE_LIMIT']}}})
        self.assertIn('CAPTURE:WS_CAPTURE_LIMIT',r['summary']['warnings'])
        self.assertIn('BOOTSTRAP_CAPTURE_NOT_GAMEPLAY_COVERAGE',r['summary']['warnings'])

    def test_invalid_urls_and_limits_rejected_before_browser(self):
        for url in ('file:///private', 'javascript:alert(1)', 'https://user:pass@example.org', 'about:blank'):
            with self.assertRaises(ValueError):validate_urls([url])
        with tempfile.TemporaryDirectory() as td, patch('aislador.capture.record_demo') as record:
            with self.assertRaises(ValueError):capture_batch(['https://demo.example'], Path(td), seconds=0)
            with self.assertRaises(ValueError):capture_batch(['https://demo.example'], Path(td), max_games=0)
            record.assert_not_called()

    def test_cli_exposes_capture_and_requires_explicit_demo(self):
        from aislador.cli import parser
        args = parser().parse_args(['capture', 'https://demo.example', '--demo'])
        self.assertTrue(args.demo)
        self.assertEqual(args.command, 'capture')

    def test_tester_spin_selection_is_readonly_and_samples_engine_families(self):
        from aislador.capture import tester_spin_urls
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / 'tester.sqlite3'
            with closing(sqlite3.connect(db)) as con:
                con.execute('CREATE TABLE games (provider,slug,url,symbol,last_status)')
                con.executemany('INSERT INTO games VALUES (?,?,?,?,?)', [
                    ('playtech','a','https://catalog.example/a','gpas_sample','PARCIAL'),
                    ('playtech','b','https://catalog.example/b','gpas_other','PARCIAL'),
                    ('playtech','c','https://catalog.example/c','legacy_sample','PARCIAL'),
                    ('playtech','d','https://catalog.example/d','pop_sample','PARCIAL'),
                    ('playtech','e','https://catalog.example/e','already_ok','OK')])
                con.commit()
            before=db.read_bytes()
            urls=tester_spin_urls(db,'playtech',3)
            self.assertEqual(len(urls),3)
            self.assertTrue(any('game=gpas_' in u for u in urls))
            self.assertTrue(any('game=pop_' in u for u in urls))
            self.assertTrue(any('game=legacy_' in u for u in urls))
            self.assertFalse(any('already_ok' in u for u in urls))
            self.assertEqual(before,db.read_bytes())
            self.assertEqual(len(tester_spin_urls(db,'playtech',None)),4)

    def test_catalog_queue_advances_to_next_uncaptured_game(self):
        with tempfile.TemporaryDirectory() as td, patch('aislador.capture.record_demo',side_effect=self.recorder) as record:
            urls=['https://demo.example/a','https://demo.example/b']
            first=capture_batch(urls,Path(td),seconds=1,max_games=1)
            second=capture_batch(urls,Path(td),seconds=1,max_games=1)
            self.assertEqual(record.call_count,2)
            self.assertEqual(second['pending'],0)

    def test_same_output_cannot_run_two_captures_at_once(self):
        from aislador.capture import _queue_lock
        with tempfile.TemporaryDirectory() as td, _queue_lock(Path(td)):
            with self.assertRaises(ValueError):capture_batch(['https://demo.example'],Path(td))


if __name__ == '__main__':unittest.main()
