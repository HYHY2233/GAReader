"""Read-only: compare a stopped data directory with its pre-maintenance backup."""
import argparse, hashlib, json, sqlite3, zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
old=sqlite3.connect(':memory:');new=sqlite3.connect(args.data_dir.resolve().joinpath('db.sqlite3').as_uri()+'?mode=ro',uri=True)
report={'status':'PASS','databaseAccess':'read-only','tables':[]}
with zipfile.ZipFile(args.archive) as archive:
    old.deserialize(archive.read('db.sqlite3'))
    tables=[r[0] for r in old.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    assert tables==[r[0] for r in new.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for table in tables:
        query='SELECT * FROM "'+table.replace('"','""')+'"'
        before=sorted(old.execute(query).fetchall(),key=repr);after=sorted(new.execute(query).fetchall(),key=repr)
        assert before==after,table+' changed'
        report['tables'].append({'name':table,'rows':len(after),'status':'PASS'})
    files=0
    for name in archive.namelist():
        if not name.startswith('papers/') or name.endswith('/'):continue
        target=(args.data_dir/name).resolve();assert target.is_relative_to(args.data_dir.resolve())
        assert hashlib.sha256(archive.read(name)).digest()==hashlib.sha256(target.read_bytes()).digest(),name
        files+=1
    report['unchangedPaperFiles']=files
old.close();new.close();args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
