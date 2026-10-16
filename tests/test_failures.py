import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from aislador.failures import drain_failures,follow_failures


class FailureCaptureTests(unittest.TestCase):
    def test_worker_remains_available_for_deferred_retries(self):
        with tempfile.TemporaryDirectory() as td:
            clock=[0]
            def sleep(_):clock[0]+=10
            outcomes=[{'pending':1,'processed':[]},{'pending':1,'processed':[]},{'pending':0,'processed':[]}]
            with patch('aislador.failures.drain_failures',side_effect=outcomes) as drain,patch('aislador.failures.time.monotonic',side_effect=lambda:clock[0]),patch('aislador.failures.time.sleep',side_effect=sleep):
                follow_failures(Path(td)/'db',Path(td)/'out')
            self.assertEqual(drain.call_count,3)

    def setup_database(self,path):
        with closing(sqlite3.connect(path)) as con:
            con.execute('CREATE TABLE test_results(id INTEGER PRIMARY KEY,provider,slug,game_url,symbol,status)')
            con.executemany('INSERT INTO test_results VALUES (?,?,?,?,?,?)',[
                (1,'playtech','a','https://www.playtechone.com/a','gpas_a','OK'),
                (2,'playtech','b','https://www.playtechone.com/b','gpas_b','PARCIAL'),
                (3,'playtech','c','https://www.playtechone.com/c','gpas_c','ERROR')])
            con.commit()

    def recorder(self,urls,out,**kwargs):
        out.mkdir(parents=True,exist_ok=True)
        return {'jobs':[{'status':'captured','analysis':str(out/'analysis')}],'families':str(out/'familias.json')}

    def test_only_failures_and_no_duplicate_capture_on_resume(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);db=p/'db.sqlite3';self.setup_database(db)
            with patch('aislador.failures.capture_batch',side_effect=self.recorder) as capture:
                a=drain_failures(db,p/'out',max_games=1)
                b=drain_failures(db,p/'out',max_games=1)
                c=drain_failures(db,p/'out',max_games=1)
            self.assertEqual(capture.call_count,2)
            self.assertEqual(a['pending'],1);self.assertEqual(b['pending'],0)
            self.assertEqual(c['processed'],[])
            self.assertTrue((p/'out/revision.json').exists())

    def test_new_failure_of_same_game_gets_new_capture(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);db=p/'db.sqlite3';self.setup_database(db)
            with patch('aislador.failures.capture_batch',side_effect=self.recorder) as capture:
                drain_failures(db,p/'out',after_id=2)
                with closing(sqlite3.connect(db)) as con:
                    con.execute('INSERT INTO test_results VALUES (?,?,?,?,?,?)',(4,'playtech','c','https://www.playtechone.com/c','gpas_c','PARCIAL'));con.commit()
                drain_failures(db,p/'out')
            self.assertEqual(capture.call_count,2)
            self.assertNotEqual(capture.call_args_list[0].args[1],capture.call_args_list[1].args[1])

    def test_failure_does_not_block_following_game_and_retry_reuses_job(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);db=p/'db.sqlite3';self.setup_database(db)
            with patch('aislador.failures.capture_batch',side_effect=[RuntimeError('failed'),self.recorder([],p/'ok')]):
                result=drain_failures(db,p/'out',max_games=2)
            self.assertEqual(len(result['processed']),2)
            self.assertEqual(result['pending'],1)

    def test_success_after_failure_supersedes_old_request(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);db=p/'db.sqlite3';self.setup_database(db)
            with closing(sqlite3.connect(db)) as con:
                con.execute('INSERT INTO test_results VALUES (?,?,?,?,?,?)',(4,'playtech','b','https://www.playtechone.com/b','gpas_b','OK'));con.commit()
            with patch('aislador.failures.capture_batch',side_effect=self.recorder) as capture:
                drain_failures(db,p/'out')
            self.assertEqual(capture.call_count,1)
