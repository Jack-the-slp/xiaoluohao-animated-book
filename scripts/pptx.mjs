import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {execFileSync} from 'node:child_process';

const [manifestPath,finalPath,modulePath,skillDir,python,helper]=process.argv.slice(2);
const {Presentation,PresentationFile}=await import(pathToFileURL(modulePath).href);
const book=JSON.parse(await fs.readFile(manifestPath,'utf8'));
const work=path.dirname(manifestPath), root=path.dirname(path.dirname(work));
const review=path.join(root,'review',path.basename(finalPath,'.pptx'));
await fs.mkdir(review,{recursive:true});
const presentation=Presentation.create({slideSize:{width:1280,height:720}});
const colors={paper:'#FCF8EC',ink:'#294632',leaf:'#3E6143',orange:'#B85D36',muted:'#758167'};
const allPaths=[book.logo,...book.roles.map(r=>r.cover),...book.pages.flatMap(p=>[p.background,p.gif])].filter(Boolean);
const assets=new Map(await Promise.all([...new Set(allPaths)].map(async p=>[p,new Uint8Array(await fs.readFile(p))])));
const targets=[];
function image(slide,p,x,y,w,h,alt,fit='contain'){
  if(!p)return;
  const contentType=p.endsWith('.gif')?'image/gif':p.endsWith('.png')?'image/png':p.endsWith('.webp')?'image/webp':'image/jpeg';
  slide.images.add({blob:assets.get(p),contentType,alt,fit,position:{left:x,top:y,width:w,height:h}});
}
function text(slide,name,value,x,y,w,h,size=24,color=colors.ink,bold=false,align='left',target){
  const q=slide.shapes.add({name,geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  q.text=value; q.text.style={typeface:'Microsoft YaHei',fontSize:size,color,bold,alignment:align,
    verticalAlignment:'middle',insets:0,autoFit:'none',wrap:'none'};
  if(target!==undefined)targets.push({shape:q,target});
  return q;
}
function slide(){return presentation.slides.add({width:1280,height:720,background:{fill:colors.paper}});}
function logo(s,x=80,y=104){image(s,book.logo,x,y,52,78,'小螺号 Logo');}
function footer(s,y=565){text(s,'brand-footer',book.footer,80,y,520,28,16,colors.muted);}
const N=book.actions.length, C=book.roles.length;
const cover=slide();logo(cover,80,80);
text(cover,'cover-eyebrow','小螺号动画书',80,194,490,38,24,colors.muted);
const coverLines=book.coverLines.slice(0,3), titleHeight=coverLines.length>2?72:86, titleTop=coverLines.length>2?231:253;
coverLines.forEach((line,i)=>text(cover,`cover-title-${i}`,line.replace(/[？?]$/,''),80,titleTop+i*titleHeight,510,titleHeight,
  line.length>7?48:coverLines.length>2?54:62,i?colors.orange:colors.ink,true));
text(cover,'cover-subtitle','看动作，读句子',80,465,490,42,26,colors.muted);
text(cover,'cover-start','选择角色',80,550,200,42,27,colors.leaf,true,'left',2);
footer(cover,628);image(cover,book.roles[0].cover,672,112,520,520,book.roles[0].name);
const directory=slide();logo(directory,80,48);
text(directory,'directory-title','选择一个角色',160,65,900,60,40,colors.ink,true);
const cols=Math.min(4,C), rows=Math.ceil(C/cols), rowHeight=Math.min(224,448/rows);
book.roles.forEach((r,i)=>{
  const row=Math.floor(i/cols), inRow=Math.min(cols,C-row*cols), start=80+(1120-inRow*280)/2;
  const x=start+(i%cols)*280, y=150+row*rowHeight;
  image(directory,r.cover,x+15,y,250,rowHeight-52,r.name);
  text(directory,`directory-${r.id}`,r.name,x+15,y+rowHeight-50,250,40,28,colors.leaf,true,'center',3+i*N);
});footer(directory,628);
text(directory,'action-count',`每个角色 ${N} 个动作`,900,628,300,28,19,colors.muted,false,'right');
for(let pi=0;pi<book.pages.length;pi++){
  const p=book.pages[pi], s=slide(), ri=book.roles.findIndex(r=>r.id===p.role), ai=book.actions.findIndex(a=>a.key===p.key);
  logo(s);text(s,'action-number',`${String(ai+1).padStart(2,'0')} / ${String(N).padStart(2,'0')}`,438,120,130,30,18,colors.muted,false,'right');
  text(s,'sentence-subject',p.subject,80,231,500,68,48,colors.ink,true);
  text(s,'sentence-place',p.place,80,303,500,66,42,colors.ink,true);
  text(s,'sentence-action',p.word+'。',80,375,520,86,p.word.length>4?58:64,colors.orange,true);
  text(s,'action-note',p.note,80,492,520,46,23,colors.muted);footer(s);
  image(s,p.background,672,100,528,528,p.place,'cover');
  image(s,p.gif,672,100,528,528,p.subject+p.place+p.word+'。');
  text(s,'directory-nav','角色目录',80,46,116,36,21,colors.leaf,true,'left',2);
  if(C<=8)book.roles.forEach((r,i)=>text(s,`role-nav-${r.id}`,r.name,224+i*(976/C),46,976/C,36,21,
    r.id===p.role?colors.orange:colors.muted,r.id===p.role,'center',3+i*N+ai));
  if(N<=8)book.actions.forEach((a,i)=>text(s,`action-nav-${a.key}`,a.word,80+i*(1120/N),640,1120/N,34,19,
    a.key===p.key?colors.orange:colors.muted,a.key===p.key,'center',3+ri*N+i));
  text(s,'previous-nav','上一页',80,603,125,32,20,colors.leaf,false,'left',pi===0?2:pi+2);
  text(s,'next-nav',pi===book.pages.length-1?'回到封面':'下一页',448,603,150,32,20,colors.leaf,false,'right',pi===book.pages.length-1?1:pi+4);
}
for(const {shape,target} of targets)shape.text.get(shape.text.toString()).link={uri:`/ppt/slides/slide${target}.xml`,isExternal:false,action:'ppaction://hlinksldjump'};
if(presentation.slides.items.length!==book.slideCount)throw new Error('Unexpected slide count');
for(let i=0;i<book.slideCount;i++){
  const png=await presentation.export({slide:presentation.slides.getItem(i),format:'png',scale:1});
  await fs.writeFile(path.join(review,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
}
await (await PresentationFile.exportPptx(presentation)).save(path.join(work,'raw.pptx'));
execFileSync(python,[helper,'patch',path.join(work,'raw.pptx'),path.join(work,'candidate.pptx'),manifestPath],
  {stdio:'inherit',env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8',PYTHONDONTWRITEBYTECODE:'1'}});
process.env.RUNTIME_NODE_MODULES=path.resolve(path.dirname(modulePath),'../../..');
const {finalizePresentation}=await import(pathToFileURL(path.join(skillDir,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({workspaceDir:root,candidatePath:path.join(work,'candidate.pptx'),finalPath,
  explicitTotalSlideCount:book.slideCount,pythonExecutable:python,
  integrityValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(skillDir,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit'],
  fontPolicy:{basis:'design',families:['Microsoft YaHei']},verifyArtifactToolImport:true,
  receiptPath:path.join(review,'file-validation.json')});
await fs.writeFile(path.join(review,'build-result.json'),JSON.stringify({result,links:targets.length},null,2));
console.log(JSON.stringify({finalPath,slides:book.slideCount,links:targets.length}));
