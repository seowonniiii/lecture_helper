from pathlib import Path
import re

# ---------- V4 patches ----------
app_path=Path('v4/app.js')
index_path=Path('v4/index.html')
css_path=Path('v4/styles.css')
app=app_path.read_text(encoding='utf-8')
index=index_path.read_text(encoding='utf-8')
css=css_path.read_text(encoding='utf-8')

# pdf-lib for flattening Pencil/highlighter strokes onto the original PDF.
if "pdf-lib@1.17.1" not in app:
    anchor="import {Document,Packer,Paragraph,TextRun,HeadingLevel,ImageRun,PageBreak,AlignmentType,Table,TableRow,TableCell,WidthType,PageOrientation} from 'https://cdn.jsdelivr.net/npm/docx@9.8.1/+esm';"
    if anchor not in app: raise SystemExit('V4 docx import anchor missing')
    app=app.replace(anchor, "import { PDFDocument, rgb } from 'https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/+esm';\n"+anchor, 1)

# Make transcript drawer optional and closed by default.
old='<div class="nhead"><div><small style="color:#6b7280;font-weight:800">PAGE NOTE</small><h2><span id="pLabel">1</span>p.</h2></div></div>'
new='<div class="nhead"><div><small style="color:#6b7280;font-weight:800">PAGE NOTE</small><h2><span id="pLabel">1</span>p.</h2></div><button id="transcriptToggle" class="tool transcript-toggle" type="button">전사문 보기</button></div>'
if old in index:
    index=index.replace(old,new,1)
elif 'id="transcriptToggle"' not in index:
    raise SystemExit('V4 nhead anchor missing')

index=index.replace('<div class="noteSplit">','<div id="noteSplit" class="noteSplit transcript-off">',1) if 'id="noteSplit"' not in index else index
index=index.replace('<section class="notePane transcriptPane">','<section id="transcriptPane" class="notePane transcriptPane hidden">',1) if 'id="transcriptPane"' not in index else index

# Add annotated PDF download button.
old='<button id="printBtn">PDF<br><small>A4 4쪽 배치</small></button><button id="md">Markdown<br><small>전사문+수업 필기</small></button><button id="json">JSON<br><small>전체 백업</small></button>'
new='<button id="printBtn">PDF<br><small>A4 4쪽 배치</small></button><button id="annotatedPdf">필기 PDF<br><small>원본+펜/형광</small></button><button id="md">Markdown<br><small>수업필기→전사문</small></button><button id="json">JSON<br><small>전체 백업</small></button>'
if old in index:
    index=index.replace(old,new,1)
elif 'id="annotatedPdf"' not in index:
    raise SystemExit('V4 export buttons anchor missing')

# Register elements.
old_map="mdHighlight:$('mdHighlight'),pinPopover:$('pinPopover')"
new_map="mdHighlight:$('mdHighlight'),transcriptToggle:$('transcriptToggle'),transcriptPane:$('transcriptPane'),noteSplit:$('noteSplit'),annotatedPdf:$('annotatedPdf'),pinPopover:$('pinPopover')"
if old_map in app:
    app=app.replace(old_map,new_map,1)
elif "annotatedPdf:$('annotatedPdf')" not in app:
    raise SystemExit('V4 element map anchor missing')

# Transcript drawer behavior.
if 'function setTranscriptVisible(' not in app:
    anchor="E.mdModeRendered.onclick=()=>setMdViewMode('rendered');"
    helper="""let transcriptVisible=false;\nfunction setTranscriptVisible(show){\n  transcriptVisible=!!show;\n  E.transcriptPane?.classList.toggle('hidden',!transcriptVisible);\n  E.noteSplit?.classList.toggle('transcript-off',!transcriptVisible);\n  if(E.transcriptToggle)E.transcriptToggle.textContent=transcriptVisible?'전사문 닫기':'전사문 보기';\n}\nE.transcriptToggle.onclick=()=>setTranscriptVisible(!transcriptVisible);\n\n"""
    if anchor not in app: raise SystemExit('V4 MD mode anchor missing')
    app=app.replace(anchor,helper+anchor,1)

# Default transcript closed on startup.
old_start='db=await openDb();setMdViewMode(mdViewMode);setupMic();await restoreLast();'
new_start='db=await openDb();setMdViewMode(mdViewMode);setTranscriptVisible(false);setupMic();await restoreLast();'
if old_start in app:
    app=app.replace(old_start,new_start,1)
elif 'setTranscriptVisible(false);setupMic();await restoreLast();' not in app:
    raise SystemExit('V4 startup anchor missing')

# Replace Markdown export: PAGE marker -> class notes -> optional transcript.
start=app.find('E.md.onclick=async()=>{')
end=app.find('E.json.onclick=async()=>{',start)
if start<0 or end<0: raise SystemExit('V4 markdown export block missing')
new_md=r'''E.md.onclick=async()=>{if(!project)return;await Promise.all([saveNote(),saveTranscript()]);const notes=await getByProject(NS,project.id),trans=await getByProject(TS,project.id);let out=`# ${E.title.value||project.title}\n\n`;for(let p=1;p<=pdfDoc.numPages;p++){const n=notes.find(x=>x.page===p),t=trans.find(x=>x.page===p),noteText=n?.text||'',transcriptText=t?.text||'';out+=`<<<PAGE ${p}>>>\n\n### 수업필기\n${noteText}${transcriptText.trim()?`\n\n### 전사문\n${transcriptText}`:''}\n\n`}downloadBlob(new Blob([out],{type:'text/markdown;charset=utf-8'}),`${safe(E.title.value)}_notes.md`)};
'''
app=app[:start]+new_md+app[end:]

# Annotated PDF export. Strokes are normalized to page coordinates; comments/pins stay out.
if 'async function exportAnnotatedPdf(' not in app:
    anchor='E.md.onclick=async()=>{'
    helper=r'''function pdfColor(hex){
  const s=String(hex||'#e11d48').replace('#','');
  const full=s.length===3?s.split('').map(x=>x+x).join(''):s.padEnd(6,'0').slice(0,6);
  return rgb(parseInt(full.slice(0,2),16)/255,parseInt(full.slice(2,4),16)/255,parseInt(full.slice(4,6),16)/255);
}
async function exportAnnotatedPdf(){
  if(!project?.pdfBlob){toast('원본 PDF를 먼저 열어주세요');return}
  try{
    toast('필기 PDF 생성 중…');await saveAnnotation();
    const bytes=await project.pdfBlob.arrayBuffer();
    const outDoc=await PDFDocument.load(bytes,{ignoreEncryption:false});
    const annotations=await getByProject(AS,project.id);
    const pages=outDoc.getPages();
    for(const row of annotations){
      const pageNo=Number(row.page);if(!Number.isInteger(pageNo)||pageNo<1||pageNo>pages.length)continue;
      const page=pages[pageNo-1],{width:w,height:h}=page.getSize();
      for(const stroke of row.strokes||[]){
        const pts=stroke?.points||[];if(!pts.length)continue;
        const color=pdfColor(stroke.color),opacity=stroke.tool==='highlight'?.25:1;
        const base=Math.max(.55,(Number(stroke.width)||2.2)*.75);
        if(pts.length===1){
          const p=pts[0],pressure=stroke.tool==='highlight'?1:(.45+.9*Math.max(.05,Math.min(1,Number(p.p)||.5)));
          page.drawCircle({x:p.x*w,y:(1-p.y)*h,size:(base*pressure)/2,color,opacity});
          continue;
        }
        for(let i=1;i<pts.length;i++){
          const a=pts[i-1],b=pts[i],pressure=stroke.tool==='highlight'?1:(.45+.9*Math.max(.05,Math.min(1,((Number(a.p)||.5)+(Number(b.p)||.5))/2)));
          page.drawLine({start:{x:a.x*w,y:(1-a.y)*h},end:{x:b.x*w,y:(1-b.y)*h},thickness:base*pressure,color,opacity});
        }
      }
    }
    const outBytes=await outDoc.save();
    downloadBlob(new Blob([outBytes],{type:'application/pdf'}),`${safe(E.title.value)}_필기.pdf`);toast('필기 PDF 저장 완료');
  }catch(err){console.error(err);toast('필기 PDF를 만들지 못했습니다')}
}
E.annotatedPdf.onclick=exportAnnotatedPdf;

'''
    app=app.replace(anchor,helper+anchor,1)

if '/* V4 transcript drawer */' not in css:
    css+=r'''

/* V4 transcript drawer */
.transcript-toggle{min-height:32px;font-size:10px}.noteSplit.transcript-off{grid-template-columns:minmax(0,1fr)}.noteSplit.transcript-off .classNotePane{min-height:440px}.noteSplit.transcript-off .classNotePane .editor{min-height:360px}.noteSplit:not(.transcript-off) .classNotePane .editor{min-height:260px}
'''

app_path.write_text(app,encoding='utf-8')
index_path.write_text(index,encoding='utf-8')
css_path.write_text(css,encoding='utf-8')

# ---------- V5 compact app ----------
v5=Path('v5');v5.mkdir(exist_ok=True)
(v5/'index.html').write_text(r'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#111827"><title>Lecture Helper V5 Compact</title><link rel="stylesheet" href="./styles.css"></head>
<body>
<header class="top"><div class="brand"><b>LH <span>V5</span></b><small id="status">PDF를 열어주세요</small></div><div class="actions"><label class="btn primary">PDF 열기<input id="pdfInput" type="file" accept="application/pdf" hidden></label><button id="exportMd" class="btn">MD 저장</button></div></header>
<main class="app">
  <section class="navbar"><button id="prev" class="navbtn">‹</button><input id="pageInput" type="number" min="1" value="1"><span>/ <b id="total">0</b></span><button id="next" class="navbtn">›</button><input id="title" class="title" placeholder="강의 제목"></section>
  <section class="thumbshell"><button id="thumbPrev" class="railbtn">‹</button><div id="thumbRail" class="thumbrail"><div class="empty">PDF를 열면 현재 페이지 주변 썸네일이 여기에 표시됨</div></div><button id="thumbNext" class="railbtn">›</button></section>
  <section class="note"><div class="notehead"><div><small>수업 필기</small><h2><span id="pLabel">1</span>p.</h2></div><span id="chars">0자</span></div>
    <div class="tags"><button data-tag="[시험] ">시험</button><button data-tag="[중요] ">중요</button><button data-tag="[교수설명] ">교수설명</button><button data-tag="[질문] ">질문</button><button id="time">시간</button></div>
    <textarea id="editor" placeholder="GoodNotes는 왼쪽에 두고, 여기에는 현재 페이지 수업 필기를 계속 적으세요."></textarea>
  </section>
  <footer><span id="filename"></span><span>페이지별 자동저장 · PDF 필기 없음 · MD 전용</span></footer>
</main><div id="toast" class="toast"></div><script type="module" src="./app.js"></script></body></html>''',encoding='utf-8')

(v5/'styles.css').write_text(r''':root{--bg:#eef1f5;--surface:#fff;--border:#dfe3e8;--text:#111827;--muted:#6b7280;--accent:#111827}*{box-sizing:border-box}html,body{margin:0;height:100%;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR",sans-serif;background:var(--bg);color:var(--text)}button,input,textarea{font:inherit}.top{height:52px;padding:max(6px,env(safe-area-inset-top)) 10px 6px;display:flex;align-items:center;justify-content:space-between;background:#fffffff2;border-bottom:1px solid var(--border);position:sticky;top:0;z-index:10;backdrop-filter:blur(14px)}.brand{display:flex;align-items:center;gap:8px}.brand b{font-size:13px}.brand b span{color:#0f766e}.brand small{font-size:9px;color:var(--muted)}.actions{display:flex;gap:5px}.btn,.navbtn,.railbtn{border:1px solid var(--border);background:#fff;border-radius:9px;min-height:34px;padding:0 9px}.btn.primary{background:#111827;color:#fff;border-color:#111827;font-weight:750}.app{height:calc(100vh - 52px);display:flex;flex-direction:column;min-height:0;background:#fff}.navbar{flex:0 0 auto;padding:6px 8px;display:flex;align-items:center;gap:6px;border-bottom:1px solid var(--border)}.navbar input[type=number]{width:48px;height:32px;border:1px solid var(--border);border-radius:8px;text-align:center}.title{min-width:0;flex:1;border:0;background:#f5f6f8;border-radius:8px;height:32px;padding:0 9px;font-weight:700;outline:none}.thumbshell{flex:0 0 116px;display:grid;grid-template-columns:34px minmax(0,1fr) 34px;gap:5px;align-items:stretch;padding:7px;background:#f4f5f7;border-bottom:1px solid var(--border)}.railbtn{padding:0;font-size:18px}.thumbrail{min-width:0;display:flex;align-items:center;gap:7px;overflow-x:auto;scrollbar-width:none}.thumbrail::-webkit-scrollbar{display:none}.thumb{flex:0 0 78px;height:98px;border:2px solid transparent;border-radius:9px;padding:3px;background:#d7dbe1;position:relative;display:flex;align-items:center;justify-content:center}.thumb.active{border-color:#111827;background:#fff;box-shadow:0 3px 12px #11182722}.thumb img{max-width:100%;max-height:100%;display:block;background:#fff}.thumb span{position:absolute;left:4px;top:4px;background:#111827d9;color:#fff;border-radius:999px;padding:2px 5px;font-size:8px;font-weight:800}.empty{margin:auto;color:var(--muted);font-size:10px;text-align:center;padding:10px}.note{flex:1 1 auto;min-height:0;padding:10px;display:flex;flex-direction:column;gap:7px}.notehead{display:flex;align-items:end;justify-content:space-between}.notehead small{font-size:9px;color:var(--muted);font-weight:800}.notehead h2{font-size:19px;margin:0}.notehead>span{font-size:9px;color:var(--muted)}.tags{display:flex;gap:5px;overflow-x:auto;flex:0 0 auto}.tags button{white-space:nowrap;border:1px solid var(--border);background:#fff;border-radius:999px;min-height:28px;padding:0 8px;font-size:10px;font-weight:750}.tags button:first-child{color:#b91c1c;background:#fff5f5}.tags button:nth-child(2){color:#a16207;background:#fffbeb}.tags button:nth-child(3){color:#1d4ed8;background:#eff6ff}.tags button:nth-child(4){color:#047857;background:#ecfdf5}textarea{flex:1 1 auto;min-height:180px;width:100%;resize:none;border:1px solid var(--border);border-radius:13px;background:#fbfbfc;padding:12px;outline:none;line-height:1.65;font-size:13px}textarea:focus{border-color:#9ca3af;box-shadow:0 0 0 2px #1118270d}footer{flex:0 0 auto;padding:5px 9px;border-top:1px solid var(--border);display:flex;justify-content:space-between;gap:8px;color:var(--muted);font-size:8px}footer span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.toast{position:fixed;left:50%;bottom:15px;transform:translateX(-50%);background:#111827;color:#fff;padding:8px 11px;border-radius:999px;font-size:10px;opacity:0;pointer-events:none;transition:.18s;z-index:30}.toast.show{opacity:1}@media(max-width:520px){.brand small{display:none}.thumbshell{flex-basis:106px}.thumb{flex-basis:68px;height:88px}.btn{padding:0 7px}.navbar{gap:4px}.title{font-size:11px}}''',encoding='utf-8')

(v5/'app.js').write_text(r'''import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.worker.min.mjs';
const $=id=>document.getElementById(id),E={pdfInput:$('pdfInput'),exportMd:$('exportMd'),status:$('status'),pageInput:$('pageInput'),total:$('total'),prev:$('prev'),next:$('next'),title:$('title'),thumbPrev:$('thumbPrev'),thumbNext:$('thumbNext'),thumbRail:$('thumbRail'),pLabel:$('pLabel'),chars:$('chars'),editor:$('editor'),time:$('time'),filename:$('filename'),toast:$('toast')};
const DB='lecture-helper-v5',PS='projects',NS='notes',LAST='lh-v5-last';let db,pdfDoc=null,project=null,currentPage=1,saveTimer=null,thumbGen=0;
function toast(t){E.toast.textContent=t;E.toast.classList.add('show');setTimeout(()=>E.toast.classList.remove('show'),1300)}function safe(n){return(n||'lecture').replace(/[\\/:*?"<>|]/g,'_').trim()||'lecture'}function now(){return new Intl.DateTimeFormat('ko-KR',{hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date())}function clamp(n,a,b){return Math.max(a,Math.min(b,n))}function req(r){return new Promise((res,rej)=>{r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}function done(tx){return new Promise((res,rej)=>{tx.oncomplete=res;tx.onerror=()=>rej(tx.error);tx.onabort=()=>rej(tx.error)})}
async function openDb(){return new Promise((res,rej)=>{const r=indexedDB.open(DB,1);r.onupgradeneeded=()=>{const d=r.result;if(!d.objectStoreNames.contains(PS))d.createObjectStore(PS,{keyPath:'id'});if(!d.objectStoreNames.contains(NS)){const s=d.createObjectStore(NS,{keyPath:'key'});s.createIndex('projectId','projectId')}};r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}async function put(s,o){const tx=db.transaction(s,'readwrite');tx.objectStore(s).put(o);await done(tx)}async function get(s,k){const tx=db.transaction(s);const x=await req(tx.objectStore(s).get(k));await done(tx);return x}async function getByProject(s,id){const tx=db.transaction(s);const x=await req(tx.objectStore(s).index('projectId').getAll(IDBKeyRange.only(id)));await done(tx);return x.sort((a,b)=>a.page-b.page)}function key(p){return`${project.id}:${p}`}
async function saveProject(){if(!project)return;project.title=E.title.value||project.title;project.page=currentPage;project.updated=Date.now();await put(PS,project);localStorage.setItem(LAST,project.id)}async function saveNote(){if(!project)return;await put(NS,{key:key(currentPage),projectId:project.id,page:currentPage,text:E.editor.value,updated:Date.now()});E.chars.textContent=`${E.editor.value.length}자`}function scheduleSave(){clearTimeout(saveTimer);saveTimer=setTimeout(async()=>{await Promise.all([saveProject(),saveNote()]);E.status.textContent=`저장됨 · ${now()}`},220)}
async function loadPdf(file){try{const buf=await file.arrayBuffer();pdfDoc=await pdfjsLib.getDocument({data:buf.slice(0)}).promise;project={id:`${file.name}:${file.size}:${file.lastModified}`,title:file.name.replace(/\.pdf$/i,''),filename:file.name,pdfBlob:new Blob([buf],{type:'application/pdf'}),page:1,total:pdfDoc.numPages,updated:Date.now()};currentPage=1;await put(PS,project);localStorage.setItem(LAST,project.id);E.title.value=project.title;E.filename.textContent=file.name;E.total.textContent=pdfDoc.numPages;await render();toast('PDF 열림')}catch(e){console.error(e);toast('PDF를 열지 못했습니다')}}async function restore(){try{const id=localStorage.getItem(LAST);if(!id)return;const p=await get(PS,id);if(!p?.pdfBlob)return;project=p;pdfDoc=await pdfjsLib.getDocument({data:await p.pdfBlob.arrayBuffer()}).promise;currentPage=clamp(p.page||1,1,pdfDoc.numPages);E.title.value=p.title||'';E.filename.textContent=p.filename||'';E.total.textContent=pdfDoc.numPages;await render()}catch(e){console.warn(e)}}
async function render(){if(!pdfDoc)return;currentPage=clamp(currentPage,1,pdfDoc.numPages);E.pageInput.value=currentPage;E.pLabel.textContent=currentPage;const n=await get(NS,key(currentPage));E.editor.value=n?.text||'';E.chars.textContent=`${E.editor.value.length}자`;E.status.textContent=`${currentPage}/${pdfDoc.numPages}`;await renderThumbs()}
async function renderThumbs(){const gen=++thumbGen;E.thumbRail.innerHTML='';const radius=4,start=Math.max(1,Math.min(currentPage-radius,Math.max(1,pdfDoc.numPages-radius*2))),end=Math.min(pdfDoc.numPages,start+radius*2);for(let p=start;p<=end;p++){if(gen!==thumbGen)return;const b=document.createElement('button');b.className='thumb'+(p===currentPage?' active':'');b.type='button';const lab=document.createElement('span');lab.textContent=`${p}p.`;b.appendChild(lab);const pg=await pdfDoc.getPage(p),vp=pg.getViewport({scale:.22}),c=document.createElement('canvas'),dpr=Math.min(devicePixelRatio||1,1.5);c.width=Math.round(vp.width*dpr);c.height=Math.round(vp.height*dpr);const ctx=c.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);await pg.render({canvasContext:ctx,viewport:vp}).promise;const img=document.createElement('img');img.src=c.toDataURL('image/jpeg',.72);b.appendChild(img);b.onclick=()=>go(p);E.thumbRail.appendChild(b)}requestAnimationFrame(()=>E.thumbRail.querySelector('.active')?.scrollIntoView({inline:'center',block:'nearest',behavior:'smooth'}))}
async function go(p){if(!pdfDoc)return;await saveNote();currentPage=clamp(Number(p)||1,1,pdfDoc.numPages);await saveProject();await render()}
function insert(text){const s=E.editor.selectionStart,e=E.editor.selectionEnd;E.editor.setRangeText(text,s,e,'end');E.editor.focus();scheduleSave()}
function download(text,name){const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1200)}
E.pdfInput.onchange=e=>{const f=e.target.files?.[0];if(f)loadPdf(f);e.target.value=''};E.prev.onclick=()=>go(currentPage-1);E.next.onclick=()=>go(currentPage+1);E.thumbPrev.onclick=()=>go(currentPage-1);E.thumbNext.onclick=()=>go(currentPage+1);E.pageInput.onchange=()=>go(E.pageInput.value);E.editor.addEventListener('input',scheduleSave);E.title.addEventListener('input',scheduleSave);document.querySelectorAll('[data-tag]').forEach(b=>b.onclick=()=>insert(b.dataset.tag));E.time.onclick=()=>insert(`[${now()}] `);E.exportMd.onclick=async()=>{if(!project||!pdfDoc)return;await Promise.all([saveProject(),saveNote()]);const notes=await getByProject(NS,project.id);let out=`# ${E.title.value||project.title}\n\n`;for(let p=1;p<=pdfDoc.numPages;p++){const n=notes.find(x=>x.page===p);out+=`<<<PAGE ${p}>>>\n\n### 수업필기\n${n?.text||''}\n\n`}download(out,`${safe(E.title.value)}_V5_notes.md`);toast('MD 저장 완료')};window.addEventListener('keydown',e=>{if(e.target===E.editor||e.target===E.title||e.target===E.pageInput)return;if(e.key==='ArrowLeft')go(currentPage-1);if(e.key==='ArrowRight')go(currentPage+1)});db=await openDb();await restore();''',encoding='utf-8')

print('Patched V4 and generated V5 compact')
