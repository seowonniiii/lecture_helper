from pathlib import Path

app_path=Path('v4/app.js')
app=app_path.read_text(encoding='utf-8')

start=app.find('let savedMdRange=null;')
end=app.find("E.mdModeRendered.onclick=()=>setMdViewMode('rendered');", start)
if start < 0 or end < 0:
    raise SystemExit('selection formatter block not found')

new_block=r'''let savedMdRange=null;
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

'''

app=app[:start]+new_block+app[end:]
app_path.write_text(app,encoding='utf-8')
print('Fixed rendered Markdown selection formatting for iPad Safari')
