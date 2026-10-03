"""Read/save only isolated test data to verify the real SQLite busy path."""
import http.cookies
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import launcher
data=ROOT/'test-runs'/'restored'
launcher.init_django(data)
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.utils import timezone
from library.models import Paper
user=User.objects.get(username='reader_a')
session=next(s for s in Session.objects.filter(expire_date__gt=timezone.now()) if s.get_decoded().get('_auth_user_id')==str(user.id))
paper=Paper.objects.get(trusted_original=True,profile='idaes-pair-v1')
base='http://127.0.0.1:8002'
authcookie=settings.SESSION_COOKIE_NAME+'='+session.session_key
with urllib.request.urlopen(urllib.request.Request(f'{base}/papers/{paper.id}/',headers={'Cookie':authcookie})) as response:
    html=response.read().decode();cookies=http.cookies.SimpleCookie(response.headers['Set-Cookie'])
token=re.search(r'data-csrf="([A-Za-z0-9]+)"',html)[1]
cookie=authcookie+'; '+settings.CSRF_COOKIE_NAME+'='+cookies[settings.CSRF_COOKIE_NAME].value
conn=sqlite3.connect(data/'db.sqlite3');conn.execute('BEGIN IMMEDIATE')
started=time.monotonic()
try:
    request=urllib.request.Request(f'{base}/api/papers/{paper.id}/ratings/importance/',data=b'{"value":3}',method='PUT',
       headers={'Cookie':cookie,'X-CSRFToken':token,'Content-Type':'application/json','Origin':base})
    try:urllib.request.urlopen(request,timeout=22)
    except urllib.error.HTTPError as exc:
        assert exc.code==503,exc.code
        message=json.loads(exc.read())['error'];assert '未保存' in message
    else:raise AssertionError('Expected a visible busy failure, not success.')
finally:conn.rollback();conn.close()
elapsed=time.monotonic()-started
assert elapsed>=14
with urllib.request.urlopen(urllib.request.Request(f'{base}/api/papers/{paper.id}/ratings/',headers={'Cookie':authcookie})) as response:
    result=json.load(response);assert result['importance']['mine']==3 and result['importance']['average']==4
(ROOT/'evidence'/'sqlite-busy.json').write_text(json.dumps({'status':'PASS','seconds':round(elapsed,2),'response':503,'saved_values_unchanged':True},indent=2),encoding='utf-8')
print('PASS SQLite busy timeout returns 503; saved scores remain unchanged.')
