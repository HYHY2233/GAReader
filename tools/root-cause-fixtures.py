"""Prepare test accounts only AFTER normal installation; never seeds enabled tags."""
import argparse, json, os, secrets, sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('name',choices=['fresh-install','legacy'])
args=parser.parse_args();data=root/'test-runs/root-cause-v4'/args.name
assert data.resolve().is_relative_to((root/'test-runs').resolve())
os.environ['PAPER_LIBRARY_DATA']=str(data);os.environ['DJANGO_SETTINGS_MODULE']='config.settings'
sys.path.insert(0,str(root/'app'));import django;django.setup()
from library.models import Tag, Paper
from django.contrib.auth.models import User
assert Tag.objects.count()==13
assert Tag.objects.filter(active=True).count()==(13 if args.name=='fresh-install' else 0)
credentials=root/'test-runs/root-cause-v4/accounts.json'
values=json.loads(credentials.read_text()) if credentials.exists() else {'password':secrets.token_urlsafe(24)}
for username,staff in [('v4_manager',True),('v4_member',False),('v4_other',False)]:
    account,_=User.objects.get_or_create(username=username)
    account.set_password(values['password']);account.first_name='隔离管理员' if staff else '隔离读者'
    account.is_staff=staff;account.is_superuser=staff;account.save()
values[args.name]={'papers':[{'id':str(p.id),'profile':p.profile} for p in Paper.objects.order_by('created_at')],
    'data_dir':str(data),'active_tags_after_normal_setup':Tag.objects.filter(active=True).count()}
credentials.write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'instance':args.name,'normal_setup_tags':Tag.objects.count(),
                  'active_tags_after_normal_setup':Tag.objects.filter(active=True).count(),'test_accounts_prepared':3}))
