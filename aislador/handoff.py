"""Export non-executable observations to the matching Tester-Spin catalog entry."""
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path


def export_playtech_evidence(analysis, database, data_root):
    path=Path(analysis)/'protocol-evidence.json'
    if not path.is_file():return {'status':'no_protocol_evidence'}
    report=json.loads(path.read_text(encoding='utf-8'))
    if (report.get('schema')!='aislador/playtech-evidence/v1' or report.get('provider')!='playtech'
        or report.get('certifies_game_ok') is not False or report.get('coverage')!='observations_only'):
        raise ValueError('Informe de protocolo incompatible')
    codes=report.get('game_codes')
    if not isinstance(codes,list) or len(codes)!=1 or not isinstance(codes[0],str):
        return {'status':'ambiguous_identity'}
    with closing(sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)) as con:
        matches=con.execute('SELECT slug FROM games WHERE provider=? AND symbol=?',('playtech',codes[0])).fetchall()
    if len(matches)!=1:return {'status':'unmatched_identity'}
    slug=matches[0][0]
    if (not isinstance(slug,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.'%+~-]{0,199}",slug)
        or slug.endswith('.') or re.fullmatch(r'(?i)(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?',slug)):
        raise ValueError('Identidad de catálogo inválida')
    target=Path(data_root).resolve()/'providers'/'playtech'/slug/'analysis'/'protocol-evidence.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    temporary.replace(target)
    return {'status':'imported','symbol':codes[0],'path':str(target),'certifies_game_ok':False}
