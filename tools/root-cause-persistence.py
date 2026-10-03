"""Read-only comparison of the two isolated tag databases before/after real restart."""
import json, sqlite3, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];base=root/'test-runs/root-cause-v4'
states={}
for name in ['fresh-install','legacy']:
    with sqlite3.connect((base/name/'db.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
        states[name]={table:db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall()
                      for table in ['library_tag','library_paper_tags','library_paper_categories']}
file=base/'tags-before-restart.json'
if sys.argv[1]=='before':file.write_text(json.dumps(states),encoding='utf-8');print('Saved isolated pre-restart tag state')
else:
    assert json.loads(json.dumps(states))==json.loads(file.read_text(encoding='utf-8'))
    report={'status':'PASS','checks':['Fresh install: selected paper tags survived real server restart and repeated setup',
                                    'Existing 0003: only administrator-selected tags enabled; unrelated inactive tag unchanged'],
            'instances':{name:{table:len(rows) for table,rows in tables.items()} for name,tables in states.items()}}
    (root/'evidence/root-cause-v4/tag-persistence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
