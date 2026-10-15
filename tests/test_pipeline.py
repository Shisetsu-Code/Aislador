import base64,json,tempfile,unittest
from pathlib import Path
from aislador.engine import analyze,write_bundle
from aislador.har import load_har,frames_from
from aislador.profiles import get_profiles,detect_provider


def entry(url='https://demo.example/api/spin',body=None,response=None,mime='application/json'):
    return {'request':{'method':'POST','url':url,'postData':{'mimeType':'application/json','text':json.dumps(body or {'action':'spin'})}},
        'response':{'status':200,'content':{'mimeType':mime,'text':json.dumps(response or {'balance':90,'win':0})}}}

class PipelineTests(unittest.TestCase):
    def test_known_visual_assets_removed_but_transactions_preserved(self):
        e=entry('https://api.hacksawgaming.com/api/play/bet',{'action':'newAction','token':'secret123'},{'newMechanic':{'choices':[0,1]},'balance':90})
        asset=entry('https://cdn.example/sheet.png',response={'texture':'big'},mime='image/png')
        asset['request']={'method':'GET','url':'https://cdn.example/sheet.png'}
        d={'log':{'entries':[asset,e]}}
        r=analyze(d,provider='hacksaw')
        self.assertEqual(r['summary']['events'],1)
        self.assertTrue(r['novelties'])
        self.assertEqual(r['events'][0]['ref'],'http:1')
        self.assertNotIn('secret123',json.dumps(r))
        self.assertIn('newMechanic',json.dumps(r['novelties']))
    def test_http_missing_body_never_looks_complete(self):
        e=entry();e['response']['content'].pop('text')
        r=analyze({'log':{'entries':[e]}},provider='pragmatic')
        self.assertIn('MISSING_RESPONSE_BODY',json.dumps(r['novelties']))
    def test_base64_response_and_urlencoded_request(self):
        e=entry();e['request']['postData']={'mimeType':'application/x-www-form-urlencoded','text':'action=doSpin&c=0.2&session=secret123'}
        e['response']['content']={'mimeType':'text/plain','encoding':'base64','text':base64.b64encode(b'na=s&balance=90&newFlag=1').decode()}
        r=analyze({'log':{'entries':[e]}},provider='pragmatic')
        self.assertEqual(r['events'][0]['action'],'doSpin')
        self.assertEqual(r['events'][0]['response']['body']['balance'],'90')
        self.assertNotIn('secret123',json.dumps(r))
    def test_firefox_and_hardfire_websocket_formats(self):
        d={'log':{'entries':[{'request':{'url':'wss://example/game'},'_webSocketMessages':[
            {'type':'send','data':'{"id":"a","action":"spin"}'},{'type':'receive','data':'{"id":"a","win":4}'}]}]}}
        fs=frames_from(d);self.assertEqual([f['direction'] for f in fs],['sent','received'])
        r=analyze(d,provider='redtiger');self.assertEqual(len(r['events']),2)
        self.assertEqual(r['events'][1]['paired_ref'],r['events'][0]['ref'])
        self.assertEqual(len(r['events'][1]['transitions']),0)
    def test_unknown_transport_payload_stays_visible(self):
        d={'log':{'entries':[{'request':{'url':'wss://example/game'},'_webSocketFrames':[{'direction':'received','opcode':2,'payloadData':'opaque'}]}]}}
        r=analyze(d,provider='belatra')
        self.assertEqual(len(r['events']),1)
        self.assertIn('OPAQUE',json.dumps(r['novelties']))
    def test_same_shape_different_actions_are_not_merged(self):
        d={'log':{'entries':[entry(body={'action':'spin'}),entry(body={'action':'collect'})]}}
        r=analyze(d,provider='redtiger')
        self.assertEqual(len(r['patterns']),2)
    def test_new_field_in_known_action_is_novel(self):
        r=analyze({'log':{'entries':[entry(body={'action':'doSpin'},response={'balance':90,'alienChoice':[1,2]})]}},provider='pragmatic')
        self.assertIn('alienChoice',json.dumps(r['novelties']))
    def test_transaction_never_removed_by_image_suffix(self):
        r=analyze({'log':{'entries':[entry(url='https://example/api/spin.png')]}},provider='hacksaw')
        self.assertEqual(r['summary']['events'],1)
    def test_output_is_new_and_source_never_changed(self):
        with tempfile.TemporaryDirectory() as td:
            source=Path(td)/'input.har';source.write_text(json.dumps({'log':{'entries':[entry()]}}))
            before=source.read_bytes();r=analyze(load_har(source),provider='pragmatic')
            dest=Path(td)/'result';write_bundle(r,dest)
            self.assertTrue((dest/'novedades.ndjson').is_file())
            self.assertTrue((dest/'resumen.md').is_file())
            self.assertEqual(source.read_bytes(),before)
            with self.assertRaises(FileExistsError):write_bundle(r,dest)
    def test_evolution_host_is_not_enough_to_decide(self):
        self.assertIsNone(detect_provider('https://games.evolution.com/',{}))
    def test_unknown_binary_get_is_preserved(self):
        e=entry('https://example/unknown/data',mime='application/octet-stream')
        e['request']={'method':'GET','url':'https://example/unknown/data'}
        r=analyze({'log':{'entries':[e]}},provider='ka_gaming')
        self.assertEqual(r['summary']['events'],1)
    def test_known_visual_json_atlas_is_context_not_protocol(self):
        e=entry('https://cdn.example/resources/sheets/atlas.json',response={'frames':{'sprite':{'frame':{'x':0}}},'meta':{'image':'atlas.png'}})
        e['request']={'method':'GET','url':'https://cdn.example/resources/sheets/atlas.json'}
        r=analyze({'log':{'entries':[e]}},provider='hacksaw')
        self.assertEqual(r['summary']['events'],0)
        self.assertEqual(r['context'][0]['kind'],'visual_json')
    def test_pragmatic_action_can_be_in_query_without_post_body(self):
        e=entry();e['request']={'method':'GET','url':'https://example/gameService?action=doSpin&c=0.2'}
        r=analyze({'log':{'entries':[e]}},provider='pragmatic')
        self.assertEqual(r['events'][0]['action'],'doSpin')
    def test_shared_evolution_route_identifies_redtiger(self):
        self.assertEqual(detect_provider('https://games.evolution.com/platform/game/spin',{}),'redtiger')

    def test_known_api_error_is_novel_even_with_reviewed_pattern(self):
        d={'log':{'entries':[entry(body={'action':'doSpin'},response={'errorCode':7,'balance':90})]}}
        first=analyze(d,provider='pragmatic')
        r=analyze(d,provider='pragmatic',knowledge={first['events'][0]['pattern']})
        self.assertIn('SERVER_ERROR',r['events'][0]['novelty_reasons'])
    def test_session_aliases_do_not_leak(self):
        d={'log':{'entries':[entry(body={'session_uuid':'private-alias','sc':'private-key','uid':'private-user'})]}}
        r=analyze(d,provider='belatra')
        self.assertNotIn('private-alias',json.dumps(r))
        self.assertNotIn('private-key',json.dumps(r))
        self.assertNotIn('private-user',json.dumps(r))
    def test_nolimit_inner_action_is_not_outer_normal_type(self):
        d={'log':{'entries':[{'request':{'url':'wss://unknown/'} ,'_webSocketFrames':[{'direction':'sent','payloadData':'{"type":"normal","content":{"type":"zeroBet","bet":"0.00"}}'}]}]}}
        r=analyze(d,provider='nolimit_city')
        self.assertEqual(r['events'][0]['action'],'zeroBet')
    def test_atlas_arrays_and_font_files_are_context(self):
        atlas=entry('https://cdn/resources/default/intro/a.json',response={'frames':[],'animations':{},'meta':{'image':'a.png'}})
        atlas['request']={'method':'GET','url':'https://cdn/resources/default/intro/a.json'}
        font=entry('https://cdn/resources/fonts/a.fnt',mime='text/plain');font['request']={'method':'GET','url':'https://cdn/resources/fonts/a.fnt'}
        r=analyze({'log':{'entries':[atlas,font]}},provider='nolimit_city')
        self.assertEqual(r['summary']['events'],0)

    def test_reviewed_shape_does_not_hide_new_choice_values(self):
        a=analyze({'log':{'entries':[entry(response={'options':[0,1]})]}},provider='pragmatic')
        b=analyze({'log':{'entries':[entry(response={'options':[0,1,2]})]}},provider='pragmatic',knowledge={a['events'][0]['pattern']})
        self.assertNotEqual(a['events'][0]['pattern'],b['events'][0]['pattern'])
        self.assertTrue(b['novelties'])
    def test_changing_money_keeps_same_shape_without_losing_values(self):
        a=analyze({'log':{'entries':[entry(response={'balance':1,'win':0})]}},provider='pragmatic')
        b=analyze({'log':{'entries':[entry(response={'balance':2,'win':1})]}},provider='pragmatic')
        self.assertEqual(a['events'][0]['pattern'],b['events'][0]['pattern'])
        self.assertEqual(b['events'][0]['response']['body']['win'],1)
    def test_source_digest_is_standard_sha256(self):
        import hashlib
        from aislador.sanitize import digest
        self.assertEqual(digest(b'abc'),hashlib.sha256(b'abc').hexdigest())

    def test_sensitive_ka_aliases_are_redacted(self):
        from aislador.sanitize import clean,safe_url
        self.assertNotIn('PRIVATE',json.dumps(clean({'ak':'PRIVATE','u':'PRIVATE','accessKey':'PRIVATE'})))
        self.assertNotIn('PRIVATE',safe_url('https://example/spin?ak=PRIVATE&u=PRIVATE'))
    def test_hacksaw_statuscode_error_cannot_be_reviewed_away(self):
        a=analyze({'log':{'entries':[entry(response={'statusCode':0})]}},provider='hacksaw')
        b=analyze({'log':{'entries':[entry(response={'statusCode':13})]}},provider='hacksaw',knowledge={a['events'][0]['pattern']})
        self.assertIn('SERVER_ERROR',b['events'][0]['novelty_reasons'])
    def test_partial_global_websocket_view_does_not_lose_entry_response(self):
        send={'direction':'sent','payload':'{"id":"x","action":"spin"}','url':'wss://example/game'}
        receive={'direction':'received','payloadData':'{"id":"x","win":1}'}
        d={'log':{'_warpWebSockets':[send],'entries':[{'request':{'url':'wss://example/game'},'_webSocketFrames':[{'direction':'sent','payloadData':send['payload']},receive]}]}}
        r=analyze(d,provider='redtiger')
        self.assertEqual(len(r['events']),2)
        self.assertEqual(r['events'][0]['paired_ref'],r['events'][1]['ref'])
    def test_form_params_and_query_preserve_duplicate_values(self):
        e=entry();e['request']['postData']={'params':[{'name':'choice','value':'1'},{'name':'choice','value':'2'}]}
        e['request']['url']='https://example/spin?choice=1&choice=2'
        r=analyze({'log':{'entries':[e]}},provider='redtiger')
        self.assertEqual(r['events'][0]['request']['body']['choice'],['1','2'])
        self.assertEqual(r['events'][0]['request']['query']['choice'],['1','2'])
    def test_asset_spine_is_removed_on_non_resources_paths(self):
        e=entry('https://cdn/game/assets/hd/spine/symbols.json',response={'skeleton':{},'bones':[],'slots':[],'skins':[],'animations':{}})
        e['request']={'method':'GET','url':'https://cdn/game/assets/hd/spine/symbols.json'}
        r=analyze({'log':{'entries':[e]}},provider='hacksaw')
        self.assertEqual(r['summary']['events'],0)

    def test_embedded_audio_json_is_visual_context(self):
        e=entry('https://cdn/game/sounds.ogg.json',response={'sounds':[{'name':'spin','data':'A'*1000}]})
        e['request']={'method':'GET','url':'https://cdn/game/sounds.ogg.json'}
        r=analyze({'log':{'entries':[e]}},provider='pragmatic')
        self.assertEqual(r['summary']['events'],0)
    def test_known_atlas_shapes_and_wasm_have_context_references(self):
        es=[]
        for path in ('a.atlas','a.shapes.txt','vendor/a.wasm'):
            e=entry('https://cdn/'+path,mime='text/plain');e['request']={'method':'GET','url':'https://cdn/'+path};es.append(e)
        r=analyze({'log':{'entries':es}},provider='redtiger')
        self.assertEqual(r['summary']['events'],0)
        self.assertEqual(len(r['context']),3)

    def test_new_semantic_field_in_asset_like_json_is_not_hidden(self):
        e=entry('https://cdn/resources/sheets/atlas.json',response={'frames':{},'meta':{'image':'a.png'},'newPurchaseOptions':[1,2]})
        e['request']={'method':'GET','url':'https://cdn/resources/sheets/atlas.json'}
        r=analyze({'log':{'entries':[e]}},provider='hacksaw')
        self.assertEqual(r['summary']['events'],1)
        self.assertIn('newPurchaseOptions',json.dumps(r['novelties']))

    def test_string_content_inside_websocket_does_not_crash(self):
        d={'log':{'entries':[{'request':{'url':'wss://example/game'},'_webSocketFrames':[{'direction':'received','payloadData':'{"content":"unknown-wire"}'}]}]}}
        r=analyze(d,provider='bgaming')
        self.assertEqual(r['summary']['events'],1)

    def test_provider_specific_credentials_are_redacted_in_all_views(self):
        from aislador.sanitize import clean,safe_url
        aliases=['mgckey','launch_token','play_token','csrfTokenHeaderValue','drops_token','profile_token','gamelist_token','challenges_token','quests_token','shop_token','ne_evo_token','wrapper_token','huid','idv','ida','wstoken']
        for alias in aliases:
            with self.subTest(alias=alias):
                self.assertNotIn('PRIVATE',json.dumps(clean({alias:'PRIVATE'})))
                self.assertNotIn('PRIVATE',safe_url('https://example/game?'+alias+'=PRIVATE'))
                self.assertNotIn('PRIVATE',str(clean('var '+alias+'="PRIVATE";')))

    def test_one_spin_wire_prefix_is_decoded_and_init_ids_removed(self):
        payload='A/u2'+json.dumps({'type':'0','key':'PRIVATEKEY','data':'PRIVATEUSER,PRIVATESESSION,freeplay,Example,1.2.3,demo,EUR'})
        d={'log':{'entries':[{'request':{'url':'wss://gs.1spin4win.com:10443/game'},'_webSocketFrames':[{'direction':'sent','payloadData':payload}]}]}}
        r=analyze(d,provider='1spin4win')
        self.assertEqual(r['summary']['opaque_events'],0)
        self.assertIn('Example',json.dumps(r))
        self.assertNotIn('PRIVATE',json.dumps(r))

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError):analyze({'log':{'entries':[]}},provider='invented')
    def test_invalid_or_incomplete_har_rejected(self):
        with self.assertRaises(ValueError):analyze({'events':[]})

if __name__=='__main__':unittest.main()
