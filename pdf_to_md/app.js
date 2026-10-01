import * as pdfjsLib from 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs';
pdfjsLib.GlobalWorkerOptions.workerSrc='https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';

const $=id=>document.getElementById(id);
const input=$('file'),drop=$('drop'),convertBtn=$('convert'),downloadBtn=$('download'),status=$('status'),statusText=$('statusText'),progress=$('progress'),preview=$('preview'),thumb=$('thumb'),mdPreview=$('mdPreview'),summary=$('summary');
let selectedFile=null,resultBlob=null,resultUrl=null,previewUrl=null;

const bytes=n=>{const u=['B','KB','MB','GB'];let i=0,v=n;while(v>=1024&&i<u.length-1){v/=1024;i++}return `${v.toFixed(i?1:0)} ${u[i]}`};
const safeBase=n=>n.replace(/\.pdf$/i,'').replace(/[\\/:*?"<>|]+/g,'_').trim()||'document';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const clean=s=>s.replace(/\u0000/g,'').replace(/[ \t]+\n/g,'\n').replace(/\n{4,}/g,'\n\n\n').trim();
const canvasBlob=c=>new Promise((res,rej)=>c.toBlob(b=>b?res(b):rej(new Error('이미지 변환 실패')),'image/png'));

function setFile(file){
  if(!file||!file.name.toLowerCase().endsWith('.pdf')){alert('PDF 파일을 선택해 주세요.');return}
  selectedFile=file; resultBlob=null; downloadBtn.disabled=true; preview.classList.remove('show');
  $('dropTitle').textContent=file.name; $('fileInfo').textContent=`${file.name} · ${bytes(file.size)}`; $('fileInfo').classList.add('show'); convertBtn.disabled=false;
}
input.addEventListener('change',()=>setFile(input.files?.[0]));
['dragenter','dragover'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('drag')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('drag')}));
drop.addEventListener('drop',e=>setFile(e.dataTransfer?.files?.[0]));

function syncFeatureUI(){
  const v=$('extractVisuals').checked,t=$('reconstructTables').checked,c=$('cropRegions').checked;
  $('extractVisuals').closest('.feature').classList.toggle('enabled',v);
  $('reconstructTables').closest('.feature').classList.toggle('enabled',t);
  $('cropMarginWrap').classList.toggle('disabled',!c);
  const enabled=['기본 변환']; if(v)enabled.push('개별 이미지'); if(v&&c)enabled.push('주변 crop'); if(t)enabled.push('표 재구성');
  $('modeHint').innerHTML=`<b>현재:</b> ${enabled.join(' + ')}`;
}
['extractVisuals','reconstructTables','cropRegions'].forEach(id=>$(id).addEventListener('change',syncFeatureUI));
syncFeatureUI();

function itemRows(items){
  const ts=items.filter(i=>typeof i.str==='string'&&i.str.trim()).map(i=>({str:i.str.trim(),x:i.transform?.[4]??0,y:i.transform?.[5]??0,w:i.width??0,h:Math.max(1,i.height??Math.abs(i.transform?.[3]??0))}));
  const rows=[];
  for(const t of ts){let r=rows.find(x=>Math.abs(x.y-t.y)<=Math.max(3.2,t.h*.22));if(!r){r={y:t.y,items:[]};rows.push(r)}r.items.push(t)}
  rows.sort((a,b)=>b.y-a.y); rows.forEach(r=>r.items.sort((a,b)=>a.x-b.x)); return rows;
}
function textFromItems(items,layout){
  if(!layout)return clean(items.map(i=>i.str||'').join(' '));
  return clean(itemRows(items).map(r=>{let s='',end=null;for(const t of r.items){if(end!==null&&t.x-end>Math.max(2.2,t.h*.18))s+=' ';s+=t.str;end=t.x+t.w}return s.replace(/\s+/g,' ').trim()}).filter(Boolean).join('\n'));
}
function header(file,pages,scale,features){
  return `---\nsource_file: "${file.name.replace(/"/g,'\\"')}"\npages: ${pages}\nrender_scale: ${scale}\ngenerated_at: "${new Date().toISOString()}"\nformat: "multimodal-ai-markdown"\nfeatures:\n  visual_extraction: ${features.visuals}\n  region_crops: ${features.regions}\n  table_reconstruction: ${features.tables}\n---\n\n# ${safeBase(file.name)}\n\n> AI 입력용 변환 문서입니다. 원본 페이지 이미지는 항상 보존되며, 선택한 기능에 따라 개별 이미지·주변 영역·표 crop·Markdown 표가 추가됩니다.\n\n`;
}

async function resolveImage(page,id){try{if(page.objs?.has?.(id))return page.objs.get(id);if(page.commonObjs?.has?.(id))return page.commonObjs.get(id)}catch(e){console.warn('image lookup failed',id,e)}return null}
function dims(obj){if(!obj)return null;const s=obj.bitmap||obj;return {width:s.width||obj.width||0,height:s.height||obj.height||0}}
async function imageToBlob(obj){
  if(!obj)return null;const src=obj.bitmap||obj,{width,height}=dims(obj)||{};if(!width||!height)return null;
  const c=document.createElement('canvas');c.width=width;c.height=height;const ctx=c.getContext('2d');
  try{
    if(typeof ImageBitmap!=='undefined'&&src instanceof ImageBitmap)ctx.drawImage(src,0,0,width,height);
    else if((typeof HTMLImageElement!=='undefined'&&src instanceof HTMLImageElement)||(typeof HTMLCanvasElement!=='undefined'&&src instanceof HTMLCanvasElement)||(typeof OffscreenCanvas!=='undefined'&&src instanceof OffscreenCanvas))ctx.drawImage(src,0,0,width,height);
    else if(obj.bitmap?.width)ctx.drawImage(obj.bitmap,0,0,width,height);
    else if(obj.data){
      const d=obj.data;let rgba;
      if(d.length===width*height*4)rgba=new Uint8ClampedArray(d.buffer||d,d.byteOffset||0,width*height*4);
      else if(d.length===width*height*3){rgba=new Uint8ClampedArray(width*height*4);for(let i=0,j=0;i<d.length;i+=3,j+=4){rgba[j]=d[i];rgba[j+1]=d[i+1];rgba[j+2]=d[i+2];rgba[j+3]=255}}
      else if(d.length===width*height){rgba=new Uint8ClampedArray(width*height*4);for(let i=0,j=0;i<d.length;i++,j+=4){rgba[j]=rgba[j+1]=rgba[j+2]=d[i];rgba[j+3]=255}}
      else return null;
      ctx.putImageData(new ImageData(rgba,width,height),0,0);
    } else return null;
    return await canvasBlob(c);
  }catch(e){console.warn('image conversion failed',e);return null}
}
function bbox(matrix,viewport){
  if(!matrix)return null;try{const tx=pdfjsLib.Util.transform(viewport.transform,matrix),pts=[[0,0],[1,0],[0,1],[1,1]].map(p=>pdfjsLib.Util.applyTransform(p,tx)),xs=pts.map(p=>p[0]),ys=pts.map(p=>p[1]);return{x:Math.min(...xs),y:Math.min(...ys),w:Math.max(...xs)-Math.min(...xs),h:Math.max(...ys)-Math.min(...ys)}}catch{return null}
}
async function cropCanvas(source,b,scale,marginRatio=0){
  if(!b||b.w<1||b.h<1)return null;const x=b.x*scale,y=b.y*scale,w=b.w*scale,h=b.h*scale,m=Math.max(w,h)*marginRatio,W=source.width,H=source.height;
  const sx=Math.floor(clamp(x-m,0,W-1)),sy=Math.floor(clamp(y-m,0,H-1)),ex=Math.ceil(clamp(x+w+m,1,W)),ey=Math.ceil(clamp(y+h+m,1,H)),sw=ex-sx,sh=ey-sy;
  if(sw<24||sh<24)return null;const c=document.createElement('canvas');c.width=sw;c.height=sh;c.getContext('2d').drawImage(source,sx,sy,sw,sh,0,0,sw,sh);return{blob:await canvasBlob(c),pixel_box:{x:sx,y:sy,w:sw,h:sh}}
}
async function extractVisuals(page,pageCanvas,pageNo,scale,minPx,makeRegions,margin,figFolder,regFolder){
  const ops=await page.getOperatorList(),vp=page.getViewport({scale:1}),out=[],seen=new Set();let ctm=[1,0,0,1,0,0],stack=[];
  for(let i=0;i<ops.fnArray.length;i++){
    const fn=ops.fnArray[i],args=ops.argsArray[i]||[];
    if(fn===pdfjsLib.OPS.save){stack.push(ctm.slice());continue} if(fn===pdfjsLib.OPS.restore){ctm=stack.pop()||[1,0,0,1,0,0];continue} if(fn===pdfjsLib.OPS.transform){ctm=pdfjsLib.Util.transform(ctm,args);continue}
    const xobj=fn===pdfjsLib.OPS.paintImageXObject||fn===pdfjsLib.OPS.paintJpegXObject,inline=fn===pdfjsLib.OPS.paintInlineImageXObject;if(!xobj&&!inline)continue;
    const id=xobj?args[0]:`inline_${i}`,key=`${id}_${ctm.map(v=>Math.round(v*10)/10).join('_')}`;if(seen.has(key))continue;seen.add(key);
    const obj=inline?args[0]:await resolveImage(page,id);if(!obj)continue;const d=dims(obj);if(!d||d.width<minPx||d.height<minPx||d.width*d.height<minPx*minPx*1.5)continue;
    const b=bbox(ctm,vp);if(b&&(b.w<18||b.h<18))continue;const n=out.length+1,base=`page_${String(pageNo).padStart(3,'0')}_fig_${String(n).padStart(2,'0')}`;
    let raw=null,region=null,regionBox=null;const rb=await imageToBlob(obj);if(rb){raw=`figures/${base}.png`;figFolder.file(`${base}.png`,rb)}
    if(makeRegions&&b){const cr=await cropCanvas(pageCanvas,b,scale,margin);if(cr){region=`regions/${base}_region.png`;regFolder.file(`${base}_region.png`,cr.blob);regionBox=cr.pixel_box}}
    if(!raw&&!region)continue;out.push({object_id:String(id),raw_image:raw,region_image:region,source_width:d.width,source_height:d.height,bbox:b?{x:+b.x.toFixed(2),y:+b.y.toFixed(2),w:+b.w.toFixed(2),h:+b.h.toFixed(2)}:null,region_pixel_box:regionBox});
  }
  out.sort((a,b)=>(a.bbox?.y??99999)-(b.bbox?.y??99999)||(a.bbox?.x??0)-(b.bbox?.x??0));out.forEach((v,i)=>v.reading_order=i+1);return out;
}

function rowCells(row,sensitivity){
  if(!row.items.length)return [];
  const hs=row.items.map(i=>i.h).sort((a,b)=>a-b),mh=hs[Math.floor(hs.length/2)]||10;
  const gapBase=sensitivity==='strict'?Math.max(42,mh*3.6):sensitivity==='loose'?Math.max(22,mh*2.0):Math.max(30,mh*2.7);
  const cells=[];let cur=[],end=null;
  for(const it of row.items){const gap=end===null?0:it.x-end;if(cur.length&&gap>gapBase){cells.push(cur);cur=[]}cur.push(it);end=it.x+it.w}
  if(cur.length)cells.push(cur);
  return cells.map(c=>({text:c.map(x=>x.str).join(' ').replace(/\s+/g,' ').trim(),x:Math.min(...c.map(x=>x.x)),end:Math.max(...c.map(x=>x.x+x.w)),y:row.y,h:Math.max(...c.map(x=>x.h))})).filter(c=>c.text);
}
function columnSimilarity(a,b,tol){
  if(a.length!==b.length)return false;let hits=0;for(let i=0;i<a.length;i++)if(Math.abs(a[i].x-b[i].x)<=tol)hits++;return hits>=Math.max(2,a.length-1);
}
function detectTables(items,pageWidth,pageHeight,sensitivity='balanced'){
  const rows=itemRows(items).map(r=>({...r,cells:rowCells(r,sensitivity)}));
  const minRows=sensitivity==='strict'?3:2,tol=sensitivity==='loose'?28:sensitivity==='strict'?14:20,maxGap=sensitivity==='loose'?34:26;
  const candidates=[];let group=[];
  const flush=()=>{if(group.length>=minRows){const counts=group.map(r=>r.cells.length),cols=Math.round(counts.reduce((a,b)=>a+b,0)/counts.length);if(cols>=2&&cols<=8){const xs=group.flatMap(r=>r.cells.map(c=>c.x)),ends=group.flatMap(r=>r.cells.map(c=>c.end)),top=Math.max(...group.map(r=>r.y+r.items.reduce((m,i)=>Math.max(m,i.h),0))),bottom=Math.min(...group.map(r=>r.y-r.items.reduce((m,i)=>Math.max(m,i.h),0))),left=Math.min(...xs),right=Math.max(...ends),w=right-left,h=top-bottom;if(w>pageWidth*.28&&h>12)candidates.push({rows:group.slice(),bbox:{x:left,y:pageHeight-top,w,h},columns:cols})}}group=[]};
  for(const r of rows){
    if(r.cells.length<2||r.cells.length>8){flush();continue}
    if(!group.length){group=[r];continue}
    const prev=group[group.length-1],vertical=Math.abs(prev.y-r.y);if(vertical>maxGap||!columnSimilarity(prev.cells,r.cells,tol)){flush();group=[r]}else group.push(r);
  }flush();
  return candidates.filter((t,i,arr)=>!arr.slice(0,i).some(p=>Math.abs(p.bbox.x-t.bbox.x)<8&&Math.abs(p.bbox.y-t.bbox.y)<8&&Math.abs(p.bbox.w-t.bbox.w)<12&&Math.abs(p.bbox.h-t.bbox.h)<12));
}
function escCell(s){return (s||'').replace(/\|/g,'\\|').replace(/\n/g,' ').trim()||' '}
function tableToMarkdown(t){
  const cols=Math.max(...t.rows.map(r=>r.cells.length));const normalized=t.rows.map(r=>Array.from({length:cols},(_,i)=>escCell(r.cells[i]?.text||'')));
  const header=normalized[0],body=normalized.slice(1);let md=`| ${header.join(' | ')} |\n| ${header.map(()=> '---').join(' | ')} |\n`;for(const r of body)md+=`| ${r.join(' | ')} |\n`;return md;
}
async function extractTables(textItems,pageCanvas,pageNo,scale,sensitivity,folder,pageWidth,pageHeight){
  const detected=detectTables(textItems,pageWidth,pageHeight,sensitivity),out=[];
  for(let i=0;i<detected.length;i++){
    const t=detected[i],base=`page_${String(pageNo).padStart(3,'0')}_table_${String(i+1).padStart(2,'0')}`,cr=await cropCanvas(pageCanvas,t.bbox,scale,.025);let image=null,pixel=null;
    if(cr){image=`tables/${base}.png`;folder.file(`${base}.png`,cr.blob);pixel=cr.pixel_box}
    out.push({reading_order:i+1,image,bbox:{x:+t.bbox.x.toFixed(2),y:+t.bbox.y.toFixed(2),w:+t.bbox.w.toFixed(2),h:+t.bbox.h.toFixed(2)},pixel_box:pixel,markdown:tableToMarkdown(t),rows:t.rows.length,columns:t.columns});
  }
  return out;
}

async function convert(){
  if(!selectedFile)return;convertBtn.disabled=true;downloadBtn.disabled=true;status.classList.add('show');progress.style.width='2%';statusText.textContent='PDF를 여는 중…';
  try{
    const features={visuals:$('extractVisuals').checked,regions:$('extractVisuals').checked&&$('cropRegions').checked,tables:$('reconstructTables').checked};
    const pdf=await pdfjsLib.getDocument({data:await selectedFile.arrayBuffer()}).promise,scale=Number($('scale').value),layout=$('layoutText').checked,zip=new JSZip(),pages=zip.folder('pages');
    const figs=features.visuals?zip.folder('figures'):null,regs=features.regions?zip.folder('regions'):null,tablesFolder=features.tables?zip.folder('tables'):null;
    const minPx=Number($('minFigure').value),margin=Number($('cropMargin').value),sensitivity=$('tableSensitivity').value;
    let md=header(selectedFile,pdf.numPages,scale,features),totalVisuals=0,totalTables=0;
    const manifest={schema:'multimodal-ai-markdown',source_file:selectedFile.name,page_count:pdf.numPages,render_scale:scale,features,generated_at:new Date().toISOString(),pages:[]};
    if(previewUrl){URL.revokeObjectURL(previewUrl);previewUrl=null}
    for(let n=1;n<=pdf.numPages;n++){
      progress.style.width=`${(((n-1)/pdf.numPages)*82+5).toFixed(1)}%`;statusText.textContent=`${n}/${pdf.numPages} 페이지 처리 중…`;
      const page=await pdf.getPage(n),vp=page.getViewport({scale}),vp1=page.getViewport({scale:1}),canvas=document.createElement('canvas'),ctx=canvas.getContext('2d',{alpha:false});canvas.width=Math.ceil(vp.width);canvas.height=Math.ceil(vp.height);ctx.fillStyle='#fff';ctx.fillRect(0,0,canvas.width,canvas.height);await page.render({canvasContext:ctx,viewport:vp}).promise;
      const pageBlob=await canvasBlob(canvas),pageName=`page_${String(n).padStart(3,'0')}.png`;pages.file(pageName,pageBlob);if(n===1)previewUrl=URL.createObjectURL(pageBlob);
      const tc=await page.getTextContent({includeMarkedContent:true}),textItems=tc.items||[],text=textFromItems(textItems,layout);
      let visuals=[],tables=[];
      if(features.visuals){try{visuals=await extractVisuals(page,canvas,n,scale,minPx,features.regions,margin,figs,regs)}catch(e){console.warn('visual extraction failed',n,e)}}
      if(features.tables){try{tables=await extractTables(textItems,canvas,n,scale,sensitivity,tablesFolder,vp1.width,vp1.height)}catch(e){console.warn('table reconstruction failed',n,e)}}
      totalVisuals+=visuals.length;totalTables+=tables.length;
      md+=`<!-- PAGE ${n} START -->\n\n## Page ${n}\n\n![Page ${n}](pages/${pageName})\n\n`;
      if(visuals.length){md+='### Extracted visuals\n\n';for(const v of visuals){md+=`#### Visual ${v.reading_order}\n\n`;if(v.region_image)md+=`![Page ${n} visual region ${v.reading_order}](${v.region_image})\n\n`;if(v.raw_image)md+=`![Page ${n} embedded image ${v.reading_order}](${v.raw_image})\n\n`;md+=`- source_size: ${v.source_width}×${v.source_height}\n`;if(v.bbox)md+=`- page_bbox: x=${v.bbox.x}, y=${v.bbox.y}, w=${v.bbox.w}, h=${v.bbox.h}\n`;md+='\n'}}
      if(tables.length){md+='### Reconstructed tables\n\n';for(const t of tables){md+=`#### Table ${t.reading_order}\n\n`;if(t.image)md+=`![Page ${n} table ${t.reading_order}](${t.image})\n\n`;md+=`> Heuristic reconstruction from PDF text coordinates. Check the table image above when exact layout matters.\n\n${t.markdown}\n`;}}
      md+=`### Extracted text\n\n${text?text:'_[No selectable text detected on this page. Use the page image above.]_'}\n\n<!-- PAGE ${n} END -->\n\n---\n\n`;
      manifest.pages.push({page:n,image:`pages/${pageName}`,text_detected:Boolean(text),text_chars:text.length,width_px:canvas.width,height_px:canvas.height,visuals,tables:tables.map(t=>({...t,markdown:undefined}))});page.cleanup();await new Promise(r=>setTimeout(r,0));
    }
    zip.file('AI_READY.md',md);zip.file('manifest.json',JSON.stringify(manifest,null,2));if($('includePdf').checked)zip.file(selectedFile.name,selectedFile);
    progress.style.width='90%';statusText.textContent='ZIP을 만드는 중…';resultBlob=await zip.generateAsync({type:'blob',compression:'DEFLATE',compressionOptions:{level:6}},m=>progress.style.width=`${Math.min(100,90+m.percent*.1).toFixed(1)}%`);
    if(resultUrl)URL.revokeObjectURL(resultUrl);resultUrl=URL.createObjectURL(resultBlob);downloadBtn.disabled=false;progress.style.width='100%';
    const extras=[];if(features.visuals)extras.push(`visual ${totalVisuals}개`);if(features.tables)extras.push(`table ${totalTables}개`);statusText.textContent=`완료 · ${pdf.numPages}페이지${extras.length?' · '+extras.join(' · '):''} · ZIP ${bytes(resultBlob.size)}`;
    if(previewUrl)thumb.src=previewUrl;mdPreview.textContent=md.slice(0,10000)+(md.length>10000?'\n\n…':'');summary.textContent=`${pdf.numPages} pages${totalVisuals?` · ${totalVisuals} visuals`:''}${totalTables?` · ${totalTables} tables`:''} · ${bytes(resultBlob.size)}`;preview.classList.add('show');
  }catch(e){console.error(e);statusText.textContent=`변환 실패: ${e?.message||e}`;alert(`변환 중 오류가 발생했습니다.\n${e?.message||e}`)}finally{convertBtn.disabled=false}
}
convertBtn.addEventListener('click',convert);
downloadBtn.addEventListener('click',()=>{if(!resultBlob||!resultUrl||!selectedFile)return;const a=document.createElement('a');a.href=resultUrl;a.download=`${safeBase(selectedFile.name)}_AI_READY.zip`;document.body.appendChild(a);a.click();a.remove()});
