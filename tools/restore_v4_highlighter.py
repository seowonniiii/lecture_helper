from pathlib import Path

app_path=Path('v4/app.js')
index_path=Path('v4/index.html')
css_path=Path('v4/styles.css')
app=app_path.read_text(encoding='utf-8')
index=index_path.read_text(encoding='utf-8')
css=css_path.read_text(encoding='utf-8')
changed=False

# 1) Add formatting controls to the rendered Markdown toolbar.
old='<div class="mdmode"><button id="mdModeRendered" class="tool active" type="button">결과 편집</button><button id="mdModeRaw" class="tool" type="button">원문</button></div><button id="mic" class="btn micbtn">🎤 시작</button>'
new='<div class="mdmode"><button id="mdModeRendered" class="tool active" type="button">결과 편집</button><button id="mdModeRaw" class="tool" type="button">원문</button></div><div class="mdformat"><button id="mdBold" class="tool fmt-bold" type="button" title="선택 영역 굵게"><b>B</b></button><button id="mdExam" class="tool fmt-exam" type="button" title="선택 영역 시험강조">시험</button><button id="mdHighlight" class="tool fmt-highlight" type="button" title="선택 영역 하이라이트">형광</button></div><button id="mic" class="btn micbtn">🎤 시작</button>'
if old in index:
    index=index.replace(old,new,1);changed=True
elif 'id="mdBold"' not in index:
    raise SystemExit('format toolbar anchor not found')

# 2) Register the new buttons.
old_map="mdRendered:$('mdRendered'),mdModeRendered:$('mdModeRendered'),mdModeRaw:$('mdModeRaw'),pinPopover:$('pinPopover')"
new_map="mdRendered:$('mdRendered'),mdModeRendered:$('mdModeRendered'),mdModeRaw:$('mdModeRaw'),mdBold:$('mdBold'),mdExam:$('mdExam'),mdHighlight:$('mdHighlight'),pinPopover:$('pinPopover')"
if old_map in app:
    app=app.replace(old_map,new_map,1);changed=True
elif "mdBold:$('mdBold')" not in app:
    raise SystemExit('element map anchor not found')

# 3) Preserve iPad/Safari text selection while tapping the toolbar, then apply formatting.
if 'function applyMdInlineFormat(' not in app:
    anchor="E.mdModeRendered.onclick=()=>setMdViewMode('rendered');"
    helper=r'''let savedMdRange=null;
function saveMdSelection(){
  const sel=window.getSelection();
  if(!sel||!sel.rangeCount||sel.isCollapsed)return;
  const r=sel.getRangeAt(0),node=r.commonAncestorContainer.nodeType===1?r.commonAncestorContainer:r.commonAncestorContainer.parentElement;
  if(node&&E.mdRendered.contains(node))savedMdRange=r.cloneRange();
}
function restoreMdSelection(){
  if(!savedMdRange)return null;
  const sel=window.getSelection();
  sel.removeAllRanges();sel.addRange(savedMdRange.cloneRange());
  return sel.getRangeAt(0);
}
function notifyRenderedChanged(){
  E.mdRendered.dispatchEvent(new Event('input',{bubbles:true}));
  saveMdSelection();
}
function applyMdInlineFormat(kind){
  if(mdViewMode!=='rendered'){setMdViewMode('rendered');toast('결과 편집에서 텍스트를 선택해주세요');return}
  const r=restoreMdSelection();
  if(!r||r.collapsed){toast('먼저 적용할 글자를 선택해주세요');return}
  const sel=window.getSelection();
  if(kind==='bold'){
    document.execCommand('bold',false,null);
    saveMdSelection();notifyRenderedChanged();return;
  }
  const tag=kind==='exam'?'exam':'mark';
  const wrapper=document.createElement(tag);
  try{
    const frag=r.extractContents();wrapper.appendChild(frag);r.insertNode(wrapper);
    const nr=document.createRange();nr.selectNodeContents(wrapper);sel.removeAllRanges();sel.addRange(nr);savedMdRange=nr.cloneRange();
    notifyRenderedChanged();
  }catch(e){console.error(e);toast('이 선택 영역은 나눠서 적용해주세요')}
}
document.addEventListener('selectionchange',saveMdSelection);
[E.mdBold,E.mdExam,E.mdHighlight].forEach(b=>{
  b.addEventListener('pointerdown',e=>e.preventDefault());
  b.addEventListener('mousedown',e=>e.preventDefault());
});
E.mdBold.onclick=()=>applyMdInlineFormat('bold');
E.mdExam.onclick=()=>applyMdInlineFormat('exam');
E.mdHighlight.onclick=()=>applyMdInlineFormat('highlight');

'''
    if anchor not in app: raise SystemExit('rendered mode handler anchor not found')
    app=app.replace(anchor,helper+anchor,1);changed=True

# 4) Styling for the inline formatting toolbar.
if '/* V4 rendered selection formatting */' not in css:
    css+=r'''

/* V4 rendered selection formatting */
.mdformat{display:flex;gap:3px;padding:2px;border:1px solid var(--border);border-radius:9px;background:#fff}.mdformat .tool{min-height:27px;padding:0 8px;font-size:9px;border:0}.mdformat .fmt-bold{font-size:11px}.mdformat .fmt-exam{color:#dc2626;font-weight:800;background:#fff1f2}.mdformat .fmt-highlight{font-weight:800;background:#fef08a;color:#713f12}.mdformat .tool:active{transform:translateY(1px)}
'''
    changed=True

if not changed:
    print('Selection formatting already applied')
else:
    app_path.write_text(app,encoding='utf-8')
    index_path.write_text(index,encoding='utf-8')
    css_path.write_text(css,encoding='utf-8')
    print('Applied rendered Markdown selection formatting controls')
