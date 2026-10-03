"""Read-only HTTP checks using an already-issued isolated test session.
No passwords are read, entered, printed or changed by this follow-up check.
"""
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import launcher
launcher.init_django(ROOT/'test-runs'/'restored')
from django.conf import settings
from django.contrib.sessions.models import Session
from django.contrib.auth.models import User
from library.models import Paper
from django.utils import timezone

user=User.objects.get(username='reader_a')
session=next(s for s in Session.objects.filter(expire_date__gt=timezone.now()) if s.get_decoded().get('_auth_user_id')==str(user.id))
base='http://127.0.0.1:8002'
def read(url):
    request=urllib.request.Request(base+url,headers={'Cookie':settings.SESSION_COOKIE_NAME+'='+session.session_key})
    with urllib.request.urlopen(request,timeout=15) as response:
        assert response.status==200 and response.url==base+url
        return response.read()
for paper in Paper.objects.filter(trusted_original=True):
    html=read(f'/papers/{paper.id}/').decode()
    expected=145 if paper.profile=='idaes-pair-v1' else 750
    assert html.count('<math ')==expected
    assert read(f'/papers/{paper.id}/files/original.pdf').startswith(b'%PDF-')
    assert read(f'/papers/{paper.id}/files/image-0.png').startswith(b'\x89PNG')
paper=Paper.objects.get(profile='idaes-pair-v1',trusted_original=True)
ratings=json.loads(read(f'/api/papers/{paper.id}/ratings/'))
assert ratings['interesting']['average']==4.5 and ratings['importance']['average']==4
assert ratings['interesting']['mine']==5 and ratings['importance']['mine']==3
comments=json.loads(read(f'/api/papers/{paper.id}/comments/'))
assert comments['count']>=2
report={'status':'PASS','time':time.strftime('%Y-%m-%d %H:%M:%S'),'base':base,
 'method':'Read-only actual HTTP after second normal start; previously issued test session; no password handling.',
 'checks':['restored session still authenticates after restart','both original papers and all MathML counts','PDF and protected image access','both score averages and own scores','comments and replies persisted'],
 'ratings':ratings,'comment_count':comments['count']}
(ROOT/'evidence'/'restart-restored.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS F07 second restored restart; real authenticated HTTP; no password handling.')
