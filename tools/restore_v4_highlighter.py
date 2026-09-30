from pathlib import Path
import re

p=Path('v4/app.js')
s=p.read_text(encoding='utf-8')

start=s.find('function cleanImportedMdBody(')
end=s.find('function setupMic(){', start)
if start < 0 or end < 0:
    raise SystemExit('MD parser block not found')

new_block=r'''function cleanImportedMdBody(body,pageNo){
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

'''
s=s[:start]+new_block+s[end:]

old="### 코멘트\n${n?.text||''}\n\n### 실시간 전사\n${t?.text||''}"
new="### .md / 전사문\n${t?.text||''}\n\n### 수업 필기\n${n?.text||''}"
if old in s:
    s=s.replace(old,new,1)
else:
    # Keep idempotency if already converted.
    if '### .md / 전사문' not in s[s.find('E.md.onclick'):]:
        raise SystemExit('Markdown export block not found')

p.write_text(s,encoding='utf-8')
print('Hardened MD parser and integrated Markdown export')
