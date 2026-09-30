from pathlib import Path

COMMON_CSS = r'''
/* UX patch: top page navigation, bottom filename, switchable notes panel */
.viewer{display:flex!important;flex-direction:column!important;min-width:0}
.viewer>.toolbar{flex:0 0 auto}.viewer>.pdfstage,.viewer>.stage{flex:1 1 auto;min-height:0}.viewer>.filebar{flex:0 0 auto}
.toolbar .nav{order:-20;flex:0 0 100%;width:100%;border:0!important;background:transparent!important;padding:0!important;min-height:38px}
.filebar{min-height:28px;padding:6px 12px;background:#f8f9fa;border-top:1px solid var(--border);display:flex;align-items:center;justify-content:center}
.filebar .file{max-width:92vw;text-align:center}
.layout-toggle{white-space:nowrap}
.shell.notes-bottom{height:auto!important;min-height:calc(100vh - 62px);grid-template-columns:1fr!important;grid-template-rows:minmax(62vh,1fr) auto!important}
.shell.notes-bottom .notes{border-left:0!important;border-top:1px solid var(--border)!important;min-height:340px;max-height:none}
.shell.notes-bottom .viewer{min-height:62vh}
@media(max-width:900px){.layout-toggle{display:inline-flex}.shell.notes-bottom{grid-template-rows:minmax(58vh,1fr) auto!important}}
'''

def inject_common(path: str, version: str, renderer: str):
    p = Path(path)
    s = p.read_text(encoding='utf-8')
    marker = '/* UX patch: top page navigation, bottom filename, switchable notes panel */'
    if marker not in s:
        s = s.replace('</style>', COMMON_CSS + '\n</style>', 1)

    token = f'// UX patch {version}'
    if token not in s:
        js = f'''
// UX patch {version}
{{
  const shell=document.querySelector('.shell');
  const viewer=document.querySelector('.viewer');
  const toolbar=document.querySelector('.toolbar');
  const nav=document.querySelector('.nav');
  if(toolbar&&nav&&!toolbar.contains(nav)) toolbar.prepend(nav);
  if(viewer&&E.filename&&!document.querySelector('.filebar')){{
    const filebar=document.createElement('div');
    filebar.className='filebar';
    filebar.appendChild(E.filename);
    viewer.appendChild(filebar);
  }}
  const layoutKey='lecture-helper-{version.lower()}-notes-layout';
  const layoutBtn=document.createElement('button');
  layoutBtn.type='button';
  layoutBtn.className='btn layout-toggle';
  const applyLayout=()=>{{
    const bottom=localStorage.getItem(layoutKey)==='bottom';
    shell?.classList.toggle('notes-bottom',bottom);
    layoutBtn.textContent=bottom?'▥ 코멘트 오른쪽':'▤ 코멘트 하단';
  }};
  layoutBtn.onclick=()=>{{
    localStorage.setItem(layoutKey,shell?.classList.contains('notes-bottom')?'right':'bottom');
    applyLayout();
    if(pdfDoc){{fit=true;{renderer};}}
  }};
  toolbar?.appendChild(layoutBtn);
  applyLayout();
}}
'''
        s = s.replace('</script>', js + '\n</script>', 1)
    p.write_text(s, encoding='utf-8')

inject_common('v1/index.html', 'V1', 'render()')
inject_common('v2/index.html', 'V2', 'renderPdf()')

# V1: tap slide edges to move pages.
p = Path('v1/index.html')
s = p.read_text(encoding='utf-8')
if '// V1 edge tap navigation' not in s:
    js = r'''
// V1 edge tap navigation
let v1EdgeStart=null;
E.canvas.addEventListener('pointerdown',ev=>{
  const r=E.canvas.getBoundingClientRect();
  v1EdgeStart={x:ev.clientX,y:ev.clientY,t:Date.now(),rx:(ev.clientX-r.left)/r.width};
});
E.canvas.addEventListener('pointerup',ev=>{
  if(!v1EdgeStart||!pdfDoc)return;
  const d=Math.hypot(ev.clientX-v1EdgeStart.x,ev.clientY-v1EdgeStart.y),dt=Date.now()-v1EdgeStart.t,x=v1EdgeStart.rx;
  v1EdgeStart=null;
  if(d>14||dt>550)return;
  if(x<.18)go(currentPage-1);else if(x>.82)go(currentPage+1);
});
'''
    s = s.replace('</script>', js + '\n</script>', 1)
p.write_text(s, encoding='utf-8')

# V2: robust Pencil detection + manual finger pan + narrow edge tap navigation.
p = Path('v2/index.html')
s = p.read_text(encoding='utf-8')

# Prevent Safari from stealing Pencil strokes; finger panning is handled manually below.
s = s.replace('.ink{position:absolute;left:0;top:0;touch-action:pan-x pan-y}', '.ink{position:absolute;left:0;top:0;touch-action:none}', 1)
s = s.replace('.ink{position:absolute;left:0;top:0;touch-action:auto}', '.ink{position:absolute;left:0;top:0;touch-action:none}', 1)

old_pointerdown = "E.inkCanvas.addEventListener('pointerdown',async ev=>{if(ev.pointerType!=='pen'){v2FingerStart={x:ev.clientX,y:ev.clientY,t:Date.now()};return}if(tool==='pin'){"
new_pointerdown = "E.inkCanvas.addEventListener('pointerdown',async ev=>{if(!isStylusPointer(ev)){const r=E.inkCanvas.getBoundingClientRect();v2FingerStart={x:ev.clientX,y:ev.clientY,t:Date.now(),rx:(ev.clientX-r.left)/r.width,scrollLeft:E.stage.scrollLeft,scrollTop:E.stage.scrollTop,moved:false};try{E.inkCanvas.setPointerCapture(ev.pointerId)}catch{}return}if(tool==='pin'){"
if old_pointerdown in s:
    s = s.replace(old_pointerdown, new_pointerdown, 1)

old_pointermove = "E.inkCanvas.addEventListener('pointermove',ev=>{if(ev.pointerType!=='pen'||!drawing||!currentStroke)return;currentStroke.points.push(normPos(ev));redrawInk();drawStroke(E.inkCanvas.getContext('2d'),currentStroke,E.inkCanvas.width,E.inkCanvas.height);ev.preventDefault()});"
new_pointermove = "E.inkCanvas.addEventListener('pointermove',ev=>{if(isStylusPointer(ev)){if(!drawing||!currentStroke)return;currentStroke.points.push(normPos(ev));redrawInk();drawStroke(E.inkCanvas.getContext('2d'),currentStroke,E.inkCanvas.width,E.inkCanvas.height);ev.preventDefault();return}if(!v2FingerStart)return;const dx=ev.clientX-v2FingerStart.x,dy=ev.clientY-v2FingerStart.y;if(Math.hypot(dx,dy)>7)v2FingerStart.moved=true;E.stage.scrollLeft=v2FingerStart.scrollLeft-dx;E.stage.scrollTop=v2FingerStart.scrollTop-dy;ev.preventDefault()});"
if old_pointermove in s:
    s = s.replace(old_pointermove, new_pointermove, 1)

old_end = "async function endDraw(ev){if(ev&&ev.pointerType!=='pen')return;if(!drawing||!currentStroke)return;"
new_end = "async function endDraw(ev){if(ev&&!isStylusPointer(ev))return;if(!drawing||!currentStroke)return;"
if old_end in s:
    s = s.replace(old_end, new_end, 1)

marker = '// V2 Apple Pencil only + finger edge navigation'
if marker in s:
    start = s.index(marker)
    end = s.index('</script>', start)
    replacement = r'''// V2 Apple Pencil only + finger edge navigation
let v2FingerStart=null;
function isStylusPointer(ev){
  if(ev.pointerType==='pen') return true;
  // iPad/Safari fallback: some Apple Pencil events may surface as touch-like pointers.
  const w=Number(ev.width||99),h=Number(ev.height||99),p=Number(ev.pressure||0);
  return ev.pointerType==='touch' && p>0 && w<=8 && h<=8;
}
E.inkCanvas.addEventListener('pointerup',ev=>{
  if(isStylusPointer(ev)||!v2FingerStart||!pdfDoc)return;
  const start=v2FingerStart;
  v2FingerStart=null;
  const d=Math.hypot(ev.clientX-start.x,ev.clientY-start.y),dt=Date.now()-start.t;
  if(start.moved||d>9||dt>450)return;
  // Only a short finger tap in the outer 10% changes page.
  if(start.rx<.10)go(currentPage-1);
  else if(start.rx>.90)go(currentPage+1);
},{passive:true});
E.inkCanvas.addEventListener('pointercancel',ev=>{
  if(!isStylusPointer(ev))v2FingerStart=null;
},{passive:true});
'''
    s = s[:start] + replacement + '\n' + s[end:]
else:
    replacement = r'''
// V2 Apple Pencil only + finger edge navigation
let v2FingerStart=null;
function isStylusPointer(ev){
  if(ev.pointerType==='pen') return true;
  const w=Number(ev.width||99),h=Number(ev.height||99),p=Number(ev.pressure||0);
  return ev.pointerType==='touch' && p>0 && w<=8 && h<=8;
}
E.inkCanvas.addEventListener('pointerup',ev=>{
  if(isStylusPointer(ev)||!v2FingerStart||!pdfDoc)return;
  const start=v2FingerStart;v2FingerStart=null;
  const d=Math.hypot(ev.clientX-start.x,ev.clientY-start.y),dt=Date.now()-start.t;
  if(start.moved||d>9||dt>450)return;
  if(start.rx<.10)go(currentPage-1);else if(start.rx>.90)go(currentPage+1);
},{passive:true});
E.inkCanvas.addEventListener('pointercancel',ev=>{if(!isStylusPointer(ev))v2FingerStart=null;},{passive:true});
'''
    s = s.replace('</script>', replacement + '\n</script>', 1)

# Make the UI wording match the behavior.
s = s.replace('Apple Pencil로 필기하고, 손가락은 스크롤·페이지 이동에 사용할 수 있어요.','Apple Pencil로 필기하고, 손가락은 스크롤 및 좌우 가장자리 탭으로 페이지 이동에 사용해요.',1)

p.write_text(s, encoding='utf-8')
