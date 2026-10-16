import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from aislador.handoff import export_playtech_evidence


class ExportTests(unittest.TestCase):
    def test_report_export_uses_catalog_identity_and_does_not_modify_database(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);analysis=p/'analysis';analysis.mkdir();db=p/'db.sqlite3'
            with closing(sqlite3.connect(db)) as con:
                con.execute('CREATE TABLE games(provider,slug,symbol)')
                con.execute('INSERT INTO games VALUES (?,?,?)',('playtech','fixture','gpas_fixture'));con.commit()
            report={'schema':'aislador/playtech-evidence/v1','provider':'playtech','game_codes':['gpas_fixture'],
                    'certifies_game_ok':False,'coverage':'observations_only','configurations':[],'rounds':[]}
            (analysis/'protocol-evidence.json').write_text(json.dumps(report));before=db.read_bytes()
            r=export_playtech_evidence(analysis,db,p/'data')
            target=p/'data/providers/playtech/fixture/analysis/protocol-evidence.json'
            self.assertTrue(target.exists());self.assertEqual(r['status'],'imported')
            self.assertEqual(json.loads(target.read_text()),report)
            self.assertEqual(db.read_bytes(),before)
            report['game_codes']=['other'];(analysis/'protocol-evidence.json').write_text(json.dumps(report))
            self.assertEqual(export_playtech_evidence(analysis,db,p/'data')['status'],'unmatched_identity')

    def test_missing_or_mixed_identity_does_not_export(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            self.assertEqual(export_playtech_evidence(p,p/'missing.db',p/'data')['status'],'no_protocol_evidence')
            (p/'protocol-evidence.json').write_text(json.dumps({'schema':'aislador/playtech-evidence/v1',
                'game_codes':['a','b'],'certifies_game_ok':False,'coverage':'observations_only','provider':'playtech'}))
            self.assertEqual(export_playtech_evidence(p,p/'missing.db',p/'data')['status'],'ambiguous_identity')
