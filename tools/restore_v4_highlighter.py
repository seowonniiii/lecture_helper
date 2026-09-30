from pathlib import Path

app_path=Path('v4/app.js')
index_path=Path('v4/index.html')
css_path=Path('v4/styles.css')
app=app_path.read_text(encoding='utf-8')
index=index_path.read_text(encoding='utf-8')
css=css_path.read_text(encoding='utf-8')
changed=False

# Browser Markdown renderer + HTML->Markdown conversion for direct rendered editing.
if "from 'https://cdn.jsdelivr.net/npm/marked" not in app:
    anchor="import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';"
    extra="""import * as pdfjsLib from 'https://cdn.jsdelivr.net/npm/pdfjs-dist@6.3.289/build/pdf.min.mjs';
import { marked } from 'https://cdn.jsdelivr.net/npm/marked@18.0.14/lib/marked.esm.js';
import TurndownService from 'https://cdn.jsdelivr.net/npm/turndown@7.2.4/+esm';
import { gfm } from 'https://cdn.jsdelivr.net/npm/@truto/turndown-plugin-gfm@1.0.3/+esm';"""
    if anchor not in app: raise SystemExit('import anchor not found')
    app=app.replace(anchor,extra,1);changed=True

old_e="mdInput:$('mdInput'),mdFilename:$('mdFilename'),pinPopover:$('pinPopover')"
new_e="mdInput:$('mdInput'),mdFilename:$('mdFilename'),mdRendered:$('mdRendered'),mdModeRendered:$('mdModeRendered'),mdModeRaw:$('mdModeRaw'),pinPopover:$('pinPopover')"
if old_e in app:
    app=app.replace(old_e,new_e,1);changed=True
elif "mdRendered:$('mdRendered')" not in app:
    raise SystemExit('E map anchor not found')

# Add rendered/raw mode buttons next to MD import.
old_actions='<div class="paneActions"><label class="btn mdload">MD 불러오기<input id="mdInput" type="file" accept=".md,text/markdown,text/plain" hidden></label><button id="mic" class="btn micbtn">🎤 시작</button></div>'
new_actions='<div class="paneActions"><label class="btn mdload">MD 불러오기<input id="mdInput" type="file" accept=".md,text/markdown,text/plain" hidden></label><div class="mdmode"><button id="mdModeRendered" class="tool active" type="button">결과 편집</button><button id="mdModeRaw" class="tool" type="button">원문</button></div><button id="mic" class="btn micbtn">🎤 시작</button></div>'
if old_actions in index:
    index=index.replace(old_actions,new_actions,1);changed=True
elif 'id="mdModeRendered"' not in index:
    raise SystemExit('pane actions anchor not found')

old_area='<textarea id="transcript" class="transcript" placeholder="<<<PAGE n>>> 형식의 .md 파일을 불러오거나 직접 수정하세요. 음성 전사도 이 칸에 추가됩니다."></textarea>'
new_area='''<div class="mdEditorStack">
          <div id="mdRendered" class="mdRendered markdown-body" contenteditable="true" spellcheck="false" data-placeholder="MD를 불러오면 실제 출력 형태로 보면서 바로 수정할 수 있습니다."></div>
          <textarea id="transcript" class="transcript mdRaw hidden" placeholder="<<<PAGE n>>> 형식의 .md 파일을 불러오거나 직접 수정하세요. 음성 전사도 이 칸에 추가됩니다."></textarea>
        </div>'''
if old_area in index:
    index=index.replace(old_area,new_area,1);changed=True
elif 'id="mdRendered"' not in index:
    raise SystemExit('transcript textarea anchor not found')

# Add editor engine after DOM element map.
if 'const mdTurndown=' not in app:
    anchor="let db,pdfDoc=null"
    helper=r'''const mdTurndown=new TurndownService({headingStyle:'atx',bulletListMarker:'-',codeBlockStyle:'fenced',emDelimiter:'*',strongDelimiter:'**'});
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

'''
    pos=app.find(anchor)
    if pos<0: raise SystemExit('state anchor not found')
    app=app[:pos]+helper+app[pos:];changed=True

# Keep rendered view synchronized on page changes.
needle="E.transcript.value=t?.text||'';E.transcriptChars.textContent=`${E.transcript.value.length}자`;pageData="
replacement="E.transcript.value=t?.text||'';E.transcriptChars.textContent=`${E.transcript.value.length}자`;syncMdRendered();pageData="
if needle in app:
    app=app.replace(needle,replacement,1);changed=True
elif 'syncMdRendered();pageData=' not in app:
    raise SystemExit('renderPage transcript anchor not found')

# Replace transcript input handler with bidirectional raw/rendered synchronization.
old_handler="E.transcript.addEventListener('input',()=>{E.transcriptChars.textContent=`${E.transcript.value.length}자`;scheduleSave()});"
new_handler="E.transcript.addEventListener('input',()=>{E.transcriptChars.textContent=`${E.transcript.value.length}자`;if(!syncingRenderedEdit&&mdViewMode==='rendered')syncMdRendered();scheduleSave()});"
if old_handler in app:
    app=app.replace(old_handler,new_handler,1);changed=True
elif "if(!syncingRenderedEdit&&mdViewMode==='rendered')" not in app:
    raise SystemExit('transcript input handler anchor not found')

# Add direct rendered editing and toggle events before setupMic.
if "E.mdRendered.addEventListener('input'" not in app:
    anchor='function setupMic(){'
    handlers=r'''E.mdModeRendered.onclick=()=>setMdViewMode('rendered');
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

'''
    if anchor not in app: raise SystemExit('setupMic anchor not found')
    app=app.replace(anchor,handlers+anchor,1);changed=True

# Initialize remembered mode before restoring saved project.
old_bottom='db=await openDb();setupMic();await restoreLast();'
new_bottom='db=await openDb();setMdViewMode(mdViewMode);setupMic();await restoreLast();'
if old_bottom in app:
    app=app.replace(old_bottom,new_bottom,1);changed=True
elif 'setMdViewMode(mdViewMode);setupMic();await restoreLast();' not in app:
    raise SystemExit('startup anchor not found')

if '/* V4 rendered Markdown editor */' not in css:
    css+=r'''

/* V4 rendered Markdown editor */
.mdmode{display:flex;gap:3px;padding:2px;border:1px solid var(--border);border-radius:9px;background:#fff}.mdmode .tool{min-height:27px;padding:0 7px;font-size:9px;border:0}.mdmode .tool.active{background:#111827;color:#fff}.mdEditorStack{flex:1 1 260px;min-height:260px;display:flex;min-width:0}.mdEditorStack>.transcript,.mdRendered{width:100%;min-height:260px;max-height:none;overflow:auto}.mdRendered{box-sizing:border-box;padding:12px 14px;background:#fff;border:1px solid var(--border);border-radius:11px;outline:none;font-size:12px;line-height:1.62;color:#111827;word-break:break-word;-webkit-user-select:text;user-select:text}.mdRendered:focus{border-color:#7c3aed;box-shadow:0 0 0 2px rgba(124,58,237,.1)}.mdRendered:empty:before{content:attr(data-placeholder);color:#9ca3af;pointer-events:none}.mdRendered h1,.mdRendered h2,.mdRendered h3,.mdRendered h4{line-height:1.25;margin:.75em 0 .35em}.mdRendered h1{font-size:1.45em}.mdRendered h2{font-size:1.28em}.mdRendered h3{font-size:1.13em}.mdRendered p{margin:.4em 0}.mdRendered ul,.mdRendered ol{padding-left:1.6em;margin:.45em 0}.mdRendered li{margin:.16em 0}.mdRendered blockquote{margin:.5em 0;padding:.25em .8em;border-left:3px solid #c4b5fd;color:#4b5563;background:#faf9ff}.mdRendered code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;background:#f3f4f6;border-radius:4px;padding:.08em .3em}.mdRendered pre{overflow:auto;background:#111827;color:#f9fafb;padding:10px;border-radius:8px}.mdRendered pre code{background:transparent;padding:0}.mdRendered table{width:100%;border-collapse:collapse;margin:.6em 0;font-size:.95em}.mdRendered th,.mdRendered td{border:1px solid #d1d5db;padding:5px 7px;vertical-align:top}.mdRendered th{background:#f3f4f6;font-weight:800}.mdRendered strong{font-weight:800}.mdRendered mark{background:#fef08a;padding:0 .08em}.mdRendered exam{color:#dc2626;font-weight:800;background:#fff1f2;padding:0 .08em;border-radius:3px}.mdRendered hr{border:0;border-top:1px solid #e5e7eb;margin:1em 0}.mdRendered a{color:#2563eb;text-decoration:underline}.mdRaw{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.55}.hidden{display:none!important}
'''
    changed=True

if not changed:
    print('Rendered Markdown editor already applied')
else:
    app_path.write_text(app,encoding='utf-8')
    index_path.write_text(index,encoding='utf-8')
    css_path.write_text(css,encoding='utf-8')
    print('Applied rendered Markdown WYSIWYG editor with raw toggle')
