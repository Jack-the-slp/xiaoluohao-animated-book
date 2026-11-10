"""Build, finish and verify a local animated picture-book PPTX."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import posixpath
import re
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image, ImageOps

P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/package/2006/relationships'
P14='http://schemas.microsoft.com/office/powerpoint/2010/main'
MC='http://schemas.openxmlformats.org/markup-compatibility/2006'
for prefix,uri in [('p',P),('a',A),('p14',P14),('mc',MC)]: ET.register_namespace(prefix,uri)

def sha(data): return hashlib.sha256(data).hexdigest()
def check(ok,message):
    if not ok: raise ValueError(message)
def read_json(path): return json.loads(path.read_text(encoding='utf-8'))
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def asset(root,value):
    p=(root/value).resolve()
    check(p.is_relative_to(root) and p.is_file(),f'Project-local resource required: {value}')
    return p

def gif_info(path):
    with Image.open(path) as im:
        check(im.format=='GIF' and im.n_frames>1,f'Animated GIF required: {path}')
        check('loop' not in im.info,f'GIF must stop after one play: {path}')
        duration=0
        for i in range(im.n_frames):
            im.seek(i); im.load(); duration+=im.info.get('duration',0)
        check(duration>0,f'Missing GIF duration: {path}')
        return dict(frames=im.n_frames,durationMs=duration,sha256=sha(path.read_bytes()))

def convert(source,background,dest):
    frames=[]; masks=[]; durations=[]
    with Image.open(source) as im:
        check(im.n_frames>1 and im.info.get('loop')==1,f'Once-playing animation required: {source}')
        size=im.size
        bg=ImageOps.fit(Image.open(background).convert('RGBA'),size) if background else Image.new('RGBA',size,(252,248,236,255))
        for i in range(im.n_frames):
            im.seek(i); sprite=im.convert('RGBA')
            frames.append(Image.alpha_composite(bg,sprite).convert('RGB'))
            masks.append(sprite.getchannel('A').point(lambda v:255 if v>0 else 0))
            durations.append(max(10,round(im.info.get('duration',160)/10)*10))
    sample=Image.new('RGB',(155*len(frames),155))
    for i,f in enumerate(frames): sample.paste(f.resize((155,155)),(155*i,0))
    palette=sample.quantize(colors=255)
    indexed=[]
    for f,mask in zip(frames,masks):
        q=f.quantize(palette=palette,dither=Image.Dither.NONE)
        q.paste(255,(0,0),ImageOps.invert(mask)); indexed.append(q)
    indexed[0].save(dest,save_all=True,append_images=indexed[1:],duration=durations,
                    disposal=2,transparency=255,optimize=False)
    result=gif_info(dest)
    check(result['frames']==len(frames) and result['durationMs']==sum(durations),'GIF frame/time mismatch')
    return result

def prepare(root,spec_path,work):
    spec=read_json(spec_path)
    if 'roles' in spec:  # Accept the maintained manifest used by the existing book.
        result=spec
        for role in result['roles']: role['cover']=str(asset(root,role['cover']))
        if result.get('logo'): result['logo']=str(asset(root,result['logo']))
        for page in result['pages']:
            page['gif']=str(asset(root,page['gif']))
            if page.get('background'): page['background']=str(asset(root,page['background']))
            page.update(gif_info(Path(page['gif'])))
    else:
        # The HTML project's validation also checks the full character/action matrix.
        from book import prepare as validate_book
        check(spec_path==root/'book.json','Standard projects use project/book.json')
        validate_book(root)
        scenes={s['id']:s for s in spec['scenes']}
        roles=[{**r,'subject':r.get('subject',r['name']),'cover':str(asset(root,r['cover']))} for r in spec['characters']]
        result=dict(title=spec['title'],coverLines=spec.get('coverLines',[spec['title']]),
                    logo=str(asset(root,spec['logo'])) if spec.get('logo') else None,
                    footer=spec.get('footerText','小螺号听觉言语语言康复平台：')+spec.get('footerAddress','TC-SLP.top'),
                    roles=roles,actions=[dict(key=p['key'],word=p['word']) for p in spec['pages']],pages=[])
        for role in roles:
            for page in spec['pages']:
                scene_id=page.get('scene') or spec.get('pptx',{}).get('sceneByAction',{}).get(page['key']) or spec['defaultScene']
                check(scene_id in scenes,f'Unknown PPT scene: {scene_id}')
                scene=scenes[scene_id]
                check(not page.get('pool') or scene.get('water'),
                      'Swimming needs an approved water background or pool illustration; choose a water scene for PPT')
                bg=asset(root,scene['image']) if scene.get('image') else None
                dest=work/f"{role['id']}-{page['key']}.gif"
                info=convert(asset(root,page['animations'][role['id']]),bg,dest)
                result['pages'].append(dict(role=role['id'],subject=role['subject'],key=page['key'],
                    word=page['word'],place='在'+scene['location'],note=page.get('note',''),
                    background=str(bg) if bg else None,gif=str(dest),**info))
    result.setdefault('coverLines',['谁在哪里','做什么'] if result['title']=='谁在哪里做什么' else [result['title']])
    roles=[r['id'] for r in result['roles']]; actions=[a['key'] for a in result['actions']]
    check(roles and actions,'At least one role and one action are required')
    check(len(set(roles))==len(roles) and len(set(actions))==len(actions),'Duplicate roles/actions')
    check(len(result['pages'])==len(roles)*len(actions),'Each role/action needs exactly one page')
    check({(p['role'],p['key']) for p in result['pages']}=={(r,a) for r in roles for a in actions},'Incomplete role/action matrix')
    result['pages'].sort(key=lambda p:(roles.index(p['role']),actions.index(p['key'])))
    result['slideCount']=2+len(result['pages'])
    result['transitionMs']=550
    write_json(work/'manifest.json',result)
    return result

def patch(source,dest,manifest):
    book=read_json(manifest); canonical={}; rename={}; removed=set(); links=0; transitions=0
    with zipfile.ZipFile(source) as src:
        names=set(src.namelist())
        for name in src.namelist():
            if name.startswith('ppt/media/'):
                data=src.read(name); check(data,f'Empty media: {name}')
                key=(Path(name).suffix,sha(data))
                if key in canonical: rename[name]=canonical[key]; removed.add(name)
                else: canonical[key]=name
        with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as dst:
            for entry in src.infolist():
                name=entry.filename
                if name in removed: continue
                data=src.read(name)
                if name.endswith('.rels'):
                    tree=ET.fromstring(data)
                    for rel in tree:
                        target=rel.get('Target','')
                        if target.startswith('/ppt/media/') and target[1:] in rename:
                            rel.set('Target','/'+rename[target[1:]])
                        if rel.get('Type','').endswith('/hyperlink') and target.startswith('/ppt/slides/slide'):
                            check(target[1:] in names,f'Broken slide target: {target}')
                            rel.set('Type','http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide'); links+=1
                    data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
                elif re.fullmatch(r'ppt/slides/slide\d+\.xml',name):
                    tree=ET.fromstring(data)
                    for old in list(tree.findall(f'{{{P}}}transition')): tree.remove(old)
                    trans=ET.Element(f'{{{P}}}transition',{'spd':'med','advClick':'1',f'{{{P14}}}dur':str(book['transitionMs'])})
                    number=int(re.search(r'slide(\d+)',name).group(1))
                    ET.SubElement(trans,f'{{{P}}}fade' if number<=2 else f'{{{P}}}cover',{} if number<=2 else {'dir':'l'})
                    at=next((i for i,c in enumerate(tree) if c.tag in {f'{{{P}}}timing',f'{{{P}}}extLst'}),len(tree))
                    tree.insert(at,trans); tree.set(f'{{{MC}}}Ignorable','p14'); transitions+=1
                    data=ET.tostring(tree,encoding='utf-8',xml_declaration=True)
                dst.writestr(entry,data)
    check(transitions==book['slideCount'],'Transition count mismatch')
    return dict(internalLinks=links,transitions=transitions,duplicateMediaRemoved=len(removed))

def verify(pptx,manifest,report_path):
    book=read_json(manifest); frames=0; link_count=0
    with zipfile.ZipFile(pptx) as z:
        names=set(z.namelist()); check(z.testzip() is None,'PPTX ZIP CRC failed')
        gifs=[n for n in names if n.startswith('ppt/media/') and n.endswith('.gif')]
        check({sha(z.read(n)) for n in gifs}=={p['sha256'] for p in book['pages']},'GIF bytes differ from prepared animations')
        for name in gifs:
            with Image.open(io.BytesIO(z.read(name))) as im:
                check(im.n_frames>1 and 'loop' not in im.info,'Lost animation or once-play metadata')
                frames+=im.n_frames
                for i in range(im.n_frames): im.seek(i); im.load()
        slide_names=[n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
        check(len(slide_names)==book['slideCount'],'Slide count mismatch')
        for i,name in enumerate(sorted(slide_names,key=lambda n:int(re.search(r'slide(\d+)',n).group(1))),1):
            tree=ET.fromstring(z.read(name)); trans=tree.find(f'{{{P}}}transition')
            check(trans is not None and trans.get('advClick')=='1' and trans.get('advTm') is None,'Manual page turn missing')
            check(trans.get(f'{{{P14}}}dur')=='550','Transition duration mismatch')
            if i>=3:
                page=book['pages'][i-3]; texts=[t.text or '' for t in tree.findall(f'.//{{{A}}}t')]
                for t in [page['subject'],page['place'],page['word']+'。',book['footer']]:check(t in texts,f'Sentence/brand mismatch: slide {i}')
            # All foreground text/images stay inside the enlarged safe frame.
            for xfrm in tree.findall(f'.//{{{A}}}xfrm'):
                off=xfrm.find(f'{{{A}}}off'); ext=xfrm.find(f'{{{A}}}ext')
                if off is None or ext is None: continue
                x,y,cx,cy=[int(v) for v in (off.get('x'),off.get('y'),ext.get('cx'),ext.get('cy'))]
                check(x>=76*9525 and y>=44*9525 and x+cx<=1204*9525 and y+cy<=676*9525,f'Outside safe margins: slide {i}')
        for name in names:
            if not name.endswith('.rels'): continue
            for rel in ET.fromstring(z.read(name)):
                target=rel.get('Target','')
                if target.startswith('/ppt/slides/'):
                    check(target[1:] in names,'Broken slide link'); link_count+=1
        check(all(len(z.read(n)) for n in names if n.startswith('ppt/media/')),'Empty media part')
    report=dict(checkedAtUTC=datetime.now(timezone.utc).isoformat(),path=str(pptx),bytes=pptx.stat().st_size,
        sha256=sha(pptx.read_bytes()),slides=book['slideCount'],animatedMedia=len(gifs),frames=frames,
        gifBytesMatch=True,sentencesAndBrandMatch=True,safeMarginsPassed=True,
        transition='cover-left',transitionMs=550,manualAdvance=True,internalSlideRelationships=link_count,
        nativePowerPoint='not_checked_by_script')
    write_json(report_path,report); return report

def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build'); build.add_argument('project',type=Path); build.add_argument('--manifest',type=Path)
    build.add_argument('--out',type=Path,required=True); build.add_argument('--node',type=Path,required=True)
    build.add_argument('--presentations-skill',type=Path,required=True)
    patcher=sub.add_parser('patch'); patcher.add_argument('source',type=Path); patcher.add_argument('dest',type=Path); patcher.add_argument('manifest',type=Path)
    verifier=sub.add_parser('verify'); verifier.add_argument('pptx',type=Path); verifier.add_argument('manifest',type=Path); verifier.add_argument('report',type=Path)
    args=parser.parse_args()
    if args.command=='patch': result=patch(args.source,args.dest,args.manifest)
    elif args.command=='verify': result=verify(args.pptx,args.manifest,args.report)
    else:
        root=args.project.resolve(); out=args.out.resolve(); check(out.is_relative_to(root),'Output must be inside project')
        check(not out.exists(),'Use a new output filename; existing deliverables are preserved')
        work=root/'.pptx-build'/out.stem; check(not work.exists(),'Use a fresh build/output name')
        work.mkdir(parents=True); out.parent.mkdir(parents=True,exist_ok=True)
        prepare(root,(args.manifest or root/'book.json').resolve(),work)
        skill=args.presentations_skill.resolve(); node=args.node.resolve()
        module=node.parent.parent/'node_modules'/'@oai/artifact-tool/dist/artifact_tool.mjs'
        check(module.is_file(),'Artifact Tool runtime missing; use load_workspace_dependencies paths')
        subprocess.run([str(node),str(skill/'container_tools/mark_artifact_operation_started.mjs'),
                        '--operation-kind','create','--expected-output-count','1','--output-format','pptx'],cwd=skill,check=True)
        subprocess.run([str(node),str(Path(__file__).with_suffix('.mjs')),str(work/'manifest.json'),str(out),
                        str(module),str(skill),sys.executable,str(Path(__file__).resolve())],check=True)
        result=verify(out,work/'manifest.json',root/'review'/out.stem/'delivery-validation.json')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as e:
        print(str(e),file=sys.stderr); sys.exit(2)
