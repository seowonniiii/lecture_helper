from pathlib import Path

p = Path('v4/app.js')
s = p.read_text(encoding='utf-8')

# 1) Separate persistent highlighter width from pen width.
old = "listening=false,lineWidth=2.2,viewCount="
new = "listening=false,lineWidth=2.2,highlightWidth=Math.max(6,Math.min(40,Number(localStorage.getItem('lh-v4-highlight-width'))||18)),viewCount="
if old in s:
    s = s.replace(old, new, 1)
elif "highlightWidth=Math.max(6,Math.min(40" not in s:
    raise SystemExit('state anchor not found')

# 2) Render each highlighter stroke using the width stored on that stroke.
s = s.replace("ctx.lineWidth=18;", "ctx.lineWidth=stroke.width||18;", 1)
s = s.replace("ctx.arc(pts[0].x,pts[0].y,9,0,Math.PI*2)", "ctx.arc(pts[0].x,pts[0].y,(stroke.width||18)/2,0,Math.PI*2)", 1)

# 3) New highlighter strokes use the currently selected highlighter width.
s = s.replace("width:tool==='highlight'?18:lineWidth", "width:tool==='highlight'?highlightWidth:lineWidth", 1)

# 4) +/- controls adjust the active drawing tool. Highlighter uses 2px steps and persists.
old_controls = "E.thin.onclick=()=>{lineWidth=clamp(lineWidth-.5,.8,8);toast(`굵기 ${lineWidth.toFixed(1)}`)};E.thick.onclick=()=>{lineWidth=clamp(lineWidth+.5,.8,8);toast(`굵기 ${lineWidth.toFixed(1)}`)};"
new_controls = "E.thin.onclick=()=>{if(tool==='highlight'){highlightWidth=clamp(highlightWidth-2,6,40);localStorage.setItem('lh-v4-highlight-width',String(highlightWidth));toast(`형광펜 굵기 ${highlightWidth}`)}else{lineWidth=clamp(lineWidth-.5,.8,8);toast(`펜 굵기 ${lineWidth.toFixed(1)}`)}};E.thick.onclick=()=>{if(tool==='highlight'){highlightWidth=clamp(highlightWidth+2,6,40);localStorage.setItem('lh-v4-highlight-width',String(highlightWidth));toast(`형광펜 굵기 ${highlightWidth}`)}else{lineWidth=clamp(lineWidth+.5,.8,8);toast(`펜 굵기 ${lineWidth.toFixed(1)}`)}};"
if old_controls in s:
    s = s.replace(old_controls, new_controls, 1)
elif "형광펜 굵기" not in s:
    raise SystemExit('width control anchor not found')

# 5) DOCX/PDF export honors the stored width too.
s = s.replace("ctx.globalCompositeOperation='source-over';ctx.globalAlpha=.25;ctx.lineWidth=18*renderScale;", "ctx.globalCompositeOperation='source-over';ctx.globalAlpha=.25;ctx.lineWidth=(stroke.width||18)*renderScale;", 1)
s = s.replace("ctx.arc(pts[0].x,pts[0].y,9*renderScale,0,Math.PI*2)", "ctx.arc(pts[0].x,pts[0].y,((stroke.width||18)*renderScale)/2,0,Math.PI*2)", 1)

p.write_text(s, encoding='utf-8')
print('Added persistent adjustable highlighter width to V4')
