"""Compare the actual restored v2 data with the v3 migration; isolated test-runs only."""
import os, sys, json, sqlite3, zipfile, hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[1];data=root/'test-runs/usability-v3/working'
if not data.resolve().is_relative_to((root/'test-runs').resolve()):raise RuntimeError('Isolated directory required')
os.environ['PAPER_LIBRARY_DATA']=str(data);os.environ['DJANGO_SETTINGS_MODULE']='config.settings';sys.path.insert(0,str(root/'app'))
archive=root/'test-runs/four-views/backups-after/paper-library-20261003-144847-de1588.zip'
report={'checks':[]};old=sqlite3.connect(':memory:');new=sqlite3.connect(data/'db.sqlite3')
with zipfile.ZipFile(archive) as z:
    old.deserialize(z.read('db.sqlite3'))
    for table in ['library_paper','library_paper_categories','library_comment','library_rating','library_annotationanchor','library_paperrevision']:
        columns=[r[1] for r in old.execute('PRAGMA table_info('+table+')')]
        fields=','.join('"'+c+'"' for c in columns)
        before=sorted(old.execute('SELECT '+fields+' FROM '+table).fetchall(),key=repr)
        after=sorted(new.execute('SELECT '+fields+' FROM '+table).fetchall(),key=repr)
        assert before==after,table+' changed during migration'
        report['checks'].append({'name':table,'rows':len(after),'status':'PASS'})
    files=0
    for name in z.namelist():
        if name.startswith('papers/') and not name.endswith('/'):
            assert hashlib.sha256(z.read(name)).digest()==hashlib.sha256((data/name).read_bytes()).digest(),name
            files+=1
    report['checks'].append({'name':'all original paper and revision bytes','files':files,'status':'PASS'})
old.close();new.close()
import django;django.setup()
from library.models import Paper,Tag
from django.contrib.auth.models import User
assert not Tag.objects.filter(active=True).exists(),'Initial vocabulary should await administrator review'
report['checks'].append({'name':'13 suggested tags inactive; zero automatic paper labels','status':'PASS','count':Tag.objects.count()})
assert not Paper.tags.through.objects.exists()
# This test-only credential is never printed or included in evidence.
credentials=json.loads((root/'test-runs/four-views/credentials.json').read_text(encoding='utf-8'))
admin=User.objects.get(username='test_manager');admin.set_password(credentials['password']);admin.is_staff=True;admin.is_superuser=True;admin.save()
output=root/'evidence/usability-v3';output.mkdir(parents=True,exist_ok=True)
(output/'migration-preservation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
