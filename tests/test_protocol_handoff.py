import json
import tempfile
import unittest
from pathlib import Path
from aislador.engine import analyze, write_bundle


def document():
    def frame(data, direction='received'):
        return {'url':'wss://gpas-stg.playtechone.com/socket.io/1/websocket/test',
                'direction':direction,'payload':'3:::'+json.dumps({'data':data})}
    cost={'uuid':'cost-a','cost':15,'name':'default','parameters':{'startingMode':'Standard'}}
    return {'log':{'entries':[],'_warpWebSockets':[
        frame({'_type':'InitGameSession','gameCode':'gpas_fixture','token':'private'},'sent'),
        frame({'_type':'com.pt.gpas.config.GetGameConfigurationResponse','data':[
            {'scope':{'betType':'default'},'content':{'game':{'coinSizes':[1,2], 'costConfiguration':[cost]}}},
            {'scope':{'betType':'freespin'},'content':{'game':{'costConfiguration':[cost]}}}]}),
        frame({'_type':'com.pt.casino.platform.game.GameCommand','betCost':100,'stakeAmount':100,
               'winAmount':20,'gameRoundClosed':False,'gameData':{'nextRound':'PICK','requestParameters':{'selectedIndex':1}}})]}}


class HandoffTests(unittest.TestCase):
    def test_server_and_opaque_errors_survive_report(self):
        d=document();frames=d['log']['_warpWebSockets']
        frames.append({**frames[0],'direction':'received','payload':'3:::{"data":{"_type":"SystemError","error":"denied"}}'})
        frames.append({**frames[0],'direction':'received','payload':'3:::{incomplete'})
        from aislador.codecs.playtech import evidence_report
        report=evidence_report(analyze(d))
        issues=[i for row in report['unresolved'] for i in row['issues']]
        self.assertIn('SERVER_ERROR',issues)
        self.assertIn('OPAQUE_WEBSOCKET',issues)

    def test_report_preserves_declarations_choices_and_does_not_invent_purchases(self):
        r=analyze(document())
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'result';write_bundle(r,out)
            report=json.loads((out/'protocol-evidence.json').read_text())
        self.assertEqual(report['schema'],'aislador/playtech-evidence/v1')
        self.assertEqual(report['game_codes'],['gpas_fixture'])
        self.assertEqual(len(report['configurations']),1)
        self.assertEqual(report['configurations'][0]['data'][1]['scope']['betType'],'freespin')
        self.assertEqual(report['rounds'][0]['gameData']['nextRound'],'PICK')
        self.assertFalse(report['certifies_game_ok'])
        self.assertEqual(report['coverage'],'observations_only')
        self.assertNotIn('private',json.dumps(report))
        self.assertNotIn('purchase_count',report)

    def test_no_playtech_report_for_other_provider(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'result';write_bundle(analyze({'log':{'entries':[]}}),out)
            self.assertFalse((out/'protocol-evidence.json').exists())
