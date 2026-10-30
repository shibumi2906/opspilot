from pathlib import Path
import hashlib,json,opspilot
root=Path(opspilot.__file__).parent
items={}
for source in Path('/work/src/opspilot').rglob('*.py'):
 relative=source.relative_to('/work/src/opspilot');actual=root/relative
 assert source.read_text()==actual.read_text(),str(relative)
 items[str(relative)]=hashlib.sha256(source.read_text().encode()).hexdigest()
for source in Path('/work/migrations').rglob('*.py'):
 actual=Path('/app/migrations')/source.relative_to('/work/migrations')
 assert source.read_text()==actual.read_text(),str(source)
Path('/reports/source-match.json').write_text(json.dumps({'matched':True,'application_files':len(items),'sources':items},indent=2)+'\n')
print('Runtime package and migration sources match',len(items))
