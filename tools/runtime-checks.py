"""Verify running production boundary without creating any production user data."""
import contextlib
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
ROOT=Path(__file__).resolve().parents[1]
results=[]
def run(args):return subprocess.run([sys.executable,str(ROOT/'launcher.py'),*args],capture_output=True,text=True,encoding='utf-8',cwd=ROOT)
r=run(['start']);assert r.returncode==0 and '本应用已在运行' in r.stdout
results.append({'id':'A05 same application recognized','status':'PASS'})
r=run(['backup']);assert r.returncode!=0 and '应用正在运行' in r.stderr
results.append({'id':'F03 running backup refused by OS lock','status':'PASS'})
with socket.socket() as s:
    s.bind(('127.0.0.1',8010));s.listen()
    r=run(['start','--port','8010']);assert r.returncode!=0 and '被其他应用占用' in r.stderr
results.append({'id':'A05 foreign port left untouched','status':'PASS'})
try:urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8000/',headers={'Host':'unrecognized.invalid'}))
except urllib.error.HTTPError as exc:assert exc.code==400
else:raise AssertionError('Unknown host accepted')
results.append({'id':'A06 unknown Host rejected','status':'PASS'})
with urllib.request.urlopen('http://127.0.0.1:8000/login/') as response:
    text=response.read().decode();assert '登录论文库' in text and 'csrfmiddlewaretoken' in text
    assert 'no-store' in response.headers['Cache-Control']
    assert response.headers['X-Content-Type-Options']=='nosniff'
    assert 'script-src' in response.headers['Content-Security-Policy']
results.append({'id':'A04 real start on production directory and login boundary','status':'PASS'})
with contextlib.closing(sqlite3.connect(ROOT/'var'/'db.sqlite3')) as c:
    counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['auth_user','library_paper','library_rating','library_comment']}
assert counts=={'auth_user':0,'library_paper':2,'library_rating':0,'library_comment':0}
results.append({'id':'A07 no production test data','status':'PASS','counts':counts})
(ROOT/'evidence'/'runtime-checks.json').write_text(json.dumps({'time':time.strftime('%Y-%m-%d %H:%M:%S'),'checks':results},ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS production launch, host, port, stopped-backup requirement and clean data.')
