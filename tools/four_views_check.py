"""Offline upgrade/restore rehearsal. Accepts only fresh, isolated test-runs directories."""
import argparse
from collections import Counter
import contextlib
import csv
import json
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import launcher


def legacy_ledger(data):
    with contextlib.closing(sqlite3.connect(data/'db.sqlite3')) as db:
        return {table:db.execute('SELECT '+columns+' FROM library_'+table+' ORDER BY id').fetchall()
                for table,columns in [('comment','id,paper_id,user_id,parent_id,body,created_at,updated_at,edited,deleted,hidden,request_key,request_hash'),
                                      ('rating','id,paper_id,user_id,dimension,value,updated_at')]}


def verification(data, output):
    from bs4 import BeautifulSoup
    from django.contrib.auth.models import User
    from django.db import transaction
    from django.test import Client
    from library.models import Paper, AnnotationAnchor
    from library.revisions import manifest_for, revision_dir
    output.mkdir(parents=True,exist_ok=True)
    member=User.objects.filter(is_staff=False,is_active=True).first()
    assert member, 'Use a baseline containing at least one ordinary test member.'
    client=Client(HTTP_HOST='127.0.0.1');client.force_login(member)
    reports=[]
    for paper in Paper.objects.all():
        manifest=manifest_for(paper.current_revision);folder=revision_dir(paper.current_revision)
        body=BeautifulSoup((folder/'body.html').read_text(encoding='utf-8'),'html.parser')
        reader=BeautifulSoup((folder/'reader.html').read_text(encoding='utf-8'),'html.parser')
        assert body.get_text()==reader.get_text(), 'Reader changed source text'
        assert [str(n) for n in body.select('math')]==[str(n) for n in reader.select('math')], 'Reader changed MathML'
        assert [n.get('src') for n in body.select('img')]==[n.get('src') for n in reader.select('img')], 'Reader changed images'
        base=f'/api/papers/{paper.id}/'
        counts=[]
        for view in ['both','en','zh','pdf']:
            response=client.get(base+'annotations/',{'view':view})
            assert response.status_code==200, response.content
            result=response.json();counts.append(result['count'])
            assert len({t['id'] for t in result['threads']})==result['count']
            for thread in result['threads']:
                assert client.get(thread['source_url']).status_code==200
        assert len(set(counts))==1
        assert Client(HTTP_HOST='127.0.0.1').get(base+'annotations/').status_code==401
        with transaction.atomic():
            paper.visible=False;paper.save(update_fields=['visible'])
            assert client.get(base+'annotations/').status_code==404
            assert client.get(base+'representation/').status_code==404
            assert client.get(f'/papers/{paper.id}/revisions/{paper.current_revision_id}/').status_code==404
            assert client.get(base+f'revisions/{paper.current_revision_id}/pdf/').status_code==404
            transaction.set_rollback(True)
        paper.refresh_from_db()
        key='idaes' if 'IDAES' in paper.title_en else 'ammonia'
        coverage={p:0 for p in ['exact','block','object','page','unmapped']};coverage.update(manifest['coverage'])
        rows=[]
        for unit in manifest['units'].values():
            mapping=unit['pdf']
            indices=sorted({f['page_index'] for f in mapping.get('fragments',[])}|set(mapping.get('pages',[])))
            rows.append({'unit_id':unit['id'],'kind':unit['kind'],'precision':mapping['precision'],
                         'physical_pages':[i+1 for i in indices],'method':mapping['method'],'reason':mapping.get('reason',''),
                         'map_text_status':unit.get('map_text_status','not-supplied'),
                         'exact_english_representations':sum(manifest['representations'][r].get('pdf',{}).get('precision')=='exact' for r in unit['representations'])})
        report={'paper':key,'paper_id':str(paper.id),'revision_id':str(paper.current_revision_id),
                'pdf_sha256':manifest['pdf_sha256'],'content_hash':manifest['content_hash'],
                'schema_version':manifest['schema_version'],'coverage':coverage,'units':rows,
                'note':'Unit coverage is conservative: bilingual counterparts use block/page. Quote+context can resolve a selected English subrange separately. No audited cross-language phrase alignment is supplied.'}
        (output/(key+'-coverage.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        with (output/(key+'-coverage.csv')).open('w',encoding='utf-8-sig',newline='') as file:
            writer=csv.DictWriter(file,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        reports.append({'paper':key,'coverage':coverage,'threads':counts[0],'source_fidelity':'PASS','permissions':'PASS','four_view_identity':'PASS'})
    launcher.verify_data(data)
    (output/'restored-verification.json').write_text(json.dumps({'data_dir':str(data),'results':reports},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(reports,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','verify'])
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--seed-from',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'evidence'/'four-views')
    args=parser.parse_args();data=args.data_dir.resolve()
    if not data.is_relative_to((ROOT/'test-runs').resolve()):raise RuntimeError('This rehearsal only permits paths under GAReader/test-runs.')
    before=None
    if args.action=='prepare':
        if not args.archive:raise RuntimeError('--archive is required; existing targets are never overwritten.')
        launcher.restore_data(args.archive.resolve(),data);before=legacy_ledger(data)
    launcher.init_django(data)
    if before is not None:
        from django.core.management import call_command
        from django.contrib.auth.models import User
        from django.test import Client
        from library.models import Paper, PaperRevision
        from library.revisions import initialize_revisions
        call_command('migrate',interactive=False,verbosity=0)
        initialize_revisions();count=PaperRevision.objects.count();initialize_revisions();launcher.import_references()
        assert PaperRevision.objects.count()==count
        assert legacy_ledger(data)==before, 'Migration changed existing comments or ratings'
        if args.seed_from:
            source=args.seed_from.resolve()
            if not source.is_relative_to((ROOT/'test-runs').resolve()):raise RuntimeError('Seed must also be isolated.')
            with contextlib.closing(sqlite3.connect(source/'db.sqlite3')) as db:
                seeds=db.execute('SELECT c.paper_id,c.body,a.source FROM library_annotationanchor a JOIN library_comment c ON c.id=a.comment_id').fetchall()
            client=Client(HTTP_HOST='127.0.0.1');client.force_login(User.objects.get(username='reader_a'))
            for pid,body,raw_source in seeds:
                paper=Paper.objects.get(pk=pid);anchor=json.loads(raw_source)
                anchor['revision_id']=str(paper.current_revision_id)
                response=client.post(f'/api/papers/{paper.id}/annotations/',json.dumps({'body':body,'source':anchor,'request_key':str(uuid.uuid4())}),content_type='application/json')
                assert response.status_code==201,response.content
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/'migration.json').write_text(json.dumps({'status':'PASS','old_comments':len(before['comment']),
            'old_ratings':len(before['rating']),'revision_count':count,'repeated_upgrade':'PASS','legacy_rows_unchanged':True},indent=2),encoding='utf-8')
        call_command('collectstatic',interactive=False,verbosity=0)
    verification(data,args.output)


if __name__=='__main__':main()
