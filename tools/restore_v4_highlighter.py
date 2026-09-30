from pathlib import Path

app_path = Path('v4/app.js')
index_path = Path('v4/index.html')
css_path = Path('v4/styles.css')

app = app_path.read_text(encoding='utf-8')
index = index_path.read_text(encoding='utf-8')
css = css_path.read_text(encoding='utf-8')
changed = False

# 1) Rebuild the PAGE NOTE workspace as a 50:50 split:
#    left = imported/editable Markdown transcript, right = class notes.
old_aside_start = '<aside class="notes">'
old_aside_end = '</aside>\n</main>'
start = index.find(old_aside_start)
end = index.find(old_aside_end, start)
if start != -1 and end != -1 and 'id="mdInput"' not in index:
    new_aside = '''<aside class="notes">
    <div class="nhead"><div><small style="color:#6b7280;font-weight:800">PAGE NOTE</small><h2><span id="pLabel">1</span>p.</h2></div></div>
    <div class="noteSplit">
      <section class="notePane transcriptPane">
        <div class="paneHead">
          <div><b>📄 .md / 전사문</b><small id="mdFilename">페이지별 전사문 · 수정 가능</small></div>
          <div class="paneActions"><label class="btn mdload">MD 불러오기<input id="mdInput" type="file" accept=".md,text/markdown,text/plain" hidden></label><button id="mic" class="btn micbtn">🎤 시작</button></div>
        </div>
        <textarea id="transcript" class="transcript" placeholder="<<<PAGE n>>> 형식의 .md 파일을 불러오거나 직접 수정하세요. 음성 전사도 이 칸에 추가됩니다."></textarea>
        <div class="meta"><span id="transcriptChars">0자</span><span>전사문 자동저장</span></div>
      </section>
      <section class="notePane classNotePane">
        <div class="paneHead"><div><b>✍️ 수업 필기</b><small>기존 Page Note 그대로 유지</small></div></div>
        <div class="tags"><button class="tag exam" data-tag="[시험] ">시험</button><button class="tag important" data-tag="[중요] ">중요</button><button class="tag prof" data-tag="[교수설명] ">교수설명</button><button class="tag question" data-tag="[질문] ">질문</button><button id="time" class="tag">시간</button></div>
        <textarea id="editor" class="editor" placeholder="이 페이지의 수업 필기를 입력하세요."></textarea>
        <div class="meta"><span id="chars">0자</span><span>수업 필기 자동저장</span></div>
      </section>
    </div>
    <div class="pinsbox"><b>📌 이 페이지 코멘트 핀</b><div id="pinList" class="pinlist"></div></div>
    <div class="exports"><button id="docx">Word<br><small>A4 4쪽 배치</small></button><button id="printBtn">PDF<br><small>A4 4쪽 배치</small></button><button id="md">Markdown<br><small>전사문+수업 필기</small></button><button id="json">JSON<br><small>전체 백업</small></button></div>
  </aside>'''
    index = index[:start] + new_aside + index[end + len('</aside>'):]
    changed = True

# 2) Register new MD file controls in JS.
old_e = "viewCount:$('viewCount'),pinPopover:$('pinPopover'),pinText:$('pinText'),pinSave:$('pinSave'),pinCancel:$('pinCancel')"
new_e = "viewCount:$('viewCount'),mdInput:$('mdInput'),mdFilename:$('mdFilename'),pinPopover:$('pinPopover'),pinText:$('pinText'),pinSave:$('pinSave'),pinCancel:$('pinCancel')"
if old_e in app:
    app = app.replace(old_e, new_e, 1)
    changed = True

# 3) Add robust page-separated Markdown import. It only writes TS (transcript)
#    and never touches NS (the user's class Page Note store).
if 'function parseMarkdownPages(' not in app:
    anchor = 'function setupMic(){'
    helper = r'''function cleanImportedMdBody(body,pageNo){
  let s=(body||'').trim();
  s=s.replace(new RegExp(`^\\s*${pageNo}\\s*p\\.\\s*`,'i'),'').trim();
  const own=s.match(/###\\s*(?:\\.md\\s*\\/?\\s*전사문|실시간\\s*전사|전사문)[^\\n]*\\n([\\s\\S]*?)(?=\\n###\\s|$)/i);
  return (own?own[1]:s).trim();
}
function parseMarkdownPages(text){
  const src=String(text||'');
  const markers=[...src.matchAll(/<<<PAGE\\s+(\\d+)>>>/gi)];
  const out=[];
  if(markers.length){
    for(let i=0;i<markers.length;i++){
      const page=Number(markers[i][1]);
      const from=markers[i].index+markers[i][0].length;
      const to=i+1<markers.length?markers[i+1].index:src.length;
      out.push({page,text:cleanImportedMdBody(src.slice(from,to),page)});
    }
    return out;
  }
  const headings=[...src.matchAll(/^\\s*(?:#{1,6}\\s*)?(\\d+)\\s*p\\.\\s*$/gmi)];
  if(headings.length){
    for(let i=0;i<headings.length;i++){
      const page=Number(headings[i][1]);
      const from=headings[i].index+headings[i][0].length;
      const to=i+1<headings.length?headings[i+1].index:src.length;
      out.push({page,text:cleanImportedMdBody(src.slice(from,to),page)});
    }
    return out;
  }
  return [{page:currentPage,text:src.trim()}];
}
async function importMarkdownFile(file){
  if(!project||!pdfDoc){toast('먼저 PDF를 열어주세요');return}
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

'''
    if anchor not in app:
        raise SystemExit('setupMic anchor not found')
    app = app.replace(anchor, helper + anchor, 1)
    changed = True

# 4) Make the exported Markdown mirror the left/right editor layout.
old_md = "out+=`<<<PAGE ${p}>>>\\n\\n${p}p.\\n\\n### 코멘트\\n${n?.text||''}\\n\\n### 실시간 전사\\n${t?.text||''}\\n\\n`"
new_md = "out+=`<<<PAGE ${p}>>>\\n\\n${p}p.\\n\\n### .md / 전사문\\n${t?.text||''}\\n\\n### 수업 필기\\n${n?.text||''}\\n\\n`"
if old_md in app:
    app = app.replace(old_md, new_md, 1)
    changed = True

# 5) Add split workspace styling. Desktop side panel gets enough width;
#    iPad/mobile stacked viewer still gives the note workspace the full screen width.
if '/* V4 MD split workspace */' not in css:
    css += r'''

/* V4 MD split workspace */
@media(min-width:901px){.shell{grid-template-columns:minmax(0,1fr) minmax(560px,42vw)}}
.noteSplit{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px;min-height:330px;align-items:stretch}.notePane{min-width:0;display:flex;flex-direction:column;gap:8px;border:1px solid var(--border);border-radius:14px;padding:10px;background:#fafbfc}.transcriptPane{background:#f8faff;border-color:#c7d2fe}.classNotePane{background:#fff}.paneHead{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;min-height:38px}.paneHead>div:first-child{display:grid;gap:2px}.paneHead b{font-size:12px}.paneHead small{font-size:9px;color:var(--muted);line-height:1.35}.paneActions{display:flex;gap:5px;align-items:center;flex-wrap:wrap;justify-content:flex-end}.mdload,.paneActions .micbtn{min-height:32px;padding:0 8px;font-size:10px}.noteSplit .editor,.noteSplit .transcript{flex:1 1 260px;min-height:260px;max-height:none;height:auto;resize:vertical}.noteSplit .transcript{background:#fff}.notes{gap:10px}.notes>.pinsbox{margin-top:2px}
@media(max-width:600px){.noteSplit{grid-template-columns:1fr}.noteSplit .editor,.noteSplit .transcript{min-height:220px}}
'''
    changed = True

if not changed:
    print('V4 MD split workspace already applied')
else:
    app_path.write_text(app,encoding='utf-8')
    index_path.write_text(index,encoding='utf-8')
    css_path.write_text(css,encoding='utf-8')
    print('Applied V4 MD import + editable split note workspace')
