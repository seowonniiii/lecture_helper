import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';
import {Document,Packer,Paragraph,TextRun,HeadingLevel,ImageRun,PageBreak,AlignmentType} from 'https://cdn.jsdelivr.net/npm/docx@9.8.1/+esm';
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.worker.min.mjs';

const $=id=>document.getElementById(id);
const E={shell:$('shell'),pdfInput:$('pdfInput'),emptyPdf:$('emptyPdf'),backupInput:$('backupInput'),status:$('status'),title:$('title'),filename:$('filename'),stage:$('stage'),stageInner:$('stageInner'),empty:$('empty'),pageWrap:$('pageWrap'),pdfCanvas:$('pdfCanvas'),inkCanvas:$('inkCanvas'),pinLayer:$('pinLayer'),page:$('page'),total:$('total'),pLabel:$('pLabel'),prev:$('prev'),next:$('next'),fit:$('fit'),inkColor:$('inkColor'),thin:$('thin'),thick:$('thick'),undo:$('undo'),redo:$('redo'),editor:$('editor'),chars:$('chars'),time:$('time'),mic:$('mic'),pinList:$('pinList'),docx:$('docx'),printBtn:$('printBtn'),md:$('md'),json:$('json'),toast:$('toast'),printArea:$('printArea'),layoutToggle:$('layoutToggle'),inputBadge:$('inputBadge')};

let db,pdfDoc=null,project=null,currentPage=1,scale=1.15,fit=true,renderTask=null,tool='pen',pageData={strokes:[],redo:[],pins:[]},saveTimer=null,recognition=null,listening=false,lineWidth=2.2;
let stylusPointerId=null,stylusDrawing=false,currentStroke=null,lastStylusPoint=null;
let touchState={mode:null,startTime:0,startX:0,startY:0,lastX:0,lastY:0,moved:false,initialDistance:0,initialScale:1,midX:0,midY:0};
let penPointerSeenUntil=0,renderGeneration=0;
const DB='lecture-helper-v4',PS='projects',NS='notes',AS='annotations',LAST='lh-v4-last';

function toast(t){E.toast.textContent=t;E.toast.classList.add('show');setTimeout(()=>E.toast.classList.remove('show'),1500)}
function nowTime(){return new Intl.DateTimeFormat('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date())}
function safe(n){return(n||'lecture').replace(/[\\/:*?"<>|]/g,'_').trim()||'lecture'}
function req(r){return new Promise((res,rej)=>{r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}
function done(tx){return new Promise((res,rej)=>{tx.oncomplete=res;tx.onerror=()=>rej(tx.error);tx.onabort=()=>rej(tx.error)})}
function clamp(n,a,b){return Math.max(a,Math.min(b,n))}
function pointerPressure(e){const p=Number(e.pressure);return p>0?clamp(p,.08,1):.5}
function touchPressure(t){const p=Number(t.force);return p>0?clamp(p,.08,1):.5}
function isStylusTouch(t){return !!t && (t.touchType==='stylus'||t.touchType==='pencil')}

async function openDb(){return new Promise((res,rej)=>{const r=indexedDB.open(DB,1);r.onupgradeneeded=()=>{const d=r.result;if(!d.objectStoreNames.contains(PS))d.createObjectStore(PS,{keyPath:'id'});if(!d.objectStoreNames.contains(NS)){const s=d.createObjectStore(NS,{keyPath:'key'});s.createIndex('projectId','projectId')}if(!d.objectStoreNames.contains(AS)){const s=d.createObjectStore(AS,{keyPath:'key'});s.createIndex('projectId','projectId')}};r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}
async function put(store,obj){const tx=db.transaction(store,'readwrite');tx.objectStore(store).put(obj);await done(tx)}
async function get(store,key){const tx=db.transaction(store);const x=await req(tx.objectStore(store).get(key));await done(tx);return x}
async function getByProject(store,id){const tx=db.transaction(store);const x=await req(tx.objectStore(store).index('projectId').getAll(IDBKeyRange.only(id)));await done(tx);return x.sort((a,b)=>a.page-b.page)}
function noteKey(p){return `${project.id}:${p}`}
async function saveProject(){if(!project)return;project.title=E.title.value||project.title;project.page=currentPage;project.updated=Date.now();await put(PS,project);localStorage.setItem(LAST,project.id)}
async function saveNote(){if(!project)return;await put(NS,{key:noteKey(currentPage),projectId:project.id,page:currentPage,text:E.editor.value,updated:Date.now()});E.chars.textContent=`${E.editor.value.length}자`}
async function saveAnnotation(){if(!project)return;await put(AS,{key:noteKey(currentPage),projectId:project.id,page:currentPage,strokes:pageData.strokes,pins:pageData.pins,updated:Date.now()})}
function scheduleSave(){clearTimeout(saveTimer);saveTimer=setTimeout(async()=>{await Promise.all([saveProject(),saveNote(),saveAnnotation()]);E.status.textContent=`저장됨 · ${nowTime()}`},250)}

async function loadPdfFile(file){
  try{
    const buf=await file.arrayBuffer();
    pdfDoc=await pdfjsLib.getDocument({data:buf.slice(0)}).promise;
    const id=`${file.name}:${file.size}:${file.lastModified}`;
    project={id,title:file.name.replace(/\.pdf$/i,''),filename:file.name,pdfBlob:new Blob([buf],{type:'application/pdf'}),page:1,total:pdfDoc.numPages,created:Date.now(),updated:Date.now()};
    await put(PS,project);localStorage.setItem(LAST,id);currentPage=1;E.title.value=project.title;E.filename.textContent=file.name;E.total.textContent=pdfDoc.numPages;E.empty.classList.add('hidden');E.pageWrap.classList.remove('hidden');E.status.textContent=`${pdfDoc.numPages}페이지 · V4 Pencil Engine`;await renderPage();toast('PDF를 열었습니다');
  }catch(e){console.error(e);toast('PDF를 열지 못했습니다')}
}
async function restoreLast(){
  try{const id=localStorage.getItem(LAST);if(!id)return;const p=await get(PS,id);if(!p||!p.pdfBlob)return;project=p;const buf=await p.pdfBlob.arrayBuffer();pdfDoc=await pdfjsLib.getDocument({data:buf}).promise;currentPage=clamp(p.page||1,1,pdfDoc.numPages);E.title.value=p.title||'';E.filename.textContent=p.filename||'';E.total.textContent=pdfDoc.numPages;E.empty.classList.add('hidden');E.pageWrap.classList.remove('hidden');E.status.textContent=`복원됨 · ${pdfDoc.numPages}페이지`;await renderPage()}catch(e){console.warn('restore failed',e)}
}

function fitScale(viewport){const w=Math.max(280,E.stage.clientWidth-36),h=Math.max(280,E.stage.clientHeight-36);return Math.min(w/viewport.width,h/viewport.height,2.2)}
async function renderPage(){
  if(!pdfDoc)return;const gen=++renderGeneration;currentPage=clamp(currentPage,1,pdfDoc.numPages);E.page.value=currentPage;E.pLabel.textContent=currentPage;E.total.textContent=pdfDoc.numPages;
  const page=await pdfDoc.getPage(currentPage);const base=page.getViewport({scale:1});if(fit)scale=fitScale(base);const vp=page.getViewport({scale});
  const dpr=Math.min(window.devicePixelRatio||1,2.5);const pc=E.pdfCanvas,ic=E.inkCanvas;pc.width=Math.round(vp.width*dpr);pc.height=Math.round(vp.height*dpr);pc.style.width=`${vp.width}px`;pc.style.height=`${vp.height}px`;ic.width=Math.round(vp.width*dpr);ic.height=Math.round(vp.height*dpr);ic.style.width=`${vp.width}px`;ic.style.height=`${vp.height}px`;E.pageWrap.style.width=`${vp.width}px`;E.pageWrap.style.height=`${vp.height}px`;
  const ctx=pc.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);if(renderTask)try{renderTask.cancel()}catch{}renderTask=page.render({canvasContext:ctx,viewport:vp});try{await renderTask.promise}catch(e){if(e?.name!=='RenderingCancelledException')throw e}if(gen!==renderGeneration)return;
  const [n,a]=await Promise.all([get(NS,noteKey(currentPage)),get(AS,noteKey(currentPage))]);E.editor.value=n?.text||'';E.chars.textContent=`${E.editor.value.length}자`;pageData={strokes:a?.strokes||[],redo:[],pins:a?.pins||[]};drawAllStrokes();renderPins();E.status.textContent=`${currentPage}/${pdfDoc.numPages} · ${Math.round(scale*100)}%`;
}
function pagePointFromClient(clientX,clientY,pressure=.5){const r=E.inkCanvas.getBoundingClientRect();return{x:clamp((clientX-r.left)/r.width,0,1),y:clamp((clientY-r.top)/r.height,0,1),p:pressure}}
function canvasPoint(pt){const r=E.inkCanvas.getBoundingClientRect();return{x:pt.x*r.width,y:pt.y*r.height,p:pt.p??.5}}
function strokeWidth(stroke,p){const base=(stroke.width||2.2)*scale;const pressure=stroke.tool==='highlight'?1:(.45+.9*clamp(p??.5,.05,1));return base*pressure}
function setupInkCtx(){const ctx=E.inkCanvas.getContext('2d');const dpr=Math.min(window.devicePixelRatio||1,2.5);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.lineCap='round';ctx.lineJoin='round';return ctx}
function clearInk(){const ctx=E.inkCanvas.getContext('2d');ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,E.inkCanvas.width,E.inkCanvas.height);ctx.restore()}
function drawStroke(stroke){if(!stroke?.points?.length)return;const ctx=setupInkCtx();const pts=stroke.points.map(canvasPoint);ctx.save();ctx.globalCompositeOperation=stroke.tool==='highlight'?'multiply':'source-over';ctx.strokeStyle=stroke.color||'#e11d48';ctx.globalAlpha=stroke.tool==='highlight'?.28:1;if(pts.length===1){ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.globalAlpha=stroke.tool==='highlight'?.28:1;ctx.arc(pts[0].x,pts[0].y,strokeWidth(stroke,pts[0].p)/2,0,Math.PI*2);ctx.fill();ctx.restore();return}
  for(let i=0;i<pts.length-1;i++){const a=pts[Math.max(0,i-1)],b=pts[i],c=pts[i+1];const start={x:(a.x+b.x)/2,y:(a.y+b.y)/2};const end={x:(b.x+c.x)/2,y:(b.y+c.y)/2};ctx.beginPath();ctx.moveTo(start.x,start.y);ctx.quadraticCurveTo(b.x,b.y,end.x,end.y);ctx.lineWidth=stroke.tool==='highlight'?strokeWidth(stroke,1)*3.2:strokeWidth(stroke,(b.p+c.p)/2);ctx.stroke()}
  ctx.restore()}
function drawAllStrokes(){clearInk();for(const s of pageData.strokes)drawStroke(s)}
function drawLiveSegment(stroke){drawAllStrokes();drawStroke(stroke)}
function pointDistanceToStroke(pt,stroke){let min=Infinity;for(const q of stroke.points||[]){const dx=pt.x-q.x,dy=pt.y-q.y;min=Math.min(min,dx*dx+dy*dy)}return Math.sqrt(min)}
function eraseAt(pt){const radius=Math.max(.012,(lineWidth*3)/(Math.max(E.inkCanvas.clientWidth,1)));const before=pageData.strokes.length;pageData.strokes=pageData.strokes.filter(s=>pointDistanceToStroke(pt,s)>radius);if(pageData.strokes.length!==before){pageData.redo=[];drawAllStrokes();scheduleSave()}}

function beginStylus(clientX,clientY,pressure,id='touch-stylus'){
  if(!project||tool==='pin')return;if(tool==='erase'){stylusDrawing=true;stylusPointerId=id;eraseAt(pagePointFromClient(clientX,clientY,pressure));return}
  stylusDrawing=true;stylusPointerId=id;currentStroke={id:`s-${Date.now()}-${Math.random().toString(36).slice(2)}`,tool,color:tool==='highlight'?'#facc15':E.inkColor.value,width:lineWidth,points:[pagePointFromClient(clientX,clientY,pressure)]};lastStylusPoint=currentStroke.points[0];
}
function continueStylus(clientX,clientY,pressure){if(!stylusDrawing)return;const pt=pagePointFromClient(clientX,clientY,pressure);if(tool==='erase'){eraseAt(pt);return}if(!currentStroke)return;const dx=pt.x-(lastStylusPoint?.x??pt.x),dy=pt.y-(lastStylusPoint?.y??pt.y);if(dx*dx+dy*dy<0.0000004)return;currentStroke.points.push(pt);lastStylusPoint=pt;drawLiveSegment(currentStroke)}
function endStylus(){if(!stylusDrawing)return;stylusDrawing=false;stylusPointerId=null;if(currentStroke?.points?.length){pageData.strokes.push(currentStroke);pageData.redo=[];currentStroke=null;lastStylusPoint=null;drawAllStrokes();scheduleSave()}else currentStroke=null}

function handlePenPointerDown(e){if(e.pointerType!=='pen'||!project)return;penPointerSeenUntil=performance.now()+1200;e.preventDefault();e.stopPropagation();try{E.inkCanvas.setPointerCapture(e.pointerId)}catch{}beginStylus(e.clientX,e.clientY,pointerPressure(e),e.pointerId)}
function handlePenPointerMove(e){if(e.pointerType!=='pen'||e.pointerId!==stylusPointerId)return;e.preventDefault();const events=typeof e.getCoalescedEvents==='function'?e.getCoalescedEvents():[e];for(const ce of events)continueStylus(ce.clientX,ce.clientY,pointerPressure(ce))}
function handlePenPointerEnd(e){if(e.pointerType!=='pen'||e.pointerId!==stylusPointerId)return;e.preventDefault();endStylus()}
E.inkCanvas.addEventListener('pointerdown',handlePenPointerDown,{passive:false});E.inkCanvas.addEventListener('pointermove',handlePenPointerMove,{passive:false});E.inkCanvas.addEventListener('pointerup',handlePenPointerEnd,{passive:false});E.inkCanvas.addEventListener('pointercancel',handlePenPointerEnd,{passive:false});

function touchDistance(a,b){return Math.hypot(a.clientX-b.clientX,a.clientY-b.clientY)}
function getFingerTouches(ev){return [...ev.touches].filter(t=>!isStylusTouch(t))}
function onTouchStart(e){
  const stylus=[...e.changedTouches].find(isStylusTouch);if(stylus&&performance.now()>penPointerSeenUntil){e.preventDefault();beginStylus(stylus.clientX,stylus.clientY,touchPressure(stylus),`stylus-${stylus.identifier}`);return}
  const f=getFingerTouches(e);if(!f.length)return;e.preventDefault();if(f.length>=2){touchState={mode:'pinch',startTime:performance.now(),startX:0,startY:0,lastX:0,lastY:0,moved:true,initialDistance:touchDistance(f[0],f[1]),initialScale:scale,midX:(f[0].clientX+f[1].clientX)/2,midY:(f[0].clientY+f[1].clientY)/2};E.pageWrap.classList.remove('touching-edge')}else{touchState={mode:'pan',startTime:performance.now(),startX:f[0].clientX,startY:f[0].clientY,lastX:f[0].clientX,lastY:f[0].clientY,moved:false,initialDistance:0,initialScale:scale,midX:0,midY:0};const r=E.inkCanvas.getBoundingClientRect(),x=(f[0].clientX-r.left)/r.width;if(x<.12||x>.88)E.pageWrap.classList.add('touching-edge')}
}
function onTouchMove(e){
  const stylus=[...e.touches].find(isStylusTouch);if(stylus&&stylusDrawing&&String(stylusPointerId).startsWith('stylus-')){e.preventDefault();continueStylus(stylus.clientX,stylus.clientY,touchPressure(stylus));return}
  const f=getFingerTouches(e);if(!f.length)return;e.preventDefault();if(f.length>=2){if(touchState.mode!=='pinch'){touchState.mode='pinch';touchState.initialDistance=touchDistance(f[0],f[1]);touchState.initialScale=scale}const d=touchDistance(f[0],f[1]);if(touchState.initialDistance>0){const newScale=clamp(touchState.initialScale*(d/touchState.initialDistance),.55,4);if(Math.abs(newScale-scale)>.015){scale=newScale;fit=false;requestScaleRender()}}touchState.moved=true;E.pageWrap.classList.remove('touching-edge');return}
  if(touchState.mode==='pan'&&f.length===1){const dx=f[0].clientX-touchState.lastX,dy=f[0].clientY-touchState.lastY;if(Math.hypot(f[0].clientX-touchState.startX,f[0].clientY-touchState.startY)>7){touchState.moved=true;E.pageWrap.classList.remove('touching-edge')}E.stage.scrollLeft-=dx;E.stage.scrollTop-=dy;touchState.lastX=f[0].clientX;touchState.lastY=f[0].clientY}
}
let scaleRenderTimer=null;function requestScaleRender(){clearTimeout(scaleRenderTimer);scaleRenderTimer=setTimeout(()=>renderPage(),70)}
function onTouchEnd(e){
  const stylusEnded=[...e.changedTouches].find(isStylusTouch);if(stylusEnded&&stylusDrawing&&String(stylusPointerId).startsWith('stylus-')){e.preventDefault();endStylus();return}
  const remaining=getFingerTouches(e);if(remaining.length>=2)return;e.preventDefault();if(touchState.mode==='pan'&&!touchState.moved&&performance.now()-touchState.startTime<360&&project){const r=E.inkCanvas.getBoundingClientRect(),x=(touchState.startX-r.left)/r.width;if(x<.12)goPage(currentPage-1);else if(x>.88)goPage(currentPage+1)}E.pageWrap.classList.remove('touching-edge');touchState.mode=null
}
E.pageWrap.addEventListener('touchstart',onTouchStart,{passive:false});E.pageWrap.addEventListener('touchmove',onTouchMove,{passive:false});E.pageWrap.addEventListener('touchend',onTouchEnd,{passive:false});E.pageWrap.addEventListener('touchcancel',onTouchEnd,{passive:false});

E.inkCanvas.addEventListener('click',e=>{if(!project||tool!=='pin')return;const pt=pagePointFromClient(e.clientX,e.clientY,1);const text=prompt('이 위치에 남길 코멘트');if(!text)return;pageData.pins.push({id:`p-${Date.now()}`,x:pt.x,y:pt.y,text,time:nowTime()});renderPins();scheduleSave()});
function renderPins(){E.pinLayer.innerHTML='';E.pinList.innerHTML='';for(const p of pageData.pins){const b=document.createElement('button');b.className='pin';b.textContent='📌';b.style.left=`${p.x*100}%`;b.style.top=`${p.y*100}%`;b.title=p.text;b.onclick=()=>toast(p.text);E.pinLayer.appendChild(b);const row=document.createElement('div');row.className='pitem';row.innerHTML=`<span><b>${p.time||''}</b> ${escapeHtml(p.text)}</span><button data-id="${p.id}">삭제</button>`;row.querySelector('button').onclick=()=>{pageData.pins=pageData.pins.filter(x=>x.id!==p.id);renderPins();scheduleSave()};E.pinList.appendChild(row)}}
function escapeHtml(s=''){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

async function goPage(p){if(!pdfDoc)return;await saveNote();await saveAnnotation();currentPage=clamp(p,1,pdfDoc.numPages);await saveProject();await renderPage();E.stage.scrollTo(0,0)}
E.prev.onclick=()=>goPage(currentPage-1);E.next.onclick=()=>goPage(currentPage+1);E.page.onchange=()=>goPage(Number(E.page.value)||currentPage);E.fit.onclick=()=>{fit=true;renderPage()};window.addEventListener('resize',()=>{if(fit&&pdfDoc)requestScaleRender()});

document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{tool=b.dataset.tool;document.querySelectorAll('[data-tool]').forEach(x=>x.classList.toggle('active',x===b));E.inputBadge.textContent=tool==='pin'?'📌 탭해서 핀 추가':tool==='erase'?'⌫ Pencil로 지우기':'✏️ Pencil · 👆 손가락 이동'});
E.thin.onclick=()=>{lineWidth=clamp(lineWidth-.5,.8,8);toast(`굵기 ${lineWidth.toFixed(1)}`)};E.thick.onclick=()=>{lineWidth=clamp(lineWidth+.5,.8,8);toast(`굵기 ${lineWidth.toFixed(1)}`)};
E.undo.onclick=()=>{const s=pageData.strokes.pop();if(s){pageData.redo.push(s);drawAllStrokes();scheduleSave()}};E.redo.onclick=()=>{const s=pageData.redo.pop();if(s){pageData.strokes.push(s);drawAllStrokes();scheduleSave()}};
E.editor.addEventListener('input',()=>{E.chars.textContent=`${E.editor.value.length}자`;scheduleSave()});E.title.addEventListener('input',scheduleSave);document.querySelectorAll('[data-tag]').forEach(b=>b.onclick=()=>insertText(b.dataset.tag));E.time.onclick=()=>insertText(`[${nowTime()}] `);
function insertText(t){const a=E.editor.selectionStart,b=E.editor.selectionEnd,v=E.editor.value;E.editor.value=v.slice(0,a)+t+v.slice(b);E.editor.focus();E.editor.selectionStart=E.editor.selectionEnd=a+t.length;E.editor.dispatchEvent(new Event('input'))}
E.layoutToggle.onclick=()=>{E.shell.classList.toggle('notes-bottom');const bottom=E.shell.classList.contains('notes-bottom');E.layoutToggle.textContent=bottom?'코멘트 →':'코멘트 ↓';setTimeout(()=>pdfDoc&&renderPage(),80)};

function setupMic(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){E.mic.disabled=true;E.mic.title='이 브라우저는 음성입력을 지원하지 않습니다';return}recognition=new SR();recognition.lang='ko-KR';recognition.continuous=true;recognition.interimResults=false;recognition.onresult=e=>{let t='';for(let i=e.resultIndex;i<e.results.length;i++)if(e.results[i].isFinal)t+=e.results[i][0].transcript+' ';if(t)insertText(t)};recognition.onend=()=>{listening=false;E.mic.textContent='🎤'};E.mic.onclick=()=>{if(listening){recognition.stop();return}try{recognition.start();listening=true;E.mic.textContent='⏹'}catch{}}}

async function composePageImage(pageNo,renderScale=1.7){const page=await pdfDoc.getPage(pageNo),vp=page.getViewport({scale:renderScale});const c=document.createElement('canvas');c.width=Math.ceil(vp.width);c.height=Math.ceil(vp.height);const ctx=c.getContext('2d');await page.render({canvasContext:ctx,viewport:vp}).promise;const a=await get(AS,`${project.id}:${pageNo}`);for(const s of a?.strokes||[]){const fake={...s,points:s.points.map(p=>({x:p.x*c.width,y:p.y*c.height,p:p.p}))};drawStrokeToContext(ctx,fake,renderScale)}return c}
function drawStrokeToContext(ctx,stroke,renderScale=1){const pts=stroke.points||[];if(!pts.length)return;ctx.save();ctx.lineCap='round';ctx.lineJoin='round';ctx.globalCompositeOperation=stroke.tool==='highlight'?'multiply':'source-over';ctx.strokeStyle=stroke.color||'#e11d48';ctx.globalAlpha=stroke.tool==='highlight'?.28:1;const base=(stroke.width||2.2)*renderScale;if(pts.length===1){ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,base/2,0,Math.PI*2);ctx.fill();ctx.restore();return}for(let i=0;i<pts.length-1;i++){const a=pts[Math.max(0,i-1)],b=pts[i],c=pts[i+1],st={x:(a.x+b.x)/2,y:(a.y+b.y)/2},en={x:(b.x+c.x)/2,y:(b.y+c.y)/2};ctx.beginPath();ctx.moveTo(st.x,st.y);ctx.quadraticCurveTo(b.x,b.y,en.x,en.y);ctx.lineWidth=stroke.tool==='highlight'?base*3.2:base*(.45+.9*((b.p+c.p)/2||.5));ctx.stroke()}ctx.restore()}
function dataUrlToUint8(dataUrl){const b=atob(dataUrl.split(',')[1]),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u}
function downloadBlob(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1500)}

E.md.onclick=async()=>{if(!project)return;await saveNote();const notes=await getByProject(NS,project.id);let out=`# ${E.title.value||project.title}\n\n`;for(let p=1;p<=pdfDoc.numPages;p++){const n=notes.find(x=>x.page===p);out+=`<<<PAGE ${p}>>>\n${n?.text||''}\n\n`}downloadBlob(new Blob([out],{type:'text/markdown;charset=utf-8'}),`${safe(E.title.value)}_notes.md`)};
E.json.onclick=async()=>{if(!project)return;await Promise.all([saveProject(),saveNote(),saveAnnotation()]);const notes=await getByProject(NS,project.id),annotations=await getByProject(AS,project.id);const payload={version:4,exportedAt:new Date().toISOString(),project:{...project,pdfBlob:undefined},notes,annotations};downloadBlob(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),`${safe(E.title.value)}_backup.json`)};
E.backupInput.onchange=async e=>{const f=e.target.files?.[0];if(!f)return;try{const j=JSON.parse(await f.text());if(!j.project?.id)throw new Error('bad');const id=j.project.id;project={...j.project,id,pdfBlob:null};await put(PS,project);for(const n of j.notes||[])await put(NS,n);for(const a of j.annotations||[])await put(AS,a);localStorage.setItem(LAST,id);toast('백업을 복원했습니다. 원본 PDF를 다시 열어주세요.')}catch{toast('백업 파일을 읽지 못했습니다')}};
E.docx.onclick=async()=>{if(!project||!pdfDoc)return;toast('Word 생성 중…');await saveNote();const notes=await getByProject(NS,project.id);const children=[new Paragraph({text:E.title.value||project.title,heading:HeadingLevel.TITLE,alignment:AlignmentType.CENTER})];for(let p=1;p<=pdfDoc.numPages;p++){children.push(new Paragraph({text:`${p}p.`,heading:HeadingLevel.HEADING_1}));const c=await composePageImage(p,1.35),png=dataUrlToUint8(c.toDataURL('image/png'));children.push(new Paragraph({children:[new ImageRun({data:png,transformation:{width:520,height:Math.round(520*c.height/c.width)}})]}));const n=notes.find(x=>x.page===p);if(n?.text)children.push(new Paragraph({children:[new TextRun({text:n.text})]}));if(p<pdfDoc.numPages)children.push(new Paragraph({children:[new PageBreak()]}))}const doc=new Document({sections:[{children}]});downloadBlob(await Packer.toBlob(doc),`${safe(E.title.value)}_lecture_notes.docx`);toast('Word 완료')};
E.printBtn.onclick=async()=>{if(!project||!pdfDoc)return;toast('PDF 출력 준비 중…');await saveNote();const notes=await getByProject(NS,project.id);E.printArea.innerHTML='';for(let p=1;p<=pdfDoc.numPages;p++){const c=await composePageImage(p,1.35),div=document.createElement('div');div.className='pp';const n=notes.find(x=>x.page===p);div.innerHTML=`<h2>${p}p.</h2><img src="${c.toDataURL('image/jpeg',.9)}"><div class="pnote">${escapeHtml(n?.text||'')}</div>`;E.printArea.appendChild(div)}setTimeout(()=>window.print(),150)};

E.pdfInput.onchange=e=>{const f=e.target.files?.[0];if(f)loadPdfFile(f)};E.emptyPdf.onchange=e=>{const f=e.target.files?.[0];if(f)loadPdfFile(f)};

// Mouse/trackpad fallback: clicking page edges changes pages; drawing remains Pencil-only by design.
E.pageWrap.addEventListener('mouseup',e=>{if(e.button!==0||tool==='pin'||!project)return;const r=E.inkCanvas.getBoundingClientRect(),x=(e.clientX-r.left)/r.width;if(x<.08)goPage(currentPage-1);else if(x>.92)goPage(currentPage+1)});

db=await openDb();setupMic();await restoreLast();
