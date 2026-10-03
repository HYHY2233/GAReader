"""Local install, service and offline maintenance. Never enables LAN access."""
from __future__ import annotations
import argparse
import contextlib
import getpass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

ROOT=Path(__file__).resolve().parent
VENV=ROOT/'.venv'
PYTHON=VENV/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
MAX_BACKUP=5*1024**3

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda:f.read(1024**2),b''):h.update(part)
    return h.hexdigest()

def configure(data):
    data.mkdir(parents=True,exist_ok=True)
    config=data/'local.json'
    if not config.exists():
        with config.open('x',encoding='utf-8') as f:
            json.dump({'secret_key':secrets.token_urlsafe(64),'instance_id':uuid.uuid4().hex},f)
        try:config.chmod(0o600)
        except OSError:pass
    for name in ['papers','staging','logs']:(data/name).mkdir(exist_ok=True)

def init_django(data):
    os.environ['PAPER_LIBRARY_DATA']=str(data)
    os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
    sys.path.insert(0,str(ROOT/'app'))
    import django
    django.setup()

@contextlib.contextmanager
def exclusive(data):
    import portalocker
    data.mkdir(parents=True,exist_ok=True)
    try:
        lock=portalocker.Lock(str(data/'.instance.lock'),mode='a+b',timeout=0)
        lock.acquire()
    except portalocker.exceptions.LockException as exc:
        raise RuntimeError('应用正在运行或其他维护正在进行。请先正常停止应用；没有执行备份或修改。') from exc
    try:yield
    finally:lock.release()

def verify_data(data):
    db=data/'db.sqlite3'
    if not db.is_file():raise RuntimeError('缺少数据库。')
    with contextlib.closing(sqlite3.connect(db)) as conn:
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('数据库完整性检查失败。')
        if conn.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('数据库外键不一致。')
        for pk,raw_hash,content_hash,has_pdf,has_map in conn.execute('SELECT id,raw_hash,content_hash,has_pdf,has_map FROM library_paper'):
            folder=data/'papers'/str(uuid.UUID(pk))
            for name in ['original.html','body.html','nav.json','validation.json']:
                if not (folder/name).is_file():raise RuntimeError('论文文件引用缺失：'+name)
            current=None
            columns={row[1] for row in conn.execute('PRAGMA table_info(library_paper)')}
            if 'current_revision_id' in columns:
                current=conn.execute('SELECT current_revision_id FROM library_paper WHERE id=?',(pk,)).fetchone()[0]
            if sha(folder/'original.html')!=raw_hash or not current and sha(folder/'body.html')!=content_hash:raise RuntimeError('论文内容哈希不符。')
            if has_pdf and not (folder/'original.pdf').is_file():raise RuntimeError('PDF 缺失。')
            if has_map and not (folder/'paragraph_map.json').is_file():raise RuntimeError('映射缺失。')
            import re
            for i in re.findall(r'@@IMAGE:(\d+)@@',(folder/'body.html').read_text(encoding='utf-8')):
                if len(list(folder.glob('image-'+i+'.*')))!=1:raise RuntimeError('图片缺失。')
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='library_paperrevision'").fetchone():
            for rid,pid,content_hash,pdf_sha,manifest_sha in conn.execute('SELECT id,paper_id,content_hash,pdf_sha256,manifest_sha256 FROM library_paperrevision'):
                folder=data/'papers'/str(uuid.UUID(pid))/'revisions'/str(uuid.UUID(rid))
                for name in ['body.html','original.html','reader.html','nav.json','representation-manifest.json','alignment.json']:
                    if not (folder/name).is_file():raise RuntimeError('内容快照文件缺失：'+name)
                if sha(folder/'body.html')!=content_hash or sha(folder/'representation-manifest.json')!=manifest_sha:raise RuntimeError('内容快照哈希不符。')
                manifest=json.loads((folder/'representation-manifest.json').read_text(encoding='utf-8'))
                for name,expected in manifest.get('assets',{}).items():
                    if Path(name).name!=name or not (folder/name).is_file() or sha(folder/name)!=expected:raise RuntimeError('快照资产不一致：'+name)
                for name,field in [('original.html','raw_hash'),('reader.html','reader_sha256'),('pdf-index.json','pdf_index_sha256')]:
                    if manifest.get(field) and sha(folder/name)!=manifest[field]:raise RuntimeError('快照资产哈希不符：'+name)
                if pdf_sha and (not (folder/'original.pdf').exists() or sha(folder/'original.pdf')!=pdf_sha):raise RuntimeError('快照 PDF 哈希不符。')
                for i in re.findall(r'@@IMAGE:(\d+)@@',(folder/'body.html').read_text(encoding='utf-8')):
                    if len(list(folder.glob('image-'+i+'.*')))!=1:raise RuntimeError('快照图片缺失。')
            bad=conn.execute('SELECT COUNT(*) FROM library_paper p LEFT JOIN library_paperrevision r ON p.current_revision_id=r.id WHERE p.current_revision_id IS NOT NULL AND (r.id IS NULL OR r.paper_id!=p.id OR r.content_hash!=p.content_hash)').fetchone()[0]
            if bad:raise RuntimeError('当前修订关联不一致。')
            bad=conn.execute('SELECT COUNT(*) FROM library_annotationanchor a JOIN library_comment c ON c.id=a.comment_id JOIN library_paperrevision r ON r.id=a.revision_id WHERE c.paper_id!=r.paper_id OR c.parent_id IS NOT NULL').fetchone()[0]
            if bad:raise RuntimeError('批注所属文章／修订不一致。')

def backup_data(data, output=None):
    # Caller holds the same OS file lock as the WSGI service.
    verify_data(data)
    out=Path(output).resolve() if output else ROOT/'backups'
    if out.is_relative_to(data.resolve()):raise RuntimeError('备份目标必须位于数据目录之外。')
    out.mkdir(parents=True,exist_ok=True)
    name='paper-library-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.zip'
    destination=out/name
    with tempfile.TemporaryDirectory(prefix='backup-',dir=out) as td:
        work=Path(td); snapshot=work/'db.sqlite3'
        with contextlib.closing(sqlite3.connect(data/'db.sqlite3')) as source, contextlib.closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)
            schema=[{'app':app,'migration':name} for app,name in target.execute('SELECT app,name FROM django_migrations ORDER BY app,name')]
        entries=[('db.sqlite3',snapshot)]
        for p in (data/'papers').rglob('*'):
            if p.is_symlink():raise RuntimeError('数据目录含符号链接，停止备份。')
            if p.is_file():entries.append((p.relative_to(data).as_posix(),p))
        manifest={'format':'paper-library-backup-v1','created_at':time.strftime('%Y-%m-%dT%H:%M:%S'),'schema':schema,
                  'configuration':'Loopback only. New secret and session invalidation on restore.',
                  'versions':(ROOT/'requirements.lock').read_text(encoding='utf-8-sig'),
                  'files':[{'path':name,'bytes':p.stat().st_size,'sha256':sha(p)} for name,p in entries]}
        required=sum(x['bytes'] for x in manifest['files'])
        if required>MAX_BACKUP or shutil.disk_usage(out).free<required*2+10*1024**2:raise RuntimeError('备份超过限制或磁盘空间不足。')
        temporary=work/'backup.zip'
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            for name,p in entries:z.write(p,name)
        check_archive(temporary)
        temporary.replace(destination)
    return destination

def check_archive(path):
    with zipfile.ZipFile(path) as z:
        info=z.infolist()
        if len(info)>25000 or sum(i.file_size for i in info)>MAX_BACKUP:raise RuntimeError('备份超限。')
        names=[i.filename for i in info]
        if len(names)!=len(set(names)) or len(names)!=len({n.casefold() for n in names}):raise RuntimeError('备份路径重复。')
        for i in info:
            p=PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or '\\' in i.filename or ':' in i.filename or not p.parts or any(x.endswith(('.', ' ')) or x.upper().split('.')[0] in {'CON','PRN','AUX','NUL',*[f'COM{j}' for j in range(1,10)],*[f'LPT{j}' for j in range(1,10)]} for x in p.parts):raise RuntimeError('备份路径不安全。')
            if (i.external_attr>>16)&0o170000==0o120000:raise RuntimeError('备份含符号链接。')
            if i.is_dir():raise RuntimeError('备份不应含额外目录条目。')
        if 'manifest.json' not in names or z.getinfo('manifest.json').file_size>10*1024**2:raise RuntimeError('清单缺失或过大。')
        manifest=json.loads(z.read('manifest.json'))
        if manifest.get('format')!='paper-library-backup-v1':raise RuntimeError('备份格式不符。')
        records=manifest.get('files',[])
        if len(records)!=len({x['path'] for x in records}) or set(names)!={'manifest.json',*(x['path'] for x in records)}:raise RuntimeError('备份文件与清单不一致。')
        for item in records:
            name=item['path']
            if name!='db.sqlite3' and not name.startswith('papers/'):raise RuntimeError('备份含不允许的文件。')
            h=hashlib.sha256();size=0
            with z.open(name) as f:
                for block in iter(lambda:f.read(1024**2),b''):h.update(block);size+=len(block)
            if size!=item['bytes'] or h.hexdigest()!=item['sha256']:raise RuntimeError('备份哈希／大小校验失败：'+name)
        return manifest

def restore_data(archive,dest):
    check_archive(archive)
    if dest.exists():raise RuntimeError('恢复只允许新目录，现有目录不会被覆盖。请指定新的 --target。')
    dest.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(dest.parent).free<sum(x['bytes'] for x in check_archive(archive)['files'])*2+10*1024**2:raise RuntimeError('恢复空间不足。')
    with tempfile.TemporaryDirectory(prefix='restore-',dir=dest.parent) as td:
        work=Path(td)/'data';work.mkdir()
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name=='manifest.json':continue
                target=work.joinpath(*PurePosixPath(name).parts)
                if not target.resolve().is_relative_to(work.resolve()):raise RuntimeError('恢复路径越界。')
                target.parent.mkdir(parents=True,exist_ok=True)
                with z.open(name) as src,target.open('xb') as f:shutil.copyfileobj(src,f)
        verify_data(work)
        with contextlib.closing(sqlite3.connect(work/'db.sqlite3')) as conn:
            conn.execute('DELETE FROM django_session');conn.commit()
        configure(work)
        work.rename(dest)
    return dest

def import_references():
    from django.conf import settings
    from library.article import load_article
    from library.models import Category, Paper
    from library.storage import write_bundle,publish
    for name in ['LCOA 计算','仿真','AI']:Category.objects.get_or_create(name=name)
    audit=json.loads((ROOT/'reference_audit.json').read_text(encoding='utf-8'))
    for ref in audit['papers']:
        if Paper.objects.filter(raw_hash=ref['html_sha256']).exists():
            print('已存在，保留原状态：'+ref['paper_key']);continue
        html=ROOT/ref['html'];raw=html.read_bytes();pdf=(ROOT/ref['original_pdf']).read_bytes()
        mapping=(html.parent/'paragraph_map.json').read_bytes()
        article=load_article(raw,html.name,mapping,pdf)
        expected={'idaes':{'pairs':234,'paragraphs':121,'images':19,'equations':13,'mathml':145,'tables':5,'references':41},
                  'ammonia':{'pairs':158,'paragraphs':91,'images':10,'equations':70,'mathml':750,'tables':9,'references':35}}[ref['paper_key']]
        for key,value in expected.items():
            if article['validation']['counts'][key]!=value:raise RuntimeError(f'{ref["paper_key"]} 的 {key} 与基线不符。')
        folder=settings.DATA_DIR/'staging'/'initial'/str(uuid.uuid4())
        write_bundle(folder,article,raw,pdf,mapping)
        metadata={'title_en':article['title_en'],'title_zh':article['title_zh'],'source_url':article['source_url'],'note':'双语全文，含原文 PDF 与段落映射。'}
        p=publish(folder,article,metadata,[Category.objects.get(name='仿真')],trusted=True)
        print('已导入：'+p.title_zh+' | '+json.dumps(article['validation']['counts'],ensure_ascii=False))

def ensure_runtime():
    if sys.version_info<(3,10):raise RuntimeError('需要兼容 Django 5.2 的 Python 3.10 或更新版本。')
    if not PYTHON.exists():
        print('创建项目独立 Python 环境…',flush=True)
        subprocess.run([sys.executable,'-m','venv',str(VENV)],check=True)
    if Path(sys.executable).resolve()!=PYTHON.resolve():
        result=subprocess.run([str(PYTHON),str(ROOT/'launcher.py'),*sys.argv[1:]],env={**os.environ,'PYTHONUTF8':'1'})
        raise SystemExit(result.returncode)

def setup(data):
    ensure_runtime()
    print('首次安装／显式维护：联网安装已锁定的依赖。',flush=True)
    subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.lock')],check=True)
    configure(data)
    with exclusive(data):
        new_install=not (data/'db.sqlite3').is_file() or not (data/'db.sqlite3').stat().st_size
        if not new_install:
            print('迁移前备份：'+str(backup_data(data)),flush=True)
        init_django(data)
        from django.core.management import call_command
        call_command('migrate',interactive=False)
        from library.tagging import initialize_vocabulary
        enabled=initialize_vocabulary(new_install=new_install)
        if enabled: print('首次安装已启用常用标签：'+ '、'.join(enabled),flush=True)
        else:
            from library.models import Tag
            if not Tag.objects.filter(active=True).exists():
                print('现有词表保持不变：暂无启用标签。管理员可从上传页进入标签管理，选择并启用需要的词条。',flush=True)
        call_command('collectstatic',interactive=False,verbosity=0)
        import_references()
        from library.revisions import initialize_revisions
        initialize_revisions()
        call_command('check')
        verify_data(data)
    subprocess.run([sys.executable,'-m','pip','check'],check=True)
    print('安装完成。双击 start.cmd，打开网站登录、注册或选择匿名登录；管理账户可用 manage-account.cmd 设置。')

def start(data,port):
    if not (data/'local.json').is_file():raise RuntimeError('尚未安装，请先运行 setup.cmd。')
    try:
        test=socket.socket();test.bind(('127.0.0.1',port));test.close()
    except OSError:
        import urllib.request
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz/',timeout=1) as r:info=json.load(r)
            own=json.loads((data/'local.json').read_text(encoding='utf-8'))['instance_id']
            if info.get('application')=='paper-library-v3' and info.get('instance')==own:
                print(f'本应用已在运行：http://127.0.0.1:{port}/');return
        except Exception:pass
        raise RuntimeError(f'端口 {port} 被其他应用占用。未终止任何进程。使用 start.cmd --port 8001 指定备用端口。')
    with exclusive(data):
        init_django(data)
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor=MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):raise RuntimeError('有待执行迁移，请先停止应用并运行 setup.cmd。')
        if not (ROOT/'app/staticfiles/staticfiles.json').is_file():raise RuntimeError('静态文件未就绪，请运行 setup.cmd。')
        from library.storage import cleanup_staging
        cleanup_staging()
        from config.wsgi import application
        from waitress import serve
        print(f'论文库已启动：http://127.0.0.1:{port}/\n数据目录：{data}\n仅本机可访问。按 Ctrl+C 停止；关闭此窗口或休眠会中断访问。',flush=True)
        serve(application,host='127.0.0.1',port=port,threads=6,max_request_body_size=160*1024**2,expose_tracebacks=False)

def manage_account(data):
    with exclusive(data):
        init_django(data)
        from django.contrib.auth import get_user_model
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        User=get_user_model()
        print('本机账户管理（请先停止网站）。密码不会显示或写入日志。')
        action=input('选择：1 创建管理员，2 创建成员，3 重置密码：').strip()
        username=input('账户名：').strip()
        if action not in {'1','2','3'} or not username:raise RuntimeError('操作或账户名无效。')
        if action=='3':
            user=User.objects.get(username=username)
        else:
            if User.objects.filter(username=username).exists():raise RuntimeError('账户已存在，请选择重置密码。')
            user=User(username=username,first_name=input('显示名称（可留空）：').strip(),is_staff=action=='1',is_superuser=action=='1')
        user.full_clean(exclude=['password'])
        password=getpass.getpass('新密码（至少 10 位）：')
        if password!=getpass.getpass('再次输入密码：'):raise RuntimeError('两次密码不一致。')
        validate_password(password,user);user.set_password(password);user.save()
        print('账户已保存。可以启动网站登录。')


def revise(data, paper_id, html, pdf=None, mapping=None, without_pdf=False):
    """Validate an explicit correction; preserve every previously published snapshot."""
    if not paper_id or not html: raise RuntimeError('修订需要 --paper 论文 ID 和 --html 新双语 HTML。')
    with exclusive(data):
        init_django(data)
        from library.models import Paper
        from library.article import load_article
        from library.storage import write_bundle
        from library.revisions import ensure_revision, revision_dir
        paper=Paper.objects.get(pk=paper_id)
        current=revision_dir(paper.current_revision) if paper.current_revision_id else data/'papers'/str(paper.id)
        raw=html.read_bytes()
        pdf_bytes=None if without_pdf else pdf.read_bytes() if pdf else (current/'original.pdf').read_bytes() if (current/'original.pdf').exists() else None
        map_bytes=mapping.read_bytes() if mapping else None
        article=load_article(raw,html.name,map_bytes,pdf_bytes)
        # A validation failure above never mutates the database or published assets.
        print('修订前备份：'+str(backup_data(data)),flush=True)
        with tempfile.TemporaryDirectory(prefix='revision-',dir=data/'staging') as temporary:
            folder=Path(temporary)/'validated'
            write_bundle(folder,article,raw,pdf_bytes,map_bytes)
            revision=ensure_revision(paper,folder)
        verify_data(data)
        print('当前内容修订：'+str(revision.id)+'；旧版批注和快照已保留。')

def main():
    parser=argparse.ArgumentParser(description='论文库本机运行与维护')
    parser.add_argument('action',choices=['setup','start','backup','restore','account','check','revise'])
    parser.add_argument('--data-dir',type=Path,default=Path(os.environ.get('PAPER_LIBRARY_DATA',ROOT/'var')))
    parser.add_argument('--port',type=int,default=8000)
    parser.add_argument('--archive',type=Path);parser.add_argument('--target',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--paper');parser.add_argument('--html',type=Path);parser.add_argument('--pdf',type=Path)
    parser.add_argument('--mapping',type=Path);parser.add_argument('--without-pdf',action='store_true')
    args=parser.parse_args();data=args.data_dir.resolve()
    # SQLite must stay off known network/synchronization locations.
    if str(data).startswith('\\\\') or any(s.lower() in {'onedrive','dropbox','google drive'} or s.lower().startswith('onedrive - ') for s in data.parts):
        raise RuntimeError('请选择本地非同步磁盘目录，通过 --data-dir 指定。')
    if args.action=='setup':setup(data)
    elif args.action=='start':start(data,args.port)
    elif args.action=='account':manage_account(data)
    elif args.action=='revise':revise(data,args.paper,args.html,args.pdf,args.mapping,args.without_pdf)
    elif args.action=='backup':
        with exclusive(data):print('备份完成（含账户密码哈希，按敏感资料保管）：'+str(backup_data(data,args.output)))
    elif args.action=='restore':
        archive=args.archive or Path(input('备份 ZIP 路径：').strip('" '))
        dest=(args.target or ROOT/'restored'/('data-'+time.strftime('%Y%m%d-%H%M%S'))).resolve()
        print('已恢复到新目录：'+str(restore_data(archive.resolve(),dest)))
        print(f'验证入口：start.cmd --data-dir "{dest}" --port 8001')
    elif args.action=='check':
        with exclusive(data):verify_data(data)
        print('数据完整性检查通过。')

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('\n已停止。')
    except Exception as exc:
        print('未完成：'+str(exc),file=sys.stderr);sys.exit(1)
