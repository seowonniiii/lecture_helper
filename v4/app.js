import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';
import { marked } from 'https://cdn.jsdelivr.net/npm/marked@18.0.14/lib/marked.esm.js';
import TurndownService from 'https://cdn.jsdelivr.net/npm/turndown@7.2.4/+esm';
import { gfm } from 'https://cdn.jsdelivr.net/npm/@truto/turndown-plugin-gfm@1.0.3/+esm';
import { PDFDocument, rgb } from 'https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/+esm';
import {Document,Packer,Paragraph,TextRun,HeadingLevel,ImageRun,PageBreak,AlignmentType,Table,TableRow,TableCell,WidthType,PageOrientation} from 'https://cdn.jsdelivr.net/npm/docx@9.8.1/+esm';
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.worker.min.mjs';

const $=id=>document.getElementById(id);
const E={shell:$('shell'),pdfInput:$('pdfInput'),emptyPdf:$('emptyPdf'),backupInput:$('backupInput'),status:$('status'),title:$('title'),filename:$('filename'),stage:$('stage'),stageInner:$('stageInner'),empty:$('empty'),pageWrap:$('pageWrap'),pdfCanvas:$('pdfCanvas'),inkCanvas:$('inkCanvas'),pinLayer:$('pinLayer'),page:$('page'),total:$('total'),pLabel:$('pLabel'),prev:$('prev'),next:$('next'),fit:$('fit'),inkColor:$('inkColor'),thin:$('thin'),thick:$('thick'),undo:$('undo'),redo:$('redo'),editor:$('editor'),chars:$('chars'),time:$('time'),mic:$('mic'),transcript:$('transcript'),transcriptChars:$('transcriptChars'),pinList:$('pinList'),docx:$('docx'),printBtn:$('printBtn'),md:$('md'),json:$('json'),toast:$('toast'),printArea:$('printArea'),layoutToggle:$('layoutToggle'),inputBadge:$('inputBadge'),viewCount:$('viewCount'),mdInput:$('mdInput'),mdFilename:$('mdFilename'),mdRendered:$('mdRendered'),mdModeRendered:$('mdModeRendered'),mdModeRaw:$('mdModeRaw'),mdBold:$('mdBold'),mdExam:$('mdExam'),mdHighlight:$('mdHighlight'),transcriptToggle:$('transcriptToggle'),transcriptPane:$('transcriptPane'),noteSplit:$('noteSplit'),annotatedPdf:$('annotatedPdf'),pinPopover:$('pinPopover'),pinText:$('pinText'),pinSave:$('pinSave'),pinCancel:$('pinCancel')};

const mdTurndown=new TurndownService({headingStyle:'atx',bulletListMarker:'-',codeBlockStyle:'fenced',emDelimiter:'*',strongDelimiter:'**'});
mdTurndown.use(gfm);
mdTurndown.keep(['exam','mark','span']);
let mdViewMode=localStorage.getItem('lh-v4-md-view-mode')||'rendered',syncingRenderedEdit=false,renderedEditTimer=null;
function sanitizeRenderedHtml(html){
  const t=document.createElement('template');t.innerHTML=String(html||'');
  t.content.querySelectorAll('script,iframe,object,embed,link,meta,style').forEach(x=>x.remove());
  t.content.querySelectorAll('*').forEach(el=>{
    for(const a of [...el.attributes]){
      const n=a.name.toLowerCase(),v=String(a.value||'').trim().toLowerCase();
      if(n.startsWith('on')||((n==='href'||n==='src')&&v.startsWith('javascript:')))el.removeAttribute(a.name);
    }
  });
  return t.innerHTML;
}
function markdownToSafeHtml(md){return sanitizeRenderedHtml(marked.parse(String(md||''),{gfm:true,breaks:true}));}
function syncMdRendered(){if(!E.mdRendered)return;E.mdRendered.innerHTML=markdownToSafeHtml(E.transcript.value);}
function setMdViewMode(mode){
  mdViewMode=mode==='raw'?'raw':'rendered';localStorage.setItem('lh-v4-md-view-mode',mdViewMode);
  const rendered=mdViewMode==='rendered';
  E.mdRendered?.classList.toggle('hidden',!rendered);E.transcript?.classList.toggle('hidden',rendered);
  E.mdModeRendered?.classList.toggle('active',rendered);E.mdModeRaw?.classList.toggle('active',!rendered);
  if(rendered)syncMdRendered();
}
function renderedHtmlToMarkdown(){return mdTurndown.turndown(E.mdRendered.innerHTML).replace(/\n{3,}/g,'\n\n').trim();}

let db,pdfDoc=null,project=null,currentPage=1,scale=1.15,fit=true,renderTask=null,tool='pen',pageData={strokes:[],redo:[],pins:[]},saveTimer=null,recognition=null,listening=false,lineWidth=2.2,highlightWidth=Math.max(6,Math.min(40,Number(localStorage.getItem('lh-v4-highlight-width'))||18)),viewCount=Math.max(1,Math.min(4,Number(localStorage.getItem('lh-v4-view-count'))||1)),pendingPin=null;
let stylusPointerId=null,stylusDrawing=false,currentStroke=null,lastStylusPoint=null;
let touchState={mode:null,startTime:0,startX:0,startY:0,lastX:0,lastY:0,moved:false,initialDistance:0,initialScale:1,midX:0,midY:0};
let penPointerSeenUntil=0,renderGeneration=0;
let lastHighlighterEndAt=0;
const DB='lecture-helper-v4',PS='projects',NS='notes',AS='annotations',TS='transcripts',LAST='lh-v4-last';

function toast(t){E.toast.textContent=t;E.toast.classList.add('show');setTimeout(()=>E.toast.classList.remove('show'),1500)}
function nowTime(){return new Intl.DateTimeFormat('ko-KR',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date())}
function safe(n){return(n||'lecture').replace(/[\\/:*?"<>|]/g,'_').trim()||'lecture'}
function req(r){return new Promise((res,rej)=>{r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}
function done(tx){return new Promise((res,rej)=>{tx.oncomplete=res;tx.onerror=()=>rej(tx.error);tx.onabort=()=>rej(tx.error)})}
function clamp(n,a,b){return Math.max(a,Math.min(b,n))}
function pointerPressure(e){const p=Number(e.pressure);return p>0?clamp(p,.08,1):.5}
function touchPressure(t){const p=Number(t.force);return p>0?clamp(p,.08,1):.5}
function isStylusTouch(t){return !!t && (t.touchType==='stylus'||t.touchType==='pencil')}

async function openDb(){return new Promise((res,rej)=>{const r=indexedDB.open(DB,2);r.onupgradeneeded=()=>{const d=r.result;if(!d.objectStoreNames.contains(PS))d.createObjectStore(PS,{keyPath:'id'});if(!d.objectStoreNames.contains(NS)){const s=d.createObjectStore(NS,{keyPath:'key'});s.createIndex('projectId','projectId')}if(!d.objectStoreNames.contains(AS)){const s=d.createObjectStore(AS,{keyPath:'key'});s.createIndex('projectId','projectId')}if(!d.objectStoreNames.contains(TS)){const s=d.createObjectStore(TS,{keyPath:'key'});s.createIndex('projectId','projectId')}};r.onsuccess=()=>res(r.result);r.onerror=()=>rej(r.error)})}
async function put(store,obj){const tx=db.transaction(store,'readwrite');tx.objectStore(store).put(obj);await done(tx)}
async function get(store,key){const tx=db.transaction(store);const x=await req(tx.objectStore(store).get(key));await done(tx);return x}
async function getByProject(store,id){const tx=db.transaction(store);const x=await req(tx.objectStore(store).index('projectId').getAll(IDBKeyRange.only(id)));await done(tx);return x.sort((a,b)=>a.page-b.page)}
function noteKey(p){return `${project.id}:${p}`}
async function saveProject(){if(!project)return;project.title=E.title.value||project.title;project.page=currentPage;project.updated=Date.now();await put(PS,project);localStorage.setItem(LAST,project.id)}
async function saveNote(){if(!project)return;await put(NS,{key:noteKey(currentPage),projectId:project.id,page:currentPage,text:E.editor.value,updated:Date.now()});E.chars.textContent=`${E.editor.value.length}자`}
async function saveTranscript(){if(!project)return;await put(TS,{key:noteKey(currentPage),projectId:project.id,page:currentPage,text:E.transcript.value,updated:Date.now()});E.transcriptChars.textContent=`${E.transcript.value.length}자`}
async function saveAnnotation(){if(!project)return;await put(AS,{key:noteKey(currentPage),projectId:project.id,page:currentPage,strokes:pageData.strokes,pins:pageData.pins,updated:Date.now()})}
function scheduleSave(){clearTimeout(saveTimer);saveTimer=setTimeout(async()=>{await Promise.all([saveProject(),saveNote(),saveTranscript(),saveAnnotation()]);E.status.textContent=`저장됨 · ${nowTime()}`},250)}

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

function fitScale(viewport){const cols=viewCount===1?1:2,rows=viewCount<=2?1:2,gap=viewCount===1?0:12;const w=Math.max(180,(E.stage.clientWidth-36-gap*(cols-1))/cols),h=Math.max(180,(E.stage.clientHeight-36-gap*(rows-1))/rows);return Math.min(w/viewport.width,h/viewport.height,2.2)}
async function renderPage(){
  if(!pdfDoc)return;const gen=++renderGeneration;currentPage=clamp(currentPage,1,pdfDoc.numPages);E.page.value=currentPage;E.pLabel.textContent=currentPage;E.total.textContent=pdfDoc.numPages;
  const page=await pdfDoc.getPage(currentPage);const base=page.getViewport({scale:1});if(fit)scale=fitScale(base);const vp=page.getViewport({scale});
  const dpr=Math.min(window.devicePixelRatio||1,2.5);const pc=E.pdfCanvas,ic=E.inkCanvas;pc.width=Math.round(vp.width*dpr);pc.height=Math.round(vp.height*dpr);pc.style.width=`${vp.width}px`;pc.style.height=`${vp.height}px`;ic.width=Math.round(vp.width*dpr);ic.height=Math.round(vp.height*dpr);ic.style.width=`${vp.width}px`;ic.style.height=`${vp.height}px`;E.pageWrap.style.width=`${vp.width}px`;E.pageWrap.style.height=`${vp.height}px`;
  const ctx=pc.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);if(renderTask)try{renderTask.cancel()}catch{}renderTask=page.render({canvasContext:ctx,viewport:vp});try{await renderTask.promise}catch(e){if(e?.name!=='RenderingCancelledException')throw e}if(gen!==renderGeneration)return;
  const [n,a,t]=await Promise.all([get(NS,noteKey(currentPage)),get(AS,noteKey(currentPage)),get(TS,noteKey(currentPage))]);E.editor.value=n?.text||'';E.chars.textContent=`${E.editor.value.length}자`;E.transcript.value=t?.text||'';E.transcriptChars.textContent=`${E.transcript.value.length}자`;syncMdRendered();pageData={strokes:a?.strokes||[],redo:[],pins:a?.pins||[]};drawAllStrokes();renderPins();await renderMultiPreviews();E.status.textContent=`${currentPage}/${pdfDoc.numPages} · ${Math.round(scale*100)}%`;
}
async function renderMultiPreviews(){E.stageInner.querySelectorAll('.previewCard').forEach(x=>x.remove());E.stageInner.classList.toggle('multi',viewCount>1);E.stageInner.style.setProperty('--grid-cols',viewCount===1?'1':'2');if(viewCount<=1||!pdfDoc)return;for(let i=1;i<viewCount;i++){const p=currentPage+i;if(p>pdfDoc.numPages)break;const b=document.createElement('button');b.className='previewCard';b.type='button';const l=document.createElement('span');l.className='previewPageNo';l.textContent=`${p}p.`;b.appendChild(l);const c=await composePageImage(p,.9),im=document.createElement('img');im.src=c.toDataURL('image/jpeg',.82);b.appendChild(im);b.onclick=()=>goPage(p);E.stageInner.appendChild(b)}}
function pagePointFromClient(clientX,clientY,pressure=.5){const r=E.inkCanvas.getBoundingClientRect();return{x:clamp((clientX-r.left)/r.width,0,1),y:clamp((clientY-r.top)/r.height,0,1),p:pressure}}
function canvasPoint(pt){const r=E.inkCanvas.getBoundingClientRect();return{x:pt.x*r.width,y:pt.y*r.height,p:pt.p??.5}}
function strokeWidth(stroke,p){const base=(stroke.width||2.2)*scale;const pressure=stroke.tool==='highlight'?1:(.45+.9*clamp(p??.5,.05,1));return base*pressure}
function setupInkCtx(){const ctx=E.inkCanvas.getContext('2d');const dpr=Math.min(window.devicePixelRatio||1,2.5);ctx.setTransform(dpr,0,0,dpr,0,0);ctx.lineCap='round';ctx.lineJoin='round';return ctx}
function clearInk(){const ctx=E.inkCanvas.getContext('2d');ctx.save();ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,E.inkCanvas.width,E.inkCanvas.height);ctx.restore()}
function drawStroke(stroke){
  if(!stroke?.points?.length)return;
  const ctx=setupInkCtx();
  const pts=stroke.points.map(canvasPoint);
  ctx.save();
  ctx.lineCap='round';ctx.lineJoin='round';

  // Keep V2 highlighter behavior exactly: fixed width, source-over, 25% alpha,
  // simple polyline. Pencil pressure/smoothing is intentionally NOT applied.
  if(stroke.tool==='highlight'){
    ctx.globalCompositeOperation='source-over';
    ctx.strokeStyle=stroke.color||'#facc15';
    ctx.globalAlpha=.25;
    ctx.lineWidth=stroke.width||18;
    if(pts.length===1){
      ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,(stroke.width||18)/2,0,Math.PI*2);ctx.fill();ctx.restore();return;
    }
    ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
    for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x,pts[i].y);
    ctx.stroke();ctx.restore();return;
  }

  ctx.globalCompositeOperation='source-over';
  ctx.strokeStyle=stroke.color||'#e11d48';
  ctx.globalAlpha=1;
  if(pts.length===1){ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,strokeWidth(stroke,pts[0].p)/2,0,Math.PI*2);ctx.fill();ctx.restore();return}
  for(let i=0;i<pts.length-1;i++){
    const a=pts[Math.max(0,i-1)],b=pts[i],c=pts[i+1];
    const start={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
    const end={x:(b.x+c.x)/2,y:(b.y+c.y)/2};
    ctx.beginPath();ctx.moveTo(start.x,start.y);ctx.quadraticCurveTo(b.x,b.y,end.x,end.y);
    ctx.lineWidth=strokeWidth(stroke,(b.p+c.p)/2);ctx.stroke();
  }
  ctx.restore()
}
function drawAllStrokes(){clearInk();for(const s of pageData.strokes)drawStroke(s)}
function drawLiveSegment(stroke){drawAllStrokes();drawStroke(stroke)}
function pointDistanceToStroke(pt,stroke){let min=Infinity;for(const q of stroke.points||[]){const dx=pt.x-q.x,dy=pt.y-q.y;min=Math.min(min,dx*dx+dy*dy)}return Math.sqrt(min)}
function eraseAt(pt){const radius=Math.max(.012,(lineWidth*3)/(Math.max(E.inkCanvas.clientWidth,1)));const before=pageData.strokes.length;pageData.strokes=pageData.strokes.filter(s=>pointDistanceToStroke(pt,s)>radius);if(pageData.strokes.length!==before){pageData.redo=[];drawAllStrokes();scheduleSave()}}

function beginStylus(clientX,clientY,pressure,id='touch-stylus'){
  if(!project||tool==='pin')return;if(tool==='erase'){stylusDrawing=true;stylusPointerId=id;eraseAt(pagePointFromClient(clientX,clientY,pressure));return}
  stylusDrawing=true;stylusPointerId=id;currentStroke={id:`s-${Date.now()}-${Math.random().toString(36).slice(2)}`,tool,color:E.inkColor.value,width:tool==='highlight'?highlightWidth:lineWidth,points:[pagePointFromClient(clientX,clientY,pressure)]};lastStylusPoint=currentStroke.points[0];
}
function continueStylus(clientX,clientY,pressure){if(!stylusDrawing)return;const pt=pagePointFromClient(clientX,clientY,pressure);if(tool==='erase'){eraseAt(pt);return}if(!currentStroke)return;const dx=pt.x-(lastStylusPoint?.x??pt.x),dy=pt.y-(lastStylusPoint?.y??pt.y);if(dx*dx+dy*dy<0.0000004)return;currentStroke.points.push(pt);lastStylusPoint=pt;drawLiveSegment(currentStroke)}
function endStylus(){
  if(!stylusDrawing)return;
  stylusDrawing=false;stylusPointerId=null;
  if(currentStroke?.points?.length){
    if(currentStroke.tool==='highlight'){
      const prev=pageData.strokes[pageData.strokes.length-1];
      const a=prev?.points?.[prev.points.length-1],b=currentStroke.points[0];
      const close=!!a&&!!b&&Math.hypot(a.x-b.x,a.y-b.y)<.015;
      const soon=performance.now()-lastHighlighterEndAt<180;
      if(prev?.tool==='highlight'&&prev.color===currentStroke.color&&close&&soon){
        prev.points.push(...currentStroke.points);
      }else{
        pageData.strokes.push(currentStroke);
      }
      lastHighlighterEndAt=performance.now();
    }else{
      pageData.strokes.push(currentStroke);
    }
    pageData.redo=[];currentStroke=null;lastStylusPoint=null;drawAllStrokes();scheduleSave();
  }else currentStroke=null;
}

function showPinPopover(clientX,clientY){if(!project||tool!=='pin')return;pendingPin=pagePointFromClient(clientX,clientY,1);E.pinText.value='';E.pinPopover.classList.remove('hidden');const w=280,h=150,p=10;E.pinPopover.style.left=`${Math.max(p,Math.min(innerWidth-w-p,clientX+12))}px`;E.pinPopover.style.top=`${Math.max(p,Math.min(innerHeight-h-p,clientY+12))}px`;setTimeout(()=>E.pinText.focus(),20)}
function hidePinPopover(){pendingPin=null;E.pinPopover.classList.add('hidden');E.pinText.value=''}
async function commitPin(){const text=E.pinText.value.trim();if(!pendingPin||!text)return hidePinPopover();pageData.pins.push({id:`p-${Date.now()}`,x:pendingPin.x,y:pendingPin.y,text,time:nowTime()});hidePinPopover();renderPins();await saveAnnotation()}
E.pinSave.onclick=commitPin;E.pinCancel.onclick=hidePinPopover;E.pinPopover.addEventListener('pointerdown',e=>e.stopPropagation());


function handlePenPointerDown(e){
  if(e.pointerType!=='pen'||!project)return;
  penPointerSeenUntil=performance.now()+1200;e.preventDefault();e.stopPropagation();
  if(tool==='pin'){showPinPopover(e.clientX,e.clientY);return;}
  try{E.inkCanvas.setPointerCapture(e.pointerId)}catch{}
  beginStylus(e.clientX,e.clientY,pointerPressure(e),e.pointerId);
}
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
  const remaining=getFingerTouches(e);if(remaining.length>=2)return;
  e.preventDefault();
  if(touchState.mode==='pan'&&!touchState.moved&&performance.now()-touchState.startTime<360&&project){
    if(tool==='pin') showPinPopover(touchState.startX,touchState.startY);
    else{
      const r=E.inkCanvas.getBoundingClientRect(),x=(touchState.startX-r.left)/r.width;
      if(x<.12)goPage(currentPage-1);else if(x>.88)goPage(currentPage+1);
    }
  }
  E.pageWrap.classList.remove('touching-edge');touchState.mode=null;
}
E.pageWrap.addEventListener('touchstart',onTouchStart,{passive:false});E.pageWrap.addEventListener('touchmove',onTouchMove,{passive:false});E.pageWrap.addEventListener('touchend',onTouchEnd,{passive:false});E.pageWrap.addEventListener('touchcancel',onTouchEnd,{passive:false});

E.inkCanvas.addEventListener('click',e=>{if(!project||tool!=='pin')return;showPinPopover(e.clientX,e.clientY)});
function renderPins(){E.pinLayer.innerHTML='';E.pinList.innerHTML='';for(const p of pageData.pins){const b=document.createElement('button');b.className='pin';b.textContent='📌';b.style.left=`${p.x*100}%`;b.style.top=`${p.y*100}%`;b.title=p.text;b.onpointerdown=e=>e.stopPropagation();b.onclick=e=>{e.stopPropagation();toast(p.text)};E.pinLayer.appendChild(b);const row=document.createElement('div');row.className='pitem';row.innerHTML=`<span><b>${p.time||''}</b> ${escapeHtml(p.text)}</span><button data-id="${p.id}">삭제</button>`;row.querySelector('button').onclick=()=>{pageData.pins=pageData.pins.filter(x=>x.id!==p.id);renderPins();scheduleSave()};E.pinList.appendChild(row)}}
function escapeHtml(s=''){return s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}

async function goPage(p){if(!pdfDoc)return;await Promise.all([saveNote(),saveTranscript(),saveAnnotation()]);currentPage=clamp(p,1,pdfDoc.numPages);await saveProject();await renderPage();E.stage.scrollTo(0,0)}
E.prev.onclick=()=>goPage(currentPage-1);E.next.onclick=()=>goPage(currentPage+1);E.page.onchange=()=>goPage(Number(E.page.value)||currentPage);E.fit.onclick=()=>{fit=true;renderPage()};window.addEventListener('resize',()=>{if(fit&&pdfDoc)requestScaleRender()});

document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{tool=b.dataset.tool;document.querySelectorAll('[data-tool]').forEach(x=>x.classList.toggle('active',x===b));E.inputBadge.textContent=tool==='pin'?'📌 탭해서 핀 추가':tool==='erase'?'⌫ Pencil로 지우기':'✏️ Pencil · 👆 손가락 이동'});
E.thin.onclick=()=>{if(tool==='highlight'){highlightWidth=clamp(highlightWidth-2,6,40);localStorage.setItem('lh-v4-highlight-width',String(highlightWidth));toast(`형광펜 굵기 ${highlightWidth}`)}else{lineWidth=clamp(lineWidth-.5,.8,8);toast(`펜 굵기 ${lineWidth.toFixed(1)}`)}};E.thick.onclick=()=>{if(tool==='highlight'){highlightWidth=clamp(highlightWidth+2,6,40);localStorage.setItem('lh-v4-highlight-width',String(highlightWidth));toast(`형광펜 굵기 ${highlightWidth}`)}else{lineWidth=clamp(lineWidth+.5,.8,8);toast(`펜 굵기 ${lineWidth.toFixed(1)}`)}};
E.undo.onclick=()=>{const s=pageData.strokes.pop();if(s){pageData.redo.push(s);drawAllStrokes();scheduleSave()}};E.redo.onclick=()=>{const s=pageData.redo.pop();if(s){pageData.strokes.push(s);drawAllStrokes();scheduleSave()}};
E.editor.addEventListener('input',()=>{E.chars.textContent=`${E.editor.value.length}자`;scheduleSave()});E.transcript.addEventListener('input',()=>{E.transcriptChars.textContent=`${E.transcript.value.length}자`;if(!syncingRenderedEdit&&mdViewMode==='rendered')syncMdRendered();scheduleSave()});E.title.addEventListener('input',scheduleSave);document.querySelectorAll('[data-tag]').forEach(b=>b.onclick=()=>insertText(b.dataset.tag));E.time.onclick=()=>insertText(`[${nowTime()}] `);E.viewCount.value=String(viewCount);E.viewCount.onchange=()=>{viewCount=Math.max(1,Math.min(4,Number(E.viewCount.value)||1));localStorage.setItem('lh-v4-view-count',String(viewCount));fit=true;if(pdfDoc)renderPage()};
function insertText(t){const a=E.editor.selectionStart,b=E.editor.selectionEnd,v=E.editor.value;E.editor.value=v.slice(0,a)+t+v.slice(b);E.editor.focus();E.editor.selectionStart=E.editor.selectionEnd=a+t.length;E.editor.dispatchEvent(new Event('input'))}
E.layoutToggle.onclick=()=>{E.shell.classList.toggle('notes-bottom');const bottom=E.shell.classList.contains('notes-bottom');E.layoutToggle.textContent=bottom?'코멘트 →':'코멘트 ↓';setTimeout(()=>pdfDoc&&renderPage(),80)};

function cleanImportedMdBody(body,pageNo){
  let lines=String(body||'').replaceAll('\r','').split('\n');
  while(lines.length&&!lines[0].trim())lines.shift();
  while(lines.length&&!lines[lines.length-1].trim())lines.pop();
  if(lines.length){
    const compact=lines[0].trim().replaceAll(' ','').toLowerCase();
    if(compact===`${pageNo}p.`)lines.shift();
  }
  let s=lines.join('\n').trim();
  const labels=['### .md / 전사문','### 실시간 전사','### 전사문'];
  for(const label of labels){
    const at=s.indexOf(label);
    if(at>=0){
      const from=at+label.length;
      const rest=s.slice(from).replace(/^\s*\n?/,'');
      const next=rest.indexOf('\n### ');
      return (next>=0?rest.slice(0,next):rest).trim();
    }
  }
  return s;
}
function pageMarkerNumber(line){
  const t=String(line||'').trim();
  if(!t.startsWith('<<<PAGE ')||!t.endsWith('>>>'))return null;
  const n=Number(t.slice(8,-3).trim());
  return Number.isInteger(n)?n:null;
}
function headingPageNumber(line){
  let t=String(line||'').trim();
  while(t.startsWith('#'))t=t.slice(1).trimStart();
  t=t.replaceAll(' ','').toLowerCase();
  if(!t.endsWith('p.'))return null;
  const n=Number(t.slice(0,-2));
  return Number.isInteger(n)?n:null;
}
function parseMarkdownPages(text){
  const lines=String(text||'').replaceAll('\r','').split('\n');
  const out=[];
  let page=null,buf=[];
  const flush=()=>{
    if(page!==null)out.push({page,text:cleanImportedMdBody(buf.join('\n'),page)});
    buf=[];
  };
  for(const line of lines){
    const n=pageMarkerNumber(line);
    if(n!==null){flush();page=n;continue}
    if(page!==null)buf.push(line);
  }
  flush();
  if(out.length)return out;

  page=null;buf=[];
  for(const line of lines){
    const n=headingPageNumber(line);
    if(n!==null){flush();page=n;continue}
    if(page!==null)buf.push(line);
  }
  flush();
  if(out.length)return out;
  return [{page:currentPage,text:String(text||'').trim()}];
}
async function importMarkdownFile(file){
  if(!project||!pdfDoc){toast('먼저 PDF를 열어주세요');return}
  await saveTranscript();
  const text=await file.text();
  const sections=parseMarkdownPages(text);
  let count=0,ignored=0;
  for(const section of sections){
    const page=Number(section.page);
    if(!Number.isInteger(page)||page<1||page>pdfDoc.numPages){ignored++;continue}
    await put(TS,{key:`${project.id}:${page}`,projectId:project.id,page,text:section.text||'',source:'md',sourceName:file.name,updated:Date.now()});
    count++;
  }
  E.mdFilename.textContent=`${file.name} · ${count}페이지 연결됨`;
  await renderPage();
  toast(`MD 전사문 ${count}페이지 불러옴 · 수업 필기 유지${ignored?` · ${ignored}페이지 제외`:''}`);
}
E.mdInput.onchange=async e=>{const f=e.target.files?.[0];if(!f)return;try{await importMarkdownFile(f)}catch(err){console.error(err);toast('MD 파일을 읽지 못했습니다')}finally{e.target.value=''}};

let savedMdRange=null;
function rangeIsInsideMd(r){
  if(!r)return false;
  const a=r.commonAncestorContainer;
  const el=a.nodeType===1?a:a.parentElement;
  return !!el&&(el===E.mdRendered||E.mdRendered.contains(el));
}
function captureMdSelection(){
  const sel=window.getSelection();
  if(!sel||!sel.rangeCount||sel.isCollapsed)return savedMdRange;
  const r=sel.getRangeAt(0);
  if(rangeIsInsideMd(r))savedMdRange=r.cloneRange();
  return savedMdRange;
}
function usableMdRange(){
  const sel=window.getSelection();
  if(sel&&sel.rangeCount&&!sel.isCollapsed){
    const live=sel.getRangeAt(0);
    if(rangeIsInsideMd(live)){savedMdRange=live.cloneRange();return live.cloneRange()}
  }
  return savedMdRange? savedMdRange.cloneRange():null;
}
function selectedTextNodes(r){
  const walker=document.createTreeWalker(E.mdRendered,NodeFilter.SHOW_TEXT,{acceptNode(node){
    if(!node.data||!node.data.length)return NodeFilter.FILTER_REJECT;
    try{return r.intersectsNode(node)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_REJECT}catch{return NodeFilter.FILTER_REJECT}
  }});
  const nodes=[];let n;
  while((n=walker.nextNode()))nodes.push(n);
  return nodes;
}
function wrapSelectedText(r,tag){
  const nodes=selectedTextNodes(r);
  if(!nodes.length)return [];
  const wrappers=[];
  for(let i=nodes.length-1;i>=0;i--){
    const node=nodes[i];
    let from=0,to=node.data.length;
    if(node===r.startContainer)from=r.startOffset;
    if(node===r.endContainer)to=r.endOffset;
    from=Math.max(0,Math.min(from,node.data.length));
    to=Math.max(from,Math.min(to,node.data.length));
    if(from===to)continue;
    const rr=document.createRange();rr.setStart(node,from);rr.setEnd(node,to);
    const wrapper=document.createElement(tag);
    try{rr.surroundContents(wrapper);wrappers.push(wrapper)}catch(err){
      console.warn('format segment failed',err);
    }
  }
  return wrappers.reverse();
}
function syncRenderedMarkdownImmediately(){
  syncingRenderedEdit=true;
  E.transcript.value=renderedHtmlToMarkdown();
  E.transcriptChars.textContent=`${E.transcript.value.length}자`;
  scheduleSave();
  syncingRenderedEdit=false;
}
function applyMdInlineFormat(kind){
  if(mdViewMode!=='rendered'){
    setMdViewMode('rendered');
    toast('결과 편집에서 글자를 먼저 선택해주세요');
    return;
  }
  const r=usableMdRange();
  if(!r||r.collapsed||!rangeIsInsideMd(r)){
    toast('먼저 적용할 글자를 드래그해서 선택해주세요');
    return;
  }
  const tag=kind==='bold'?'strong':kind==='exam'?'exam':'mark';
  const wrappers=wrapSelectedText(r,tag);
  if(!wrappers.length){toast('선택 영역에 적용하지 못했습니다');return}
  syncRenderedMarkdownImmediately();
  try{
    const nr=document.createRange();
    nr.setStartBefore(wrappers[0]);nr.setEndAfter(wrappers[wrappers.length-1]);
    savedMdRange=nr.cloneRange();
    const sel=window.getSelection();sel.removeAllRanges();sel.addRange(nr);
  }catch{savedMdRange=null}
}
document.addEventListener('selectionchange',()=>captureMdSelection());
function bindMdFormatButton(button,kind){
  const run=e=>{
    e.preventDefault();e.stopPropagation();
    captureMdSelection();
    applyMdInlineFormat(kind);
  };
  if(window.PointerEvent){
    button.addEventListener('pointerdown',run,{passive:false});
  }else{
    button.addEventListener('touchstart',run,{passive:false});
    button.addEventListener('mousedown',run);
  }
  button.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();applyMdInlineFormat(kind)}});
}
bindMdFormatButton(E.mdBold,'bold');
bindMdFormatButton(E.mdExam,'exam');
bindMdFormatButton(E.mdHighlight,'highlight');

let transcriptVisible=false;
function setTranscriptVisible(show){
  transcriptVisible=!!show;
  E.transcriptPane?.classList.toggle('hidden',!transcriptVisible);
  E.noteSplit?.classList.toggle('transcript-off',!transcriptVisible);
  if(E.transcriptToggle)E.transcriptToggle.textContent=transcriptVisible?'전사문 닫기':'전사문 보기';
}
E.transcriptToggle.onclick=()=>setTranscriptVisible(!transcriptVisible);

E.mdModeRendered.onclick=()=>setMdViewMode('rendered');
E.mdModeRaw.onclick=()=>setMdViewMode('raw');
E.mdRendered.addEventListener('input',()=>{
  clearTimeout(renderedEditTimer);
  renderedEditTimer=setTimeout(()=>{
    syncingRenderedEdit=true;
    E.transcript.value=renderedHtmlToMarkdown();
    E.transcriptChars.textContent=`${E.transcript.value.length}자`;
    scheduleSave();
    syncingRenderedEdit=false;
  },120);
});
E.mdRendered.addEventListener('paste',e=>{
  e.preventDefault();
  const text=e.clipboardData?.getData('text/plain')||'';
  document.execCommand('insertText',false,text);
});

function setupMic(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR){E.mic.disabled=true;return}recognition=new SR();recognition.lang='ko-KR';recognition.continuous=true;recognition.interimResults=false;recognition.onresult=e=>{let t='';for(let i=e.resultIndex;i<e.results.length;i++)if(e.results[i].isFinal)t+=e.results[i][0].transcript+' ';if(t.trim()){const q=E.transcript.value&&!E.transcript.value.endsWith('\n')?'\n':'';E.transcript.value+=`${q}[${nowTime()}] ${t.trim()}\n`;E.transcript.dispatchEvent(new Event('input'))}};recognition.onend=()=>{listening=false;E.mic.textContent='🎤 시작';E.mic.classList.remove('listening')};E.mic.onclick=()=>{if(listening){recognition.stop();return}try{recognition.start();listening=true;E.mic.textContent='⏹ 중지';E.mic.classList.add('listening')}catch{}}}

async function composePageImage(pageNo,renderScale=1.7){const page=await pdfDoc.getPage(pageNo),vp=page.getViewport({scale:renderScale});const c=document.createElement('canvas');c.width=Math.ceil(vp.width);c.height=Math.ceil(vp.height);const ctx=c.getContext('2d');await page.render({canvasContext:ctx,viewport:vp}).promise;const a=await get(AS,`${project.id}:${pageNo}`);for(const s of a?.strokes||[]){const fake={...s,points:s.points.map(p=>({x:p.x*c.width,y:p.y*c.height,p:p.p}))};drawStrokeToContext(ctx,fake,renderScale)}for(const q of a?.pins||[]){ctx.save();ctx.fillStyle='#f59e0b';ctx.beginPath();ctx.arc(q.x*c.width,q.y*c.height,8*renderScale,0,Math.PI*2);ctx.fill();ctx.fillStyle='#111827';ctx.font=`bold ${8*renderScale}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText('!',q.x*c.width,q.y*c.height);ctx.restore()}return c}
function drawStrokeToContext(ctx,stroke,renderScale=1){
  const pts=stroke.points||[];if(!pts.length)return;
  ctx.save();ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle=stroke.color||'#e11d48';
  if(stroke.tool==='highlight'){
    ctx.globalCompositeOperation='source-over';ctx.globalAlpha=.25;ctx.lineWidth=(stroke.width||18)*renderScale;
    if(pts.length===1){ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,((stroke.width||18)*renderScale)/2,0,Math.PI*2);ctx.fill();ctx.restore();return;}
    ctx.beginPath();ctx.moveTo(pts[0].x,pts[0].y);
    for(let i=1;i<pts.length;i++)ctx.lineTo(pts[i].x,pts[i].y);
    ctx.stroke();ctx.restore();return;
  }
  ctx.globalCompositeOperation='source-over';ctx.globalAlpha=1;
  const base=(stroke.width||2.2)*renderScale;
  if(pts.length===1){ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,base/2,0,Math.PI*2);ctx.fill();ctx.restore();return;}
  for(let i=0;i<pts.length-1;i++){
    const a=pts[Math.max(0,i-1)],b=pts[i],c=pts[i+1],st={x:(a.x+b.x)/2,y:(a.y+b.y)/2},en={x:(b.x+c.x)/2,y:(b.y+c.y)/2};
    ctx.beginPath();ctx.moveTo(st.x,st.y);ctx.quadraticCurveTo(b.x,b.y,en.x,en.y);ctx.lineWidth=base*(.45+.9*((b.p+c.p)/2||.5));ctx.stroke();
  }
  ctx.restore();
}
function dataUrlToUint8(dataUrl){const b=atob(dataUrl.split(',')[1]),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return u}
function downloadBlob(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1500)}

function pdfColor(hex){
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

E.md.onclick=async()=>{if(!project)return;await Promise.all([saveNote(),saveTranscript()]);const notes=await getByProject(NS,project.id),trans=await getByProject(TS,project.id);let out=`# ${E.title.value||project.title}\n\n`;for(let p=1;p<=pdfDoc.numPages;p++){const n=notes.find(x=>x.page===p),t=trans.find(x=>x.page===p),noteText=n?.text||'',transcriptText=t?.text||'';out+=`<<<PAGE ${p}>>>\n\n### 수업필기\n${noteText}${transcriptText.trim()?`\n\n### 전사문\n${transcriptText}`:''}\n\n`}downloadBlob(new Blob([out],{type:'text/markdown;charset=utf-8'}),`${safe(E.title.value)}_notes.md`)};
E.json.onclick=async()=>{if(!project)return;await Promise.all([saveProject(),saveNote(),saveTranscript(),saveAnnotation()]);const notes=await getByProject(NS,project.id),transcripts=await getByProject(TS,project.id),annotations=await getByProject(AS,project.id);const payload={version:4,exportedAt:new Date().toISOString(),project:{...project,pdfBlob:undefined},notes,transcripts,annotations};downloadBlob(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),`${safe(E.title.value)}_backup.json`)};
E.backupInput.onchange=async e=>{const f=e.target.files?.[0];if(!f)return;try{const j=JSON.parse(await f.text());if(!j.project?.id)throw new Error('bad');const id=j.project.id;project={...j.project,id,pdfBlob:null};await put(PS,project);for(const n of j.notes||[])await put(NS,n);for(const t of j.transcripts||[])await put(TS,t);for(const a of j.annotations||[])await put(AS,a);localStorage.setItem(LAST,id);toast('백업을 복원했습니다. 원본 PDF를 다시 열어주세요.')}catch{toast('백업 파일을 읽지 못했습니다')}};
async function fourUpCell(pageNo){if(pageNo>pdfDoc.numPages)return new TableCell({width:{size:50,type:WidthType.PERCENTAGE},children:[new Paragraph({text:''})]});const c=await composePageImage(pageNo,1.15),png=dataUrlToUint8(c.toDataURL('image/png'));const maxW=245,maxH=315,ratio=c.width/c.height;let w=maxW,h=w/ratio;if(h>maxH){h=maxH;w=h*ratio}return new TableCell({width:{size:50,type:WidthType.PERCENTAGE},children:[new Paragraph({children:[new TextRun({text:`${pageNo}p.`,bold:true,size:18})]}),new Paragraph({alignment:AlignmentType.CENTER,children:[new ImageRun({data:png,transformation:{width:Math.round(w),height:Math.round(h)}})]})]})}
E.docx.onclick=async()=>{if(!project||!pdfDoc)return;toast('Word 4쪽 배치 생성 중…');await Promise.all([saveNote(),saveTranscript(),saveAnnotation()]);const children=[new Paragraph({text:E.title.value||project.title,heading:HeadingLevel.TITLE,alignment:AlignmentType.CENTER})];for(let start=1;start<=pdfDoc.numPages;start+=4){const cells=await Promise.all([0,1,2,3].map(i=>fourUpCell(start+i)));children.push(new Table({width:{size:100,type:WidthType.PERCENTAGE},rows:[new TableRow({children:[cells[0],cells[1]]}),new TableRow({children:[cells[2],cells[3]]})]}));if(start+4<=pdfDoc.numPages)children.push(new Paragraph({children:[new PageBreak()]}))}const doc=new Document({sections:[{properties:{page:{size:{width:11906,height:16838,orientation:PageOrientation.PORTRAIT},margin:{top:360,right:360,bottom:360,left:360}}},children}]});downloadBlob(await Packer.toBlob(doc),`${safe(E.title.value)}_4up.docx`);toast('Word 4쪽 배치 완료')};
E.printBtn.onclick=async()=>{if(!project||!pdfDoc)return;toast('PDF 4쪽 배치 준비 중…');await Promise.all([saveNote(),saveTranscript(),saveAnnotation()]);E.printArea.innerHTML='';for(let start=1;start<=pdfDoc.numPages;start+=4){const sheet=document.createElement('article');sheet.className='sheet4';for(let i=0;i<4;i++){const p=start+i,slot=document.createElement('div');slot.className='slot4';if(p<=pdfDoc.numPages){const c=await composePageImage(p,1.05);slot.innerHTML=`<div class="slotlabel">${p}p.</div><img src="${c.toDataURL('image/jpeg',.9)}">`}else slot.classList.add('empty4');sheet.appendChild(slot)}E.printArea.appendChild(sheet)}setTimeout(()=>window.print(),180)};

E.pdfInput.onchange=e=>{const f=e.target.files?.[0];if(f)loadPdfFile(f)};E.emptyPdf.onchange=e=>{const f=e.target.files?.[0];if(f)loadPdfFile(f)};

// Mouse/trackpad fallback: clicking page edges changes pages; drawing remains Pencil-only by design.
E.pageWrap.addEventListener('mouseup',e=>{if(e.button!==0||tool==='pin'||!project)return;const r=E.inkCanvas.getBoundingClientRect(),x=(e.clientX-r.left)/r.width;if(x<.08)goPage(currentPage-1);else if(x>.92)goPage(currentPage+1)});

db=await openDb();setMdViewMode(mdViewMode);setTranscriptVisible(false);setupMic();await restoreLast();
