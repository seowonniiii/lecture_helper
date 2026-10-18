// Preserve PDF text fill colors without OCR or text rasterization.
// Returns exact #RRGGBB colors and compact, safe inline HTML for Markdown.

function colorHex(argb) {
  if (typeof argb !== 'number' || !Number.isFinite(argb)) return '#000000';
  return '#' + (argb >>> 0 & 0xffffff).toString(16).padStart(6, '0');
}

export function colorLabel(hex) {
  const r=parseInt(hex.slice(1,3),16)/255,g=parseInt(hex.slice(3,5),16)/255,b=parseInt(hex.slice(5,7),16)/255;
  const max=Math.max(r,g,b),min=Math.min(r,g,b),delta=max-min;
  if(max<0.12)return '검정';
  if(delta<0.12)return max>0.91?'흰색':'회색';
  let hue=0;
  if(max===r)hue=((g-b)/delta)%6;
  else if(max===g)hue=(b-r)/delta+2;
  else hue=(r-g)/delta+4;
  hue=(hue*60+360)%360;
  if(hue<16||hue>=346)return '빨강';
  if(hue<45)return '주황';
  if(hue<70)return '노랑';
  if(hue<170)return '초록';
  if(hue<200)return '청록';
  if(hue<260)return '파랑';
  if(hue<300)return '보라';
  return '분홍';
}

const escapeHtml=s=>s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const normalize=s=>s.replace(/\s+/gu,'');

export function renderColoredWalk(stext, originalPlainText) {
  const lines=[];
  const counts={};
  let current=null,atBlockBoundary=false,coloredChars=0;

  function flushLine(){
    if(current!==null){lines.push(current);current=null}
  }
  stext.walk({
    beginTextBlock(){
      if(lines.length && lines[lines.length-1]!==null)atBlockBoundary=true;
    },
    endTextBlock(){
      flushLine();
      if(lines.length && lines[lines.length-1]!==null)lines.push(null);
    },
    beginLine(){
      if(atBlockBoundary && lines.length && lines[lines.length-1]!==null)lines.push(null);
      atBlockBoundary=false;
      current=[];
    },
    onChar(utf,origin,font,size,quad,argb){
      if(current===null)current=[];
      let ch='';
      try {
        ch=typeof utf==='number'?String.fromCodePoint(utf):String(utf??'');
      } catch {return}
      if(!ch)return;
      const color=colorHex(argb);
      const last=current[current.length-1];
      if(last && last.color===color)last.text+=ch;
      else current.push({color,text:ch});
    },
    endLine(){flushLine()}
  });
  flushLine();
  while(lines.length && lines[lines.length-1]===null)lines.pop();
  let decorated='',walkPlain='';
  for(let i=0;i<lines.length;i++){
    if(i>0){const sep=lines[i]===null||lines[i-1]===null?'\n':'\n';decorated+=sep;walkPlain+=sep}
    const line=lines[i];
    if(!line)continue;
    for(const run of line){
      walkPlain+=run.text;
      const color=run.color;
      // Black matches the default Markdown text color and needs no markup.
      if(color==='#000000'){decorated+=escapeHtml(run.text);continue}
      const label=colorLabel(color);
      const attrs='style="color:'+color+(label==='흰색'?';background-color:#303030':'')+'" data-pdf-color="'+color+'" data-pdf-color-name="'+label+'"';
      decorated+='<span '+attrs+'>'+escapeHtml(run.text)+'</span>';
      const nonspace=normalize(run.text).length;
      if(nonspace){counts[color]=(counts[color]||0)+nonspace;coloredChars+=nonspace}
    }
  }
  const original=normalize(originalPlainText||'');
  const reconstructed=normalize(walkPlain);
  // Colorized text must not replace searchable text unless no characters were
  // dropped/reordered. Fail closed and keep the original exact plain text.
  const safe=original===reconstructed;
  return {
    markdown:safe?decorated.trim():originalPlainText,
    safe,
    colors: safe?counts:{},
    coloredChars:safe?coloredChars:0,
    message:safe?'':'원본 텍스트와 색상 추출 텍스트의 문자 순서가 달라 색상 표시를 생략했습니다.'
  };
}
