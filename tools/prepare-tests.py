"""Create a NEW isolated fixture; refuse to reset any existing test or real data."""
import json
from pathlib import Path
import secrets
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import launcher
data=ROOT/'test-runs'/'integration'
credentials=ROOT/'test-runs'/'credentials.json'
if data.exists() or credentials.exists():
    raise SystemExit('测试目录已存在，不会重置。请在新的源码副本运行本组端到端测试。')
(ROOT/'evidence').mkdir(exist_ok=True)
launcher.configure(data);launcher.init_django(data)
from django.core.management import call_command
from django.contrib.auth.models import User
from library.models import Paper
call_command('migrate',interactive=False,verbosity=0)
call_command('collectstatic',interactive=False,verbosity=0)
launcher.import_references()
password=secrets.token_urlsafe(24)
for name,display in [('reader_a','测试甲'),('reader_b','测试乙')]:
    User.objects.create_user(name,password=password,first_name=display)
User.objects.create_superuser('test_manager',password=password,first_name='测试管理员')
credentials.write_text(json.dumps({'password':password,'papers':[{'id':str(p.id),'title':p.title_zh,'profile':p.profile} for p in Paper.objects.all()]},ensure_ascii=False),encoding='utf-8')
print('隔离测试已准备。凭据仅保存在被忽略的本机测试目录，不输出、不放入共享包。')
print('用 start.cmd --data-dir test-runs/integration --port 8001 启动测试库。')
