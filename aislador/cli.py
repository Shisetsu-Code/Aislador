"""Local extraction and explicit, auditable pattern review."""
import argparse,glob,json,re,sys
from pathlib import Path
from .har import load_har,body_text,MAX_BODY
from .engine import analyze,write_bundle
from .profiles import get_profiles
from .sanitize import clean,digest


def load_knowledge(path):
    if path is None:return set()
    d=json.loads(Path(path).read_text(encoding='utf-8'))
    if d.get('schema')!='aislador/knowledge/v1' or not isinstance(d.get('reviewed'),dict):raise ValueError('Base de patrones inválida.')
    return set(d['reviewed'])


def run_extract(paths,provider='auto',out=Path('salidas'),knowledge=None,progress=print):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);results=[]
    reviewed=load_knowledge(knowledge)
    for path in paths:
        path=Path(path);progress('Leyendo '+path.name)
        document=load_har(path)
        result=analyze(document,provider=provider,knowledge=reviewed,source_name=path.name,source_sha256=digest(path.read_bytes()))
        name=(re.sub(r'[^A-Za-z0-9._-]+','_',path.stem)[:70].strip('.') or 'captura')+'-'+result['summary']['source_sha256'][:8]
        destination=out/name;counter=1
        while destination.exists():counter+=1;destination=out/(name+'-'+str(counter))
        write_bundle(result,destination)
        results.append({'output':str(destination.resolve()),**result['summary']})
        progress(str(result['summary']['events'])+' eventos; '+str(result['summary']['novel_patterns'])+' patrones por revisar.')
    return results


def context_excerpt(path,ref,find=None,radius=400,limit=12000):
    document=load_har(path)
    match=re.fullmatch(r'http:(\d+)',ref)
    if not match:raise ValueError('Contexto requiere una referencia HTTP, por ejemplo http:20.')
    entries=document['log']['entries'];index=int(match[1])
    if index>=len(entries):raise ValueError('Referencia fuera de la captura.')
    text,issue=body_text((entries[index].get('response') or {}).get('content') or {})
    if issue:raise ValueError('El cuerpo de contexto no está disponible: '+issue)
    text=clean(text)
    if not isinstance(text,str):text=json.dumps(text,ensure_ascii=True,indent=2)
    offset=text.find(find) if find else 0
    if find and offset<0:raise ValueError('No se encontró el texto solicitado.')
    start=max(0,offset-radius) if find else 0
    end=min(len(text),offset+len(find)+radius if find else limit,start+limit)
    return {'ref':ref,'start':start,'end':end,'total_chars':len(text),'offset_space':'sanitized_text','truncated':start>0 or end<len(text),'text':clean(text[start:end])}


def review_pattern(patterns_path,identifier,note,knowledge_path):
    rows=json.loads(Path(patterns_path).read_text(encoding='utf-8'))
    candidate=next((row for row in rows if row.get('id')==identifier),None)
    if candidate is None:raise ValueError('El patrón no existe en ese informe.')
    if not note.strip():raise ValueError('La revisión necesita una nota que explique lo comprobado.')
    path=Path(knowledge_path)
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema':'aislador/knowledge/v1','reviewed':{}}
    if data.get('schema')!='aislador/knowledge/v1' or not isinstance(data.get('reviewed'),dict):raise ValueError('Base de patrones inválida.')
    data['reviewed'][identifier]={'provider':candidate['provider'],'note':clean(note),'signature':candidate['signature']}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=True,indent=2)+'\n',encoding='utf-8')
    return {'reviewed':identifier,'knowledge':str(path)}


def parser():
    p=argparse.ArgumentParser(prog='aislador',description='Aísla protocolo y novedades de HAR locales, sin ejecutar jugadas.')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('providers',help='mostrar perfiles y cobertura real')
    sub.add_parser('gui',help='abrir la ventana local')
    ex=sub.add_parser('extract',help='extraer uno o varios HAR')
    ex.add_argument('paths',nargs='+');ex.add_argument('--provider',default='auto',choices=['auto',*get_profiles()])
    ex.add_argument('--out',type=Path,default=Path('salidas'));ex.add_argument('--knowledge',type=Path)
    ex.add_argument('--recursive',action='store_true');ex.add_argument('--json',action='store_true',help='resumen para herramientas, sin progreso en stdout')
    ctx=sub.add_parser('context',help='leer una ventana acotada de un recurso original')
    ctx.add_argument('har',type=Path);ctx.add_argument('--ref',required=True);ctx.add_argument('--find');ctx.add_argument('--radius',type=int,default=400);ctx.add_argument('--limit',type=int,default=12000)
    ev=sub.add_parser('event',help='leer un evento por referencia')
    ev.add_argument('directory',type=Path);ev.add_argument('--ref',required=True)
    review=sub.add_parser('review',help='registrar un patrón ya revisado explícitamente')
    review.add_argument('patterns',type=Path);review.add_argument('--pattern',required=True);review.add_argument('--note',required=True);review.add_argument('--knowledge',type=Path,required=True)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=='providers':
            result=[{'key':p['key'],'name':p['name'],'protocol_status':p['protocol_status'],'notes':p.get('notes')} for p in get_profiles().values()]
        elif args.command=='gui':
            from .gui import main as gui_main
            gui_main();return 0
        elif args.command=='extract':
            files=[]
            for raw in args.paths:
                matches=[Path(raw)] if Path(raw).exists() else [Path(p) for p in glob.glob(raw)]
                for path in matches:
                    files.extend(sorted(path.rglob('*.har') if args.recursive else path.glob('*.har')) if path.is_dir() else [path])
            files=list(dict.fromkeys(p.resolve() for p in files))
            if not files:raise ValueError('No se encontraron archivos HAR.')
            result=run_extract(files,args.provider,args.out,args.knowledge,progress=(lambda _:None) if args.json else lambda message:print(message,file=sys.stderr))
        elif args.command=='context':
            if not 0<=args.radius<=100000 or not 1<=args.limit<=MAX_BODY:raise ValueError('Ventana fuera del límite.')
            result=context_excerpt(args.har,args.ref,args.find,args.radius,args.limit)
        elif args.command=='event':
            result=None
            with (args.directory/'eventos.ndjson').open(encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line)
                    if row.get('ref')==args.ref:result=row;break
            if result is None:raise ValueError('Referencia no encontrada en ese informe.')
        else:result=review_pattern(args.patterns,args.pattern,args.note,args.knowledge)
        print(json.dumps(result,ensure_ascii=True,indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError,RecursionError) as exc:
        print('No se pudo completar: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
