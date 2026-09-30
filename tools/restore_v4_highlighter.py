from pathlib import Path
p=Path('v4/app.js')
s=p.read_text()
bad=";downloadBlob(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}),`${safe(E.title.value)}_backup.json`)};"
if bad not in s: raise SystemExit('duplicate JSON tail not found')
s=s.replace(bad,';',1)
p.write_text(s)
print('Removed duplicated JSON export tail')
