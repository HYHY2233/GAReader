"""Read-only: select real source segments for the v4 isolated browser acceptance."""
import json, os, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];data=root/'test-runs/root-cause-v4/working'
assert data.resolve().is_relative_to((root/'test-runs').resolve())
os.environ['PAPER_LIBRARY_DATA']=str(data);os.environ['DJANGO_SETTINGS_MODULE']='config.settings';sys.path.insert(0,str(root/'app'))
import django;django.setup()
from library.models import Paper
from library.anchors import validate_source, project
from library.revisions import manifest_for, pdf_for
for paper in Paper.objects.filter(visible=True).select_related('current_revision'):
    revision=paper.current_revision;m=manifest_for(revision);pdf=pdf_for(revision);choices={}
    for rep in m['representations'].values():
        if rep['language']!='en' or len(rep['text'])<60:continue
        raw={'revision_id':str(revision.id),'created_view':'en','source_language':'en','kind':'text',
             'segments':[{'unit_id':rep['unit_id'],'representation_id':rep['id'],'start':0,'end':len(rep['text']),
                          'quote':rep['text'],'prefix':'','suffix':'','text_hash':rep['text_hash'],
                          'normalization_version':rep['normalization_version']}]}
        try:source=validate_source(raw,revision,m,pdf)
        except ValueError:continue
        projected=project(source,m,m,pdf,'pdf');precisions={p['precision'] for p in projected}
        if precisions in ({'exact'},{'block'}):choices.setdefault(next(iter(precisions)),source)
        if len(choices)==2:
            mixed=dict(source,segments=[choices['exact']['segments'][0],choices['block']['segments'][0]])
            mixed['segments'].sort(key=lambda s:m['units'][s['unit_id']]['order'])
            mixed=validate_source(mixed,revision,m,pdf)
            result={'paper':str(paper.id),'source':mixed,'expected':project(mixed,m,m,pdf,'pdf')}
            (data.parent/'mixed-source.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'paper':str(paper.id),'segments':[{'unit':s['unit_id'],'length':len(s['quote'])} for s in mixed['segments']],
                              'precisions':[p['precision'] for p in result['expected']]}));sys.exit(0)
raise RuntimeError('No real mixed exact/block source pair found')
