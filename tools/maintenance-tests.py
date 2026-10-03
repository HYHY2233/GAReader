"""Isolated persistence, backup corruption, repeat-install and path tests."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import launcher
report={'time':time.strftime('%Y-%m-%d %H:%M:%S'),'checks':[]}
data=ROOT/'test-runs'/'integration'

def check(name,fn):
    try:
        detail=fn();report['checks'].append({'id':name,'status':'PASS','detail':detail});print('PASS '+name,flush=True)
    except Exception as exc:
        report['checks'].append({'id':name,'status':'FAIL','detail':str(exc)});print('FAIL '+name+': '+str(exc),flush=True)

def counts(directory):
    with contextlib.closing(sqlite3.connect(directory/'db.sqlite3')) as c:
        return {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['auth_user','library_paper','library_rating','library_comment']}

def repeat():
    old=counts(data);keyhash=launcher.sha(data/'local.json')
    with contextlib.closing(sqlite3.connect(data/'db.sqlite3')) as c:
        c.execute("UPDATE library_paper SET visible=0 WHERE profile='ammonia-pair-v2'");c.commit()
    result=subprocess.run([str(ROOT/'setup.cmd'),'--data-dir',str(data)],env={**os.environ,'PAPER_LIBRARY_NO_PAUSE':'1','PYTHONUTF8':'1'},capture_output=True,text=True)
    (ROOT/'evidence'/'repeat-setup.txt').write_text(result.stdout+result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stderr
    assert old==counts(data);assert keyhash==launcher.sha(data/'local.json')
    with contextlib.closing(sqlite3.connect(data/'db.sqlite3')) as c:
        assert c.execute("SELECT visible FROM library_paper WHERE profile='ammonia-pair-v2'").fetchone()[0]==0
        c.execute("UPDATE library_paper SET visible=1 WHERE profile='ammonia-pair-v2'");c.commit()
    assert old['library_rating']==4 and old['library_comment']>=2
    return old

archive=None
def backup_restore():
    global archive
    with launcher.exclusive(data):archive=launcher.backup_data(data,ROOT/'test-runs'/'verified-backups')
    before=launcher.sha(data/'db.sqlite3');target=ROOT/'test-runs'/'restored'
    launcher.restore_data(archive,target)
    assert counts(data)==counts(target);assert launcher.sha(data/'db.sqlite3')==before
    assert launcher.sha(data/'local.json')!=launcher.sha(target/'local.json')
    report['archive']=str(archive);report['restored']=str(target)
    with contextlib.closing(sqlite3.connect(target/'db.sqlite3')) as c:assert c.execute('SELECT COUNT(*) FROM django_session').fetchone()[0]==0
    return counts(target)

def bad_archives():
    badroot=ROOT/'test-runs'/'bad-backups';badroot.mkdir(exist_ok=True)
    variants=['missing','hash','traversal','symlink','case-duplicate','too-large']
    for variant in variants:
        bad=badroot/(variant+'.zip')
        with zipfile.ZipFile(archive) as src,zipfile.ZipFile(bad,'w',zipfile.ZIP_DEFLATED) as z:
            for info in src.infolist():
                if variant=='missing' and info.filename=='db.sqlite3':continue
                content=src.read(info.filename)
                if variant=='hash' and info.filename=='db.sqlite3':content=b'broken'
                z.writestr(info,content)
            if variant=='traversal':z.writestr('../escape.txt','x')
            if variant=='symlink':
                link=zipfile.ZipInfo('papers/link');link.create_system=3;link.external_attr=0o120777<<16;z.writestr(link,'/private')
            if variant=='case-duplicate':z.writestr('DB.SQLITE3','x')
        try:
            if variant=='too-large':
                with patch.object(launcher,'MAX_BACKUP',100):launcher.check_archive(bad)
            else:launcher.restore_data(bad,badroot/('restore-'+variant))
        except (RuntimeError,ValueError):pass
        else:raise AssertionError('bad archive accepted '+variant)
        assert not (badroot/('restore-'+variant)).exists()
    with patch.object(launcher.shutil,'disk_usage',return_value=type('Disk',(),{'free':1})()):
        try:
            with launcher.exclusive(data):launcher.backup_data(data,badroot/'full-disk')
        except RuntimeError:pass
        else:raise AssertionError('disk-full falsely succeeded')
    return variants+['disk-full']

def account_entry():
    target=ROOT/'test-runs'/'account-command'
    launcher.restore_data(archive,target)
    script='''import launcher,secrets
from unittest.mock import patch
password=secrets.token_urlsafe(24)
with patch('builtins.input',side_effect=['1','local_command_admin','本机测试']),patch('getpass.getpass',return_value=password):launcher.manage_account(launcher.ROOT/'test-runs'/'account-command')
from django.contrib.auth.models import User
u=User.objects.get(username='local_command_admin');assert u.is_superuser and u.check_password(password)
password2=secrets.token_urlsafe(24)
with patch('builtins.input',side_effect=['3','local_command_admin']),patch('getpass.getpass',return_value=password2):launcher.manage_account(launcher.ROOT/'test-runs'/'account-command')
u.refresh_from_db();assert u.check_password(password2) and not u.check_password(password)
print('PASS admin creation/reset without credential output')
'''
    r=subprocess.run([sys.executable,'-c',script],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    return 'Create/reset validated with mocked no-echo input in isolated database.'

def clean_production():
    c=counts(ROOT/'var')
    assert c=={'auth_user':0,'library_paper':2,'library_rating':0,'library_comment':0},c
    return c

check('A03 repeated setup preserves data/secret/hidden state',repeat)
check('F04 F05 stopped consistent backup and independent restore',backup_restore)
if archive:
    check('F06 malformed ZIP, disk-full and fresh-target safety',bad_archives)
    check('D10 local administrator creation/password reset',account_entry)
check('A07 production contains only two real papers and no test users',clean_production)
(ROOT/'evidence'/'maintenance-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
sys.exit(any(c['status']=='FAIL' for c in report['checks']))
