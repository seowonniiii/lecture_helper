from pathlib import Path

p = Path('v2/index.html')
s = p.read_text(encoding='utf-8')

css_marker = '/* iPad Pencil selection suppression */'
if css_marker not in s:
    css = r'''
/* iPad Pencil selection suppression */
.pagewrap,.pagewrap *{
  -webkit-user-select:none!important;
  user-select:none!important;
  -webkit-touch-callout:none!important;
}
.pagewrap canvas{-webkit-tap-highlight-color:transparent!important;}
'''
    s = s.replace('</style>', css + '\n</style>', 1)

js_marker = '// iPad Pencil selection suppression'
if js_marker not in s:
    js = r'''
// iPad Pencil selection suppression
for(const type of ['selectstart','dragstart']){
  E.pageWrap.addEventListener(type,e=>e.preventDefault());
}
E.pageWrap.addEventListener('contextmenu',e=>e.preventDefault());
'''
    s = s.replace('</script>', js + '\n</script>', 1)

p.write_text(s, encoding='utf-8')
