from pathlib import Path
import re

path = Path('v4/app.js')
text = path.read_text(encoding='utf-8')

pattern = re.compile(r"function drawStroke\(stroke\)\{.*?\n  ctx\.restore\(\)\}\nfunction drawAllStrokes", re.S)
replacement = r'''function drawStroke(stroke){
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
    ctx.lineWidth=18;
    if(pts.length===1){
      ctx.beginPath();ctx.fillStyle=ctx.strokeStyle;ctx.arc(pts[0].x,pts[0].y,9,0,Math.PI*2);ctx.fill();ctx.restore();return;
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
function drawAllStrokes'''

new_text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f'drawStroke replacement count was {count}, expected 1')

old = "currentStroke={id:`s-${Date.now()}-${Math.random().toString(36).slice(2)}`,tool,color:tool==='highlight'?'#facc15':E.inkColor.value,width:lineWidth,points:[pagePointFromClient(clientX,clientY,pressure)]}"
new = "currentStroke={id:`s-${Date.now()}-${Math.random().toString(36).slice(2)}`,tool,color:E.inkColor.value,width:tool==='highlight'?18:lineWidth,points:[pagePointFromClient(clientX,clientY,pressure)]}"
if old not in new_text:
    raise SystemExit('highlight currentStroke initializer not found')
new_text = new_text.replace(old, new, 1)

path.write_text(new_text, encoding='utf-8')
print('Restored V2-style highlighter in V4')
