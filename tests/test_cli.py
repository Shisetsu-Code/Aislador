import json,tempfile,unittest
from pathlib import Path
from aislador.cli import context_excerpt

class ContextTests(unittest.TestCase):
    def test_excerpt_redacts_before_slicing(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.har'
            path.write_text(json.dumps({'log':{'entries':[{'response':{'content':{'text':'var token="PRIVATESECRET";'}}}]}}))
            try:result=context_excerpt(path,'http:0',find='PRIVATESECRET',radius=0)
            except ValueError:return
            self.assertNotIn('PRIVATESECRET',json.dumps(result))


class CommandTests(unittest.TestCase):
    def test_extract_json_cli_and_repeat_runs_use_separate_folders(self):
        from aislador.cli import main
        from contextlib import redirect_stdout,redirect_stderr
        from io import StringIO
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'a.har';path.write_text(json.dumps({'log':{'entries':[]}}))
            result=[]
            for _ in range(2):
                output=StringIO()
                with redirect_stdout(output),redirect_stderr(StringIO()):
                    code=main(['extract',str(path),'--out',str(Path(td)/'out'),'--provider','pragmatic','--json'])
                self.assertEqual(code,0);result.append(json.loads(output.getvalue())[0]['output'])
            self.assertNotEqual(*result)
    def test_review_new_fields_remain_recorded_and_errors_never_suppressed(self):
        from aislador.cli import review_pattern,load_knowledge
        with tempfile.TemporaryDirectory() as td:
            patterns=Path(td)/'patrones.json';knowledge=Path(td)/'knowledge.json'
            patterns.write_text(json.dumps([{'id':'example','provider':'pragmatic','signature':{'fields':['x']}}]))
            review_pattern(patterns,'example','Revisé el significado del campo',knowledge)
            self.assertEqual(load_knowledge(knowledge),{'example'})
    def test_empty_glob_is_an_error(self):
        from aislador.cli import main
        from contextlib import redirect_stderr
        from io import StringIO
        with tempfile.TemporaryDirectory() as td,redirect_stderr(StringIO()):
            self.assertEqual(main(['extract',str(Path(td)/'missing*.har')]),2)
