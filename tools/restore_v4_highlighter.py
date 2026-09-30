from pathlib import Path
import re

path = Path('v4/app.js')
text = path.read_text(encoding='utf-8')
changed = False

# Track very short Safari/iPad Pencil interruptions so a single highlighter drag
# can be stitched back into one logical stroke.
if 'let lastHighlighterEndAt=0;' not in text:
    anchor = "let penPointerSeenUntil=0,renderGeneration=0;"
    if anchor not in text:
        raise SystemExit('state anchor not found')
    text = text.replace(anchor, anchor + "\nlet lastHighlighterEndAt=0;", 1)
    changed = True

old_end = "function endStylus(){if(!stylusDrawing)return;stylusDrawing=false;stylusPointerId=null;if(currentStroke?.points?.length){pageData.strokes.push(currentStroke);pageData.redo=[];currentStroke=null;lastStylusPoint=null;drawAllStrokes();scheduleSave()}else currentStroke=null}"
new_end = r'''function endStylus(){
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
}'''
if old_end in text:
    text = text.replace(old_end, new_end, 1)
    changed = True
elif 'lastHighlighterEndAt<180' not in text:
    raise SystemExit('endStylus anchor not found')

# Pin placement must be handled before the normal Pencil drawing path because
# iPad touch handlers prevent the synthetic click event that V4 originally used.
if 'async function addPinAt(' not in text:
    anchor = new_end if new_end in text else 'function endStylus()'
    if anchor == 'function endStylus()':
        raise SystemExit('cannot find endStylus for pin helper insertion')
    helper = r'''

async function addPinAt(clientX,clientY){
  if(!project||tool!=='pin')return;
  const pt=pagePointFromClient(clientX,clientY,1);
  const text=prompt('이 위치에 남길 코멘트');
  if(!text?.trim())return;
  pageData.pins.push({id:`p-${Date.now()}`,x:pt.x,y:pt.y,text:text.trim(),time:nowTime()});
  renderPins();
  await saveAnnotation();
  E.status.textContent=`핀 저장됨 · ${nowTime()}`;
}
'''
    text = text.replace(anchor, anchor + helper, 1)
    changed = True

old_pen = "function handlePenPointerDown(e){if(e.pointerType!=='pen'||!project)return;penPointerSeenUntil=performance.now()+1200;e.preventDefault();e.stopPropagation();try{E.inkCanvas.setPointerCapture(e.pointerId)}catch{}beginStylus(e.clientX,e.clientY,pointerPressure(e),e.pointerId)}"
new_pen = r'''function handlePenPointerDown(e){
  if(e.pointerType!=='pen'||!project)return;
  penPointerSeenUntil=performance.now()+1200;e.preventDefault();e.stopPropagation();
  if(tool==='pin'){addPinAt(e.clientX,e.clientY);return;}
  try{E.inkCanvas.setPointerCapture(e.pointerId)}catch{}
  beginStylus(e.clientX,e.clientY,pointerPressure(e),e.pointerId);
}'''
if old_pen in text:
    text = text.replace(old_pen, new_pen, 1)
    changed = True
elif "if(tool==='pin'){addPinAt" not in text:
    raise SystemExit('handlePenPointerDown anchor not found')

# A short finger tap in pin mode places a pin; only non-pin short edge taps turn pages.
old_touch_end = "function onTouchEnd(e){\n  const stylusEnded=[...e.changedTouches].find(isStylusTouch);if(stylusEnded&&stylusDrawing&&String(stylusPointerId).startsWith('stylus-')){e.preventDefault();endStylus();return}\n  const remaining=getFingerTouches(e);if(remaining.length>=2)return;e.preventDefault();if(touchState.mode==='pan'&&!touchState.moved&&performance.now()-touchState.startTime<360&&project){const r=E.inkCanvas.getBoundingClientRect(),x=(touchState.startX-r.left)/r.width;if(x<.12)goPage(currentPage-1);else if(x>.88)goPage(currentPage+1)}E.pageWrap.classList.remove('touching-edge');touchState.mode=null\n}"
new_touch_end = r'''function onTouchEnd(e){
  const stylusEnded=[...e.changedTouches].find(isStylusTouch);if(stylusEnded&&stylusDrawing&&String(stylusPointerId).startsWith('stylus-')){e.preventDefault();endStylus();return}
  const remaining=getFingerTouches(e);if(remaining.length>=2)return;
  e.preventDefault();
  if(touchState.mode==='pan'&&!touchState.moved&&performance.now()-touchState.startTime<360&&project){
    if(tool==='pin') addPinAt(touchState.startX,touchState.startY);
    else{
      const r=E.inkCanvas.getBoundingClientRect(),x=(touchState.startX-r.left)/r.width;
      if(x<.12)goPage(currentPage-1);else if(x>.88)goPage(currentPage+1);
    }
  }
  E.pageWrap.classList.remove('touching-edge');touchState.mode=null;
}'''
if old_touch_end in text:
    text = text.replace(old_touch_end, new_touch_end, 1)
    changed = True
elif "if(tool==='pin') addPinAt" not in text:
    raise SystemExit('onTouchEnd anchor not found')

old_click = "E.inkCanvas.addEventListener('click',e=>{if(!project||tool!=='pin')return;const pt=pagePointFromClient(e.clientX,e.clientY,1);const text=prompt('이 위치에 남길 코멘트');if(!text)return;pageData.pins.push({id:`p-${Date.now()}`,x:pt.x,y:pt.y,text,time:nowTime()});renderPins();scheduleSave()});"
new_click = "E.inkCanvas.addEventListener('click',e=>{if(!project||tool!=='pin')return;addPinAt(e.clientX,e.clientY)});"
if old_click in text:
    text = text.replace(old_click, new_click, 1)
    changed = True

old_pin_click = "b.title=p.text;b.onclick=()=>toast(p.text);"
new_pin_click = "b.title=p.text;b.onpointerdown=e=>e.stopPropagation();b.onclick=e=>{e.stopPropagation();toast(p.text)};"
if old_pin_click in text:
    text = text.replace(old_pin_click, new_pin_click, 1)
    changed = True

# Export highlighter as one V2-style continuous translucent path, instead of
# segment-by-segment multiply strokes that create dark blocks at every join.
pattern = re.compile(r"function drawStrokeToContext\(ctx,stroke,renderScale=1\)\{.*?\}\nfunction dataUrlToUint8", re.S)
replacement = r'''function drawStrokeToContext(ctx,stroke,renderScale=1){
  const pts=stroke.points||[];if(!pts.length)return;
  ctx.save();ctx.lineCap='round';ctx.lineJoin='round';ctx.strokeStyle=stroke.color||'#e11d48';
  if(stroke.tool==='highlight'){
    ctx.globalCompositeOperation='source-over';ctx.globalAlpha=.25;ctx.lineWidth=18*renderScale;
    if(pts.length===1){ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,9*renderScale,0,Math.PI*2);ctx.fill();ctx.restore();return;}
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
function dataUrlToUint8'''
new_text, count = pattern.subn(replacement, text, count=1)
if count == 1:
    text = new_text
    changed = True
elif 'ctx.lineWidth=18*renderScale' not in text:
    raise SystemExit(f'drawStrokeToContext replacement count was {count}')

if not changed:
    print('V4 pin/highlighter fixes already applied')
else:
    path.write_text(text, encoding='utf-8')
    print('Applied V4 pin + continuous highlighter fixes')
