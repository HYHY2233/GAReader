"""Exercise stopped backup restoration and real corrections only under test-runs."""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import launcher


def rows(data):
    with contextlib.closing(sqlite3.connect(data / 'db.sqlite3')) as db:
        return {name: db.execute('SELECT * FROM ' + name + ' ORDER BY 1').fetchall()
                for name in ['library_comment', 'library_rating', 'library_annotationanchor', 'library_paperrevision']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/four-views/maintenance.json')
    args = parser.parse_args()
    source, target = args.source.resolve(), args.target.resolve()
    for path in [source, target]:
        if not path.is_relative_to((ROOT / 'test-runs').resolve()):
            raise RuntimeError('This rehearsal requires isolated test-runs directories.')
    with launcher.exclusive(source):
        expected = rows(source)
    launcher.restore_data(args.archive.resolve(), target)
    assert rows(target) == expected, 'Backup restoration changed rows'
    launcher.init_django(target)
    from bs4 import BeautifulSoup
    from django.contrib.auth.models import User
    from django.test import Client
    from library.models import Paper, PaperRevision, AnnotationAnchor
    from library.revisions import manifest_for, revision_dir

    client = Client(HTTP_HOST='127.0.0.1')
    client.force_login(User.objects.get(username='reader_a'))
    paper = Paper.objects.get(title_en__icontains='IDAES')
    revision = paper.current_revision
    folder = revision_dir(revision)
    manifest = manifest_for(revision)
    old_files = {p.name: launcher.sha(p) for p in folder.iterdir() if p.is_file()}
    english = manifest['representations']['p-abstract::en::0']
    quote = 'Energy systems and'
    start = english['text'].index(quote)
    anchor = {'revision_id': str(revision.id), 'created_view': 'en', 'source_language': 'en', 'kind': 'text',
              'segments': [{'unit_id': 'p-abstract', 'representation_id': english['id'], 'start': start,
                            'end': start + len(quote), 'quote': quote, 'text_hash': english['text_hash'],
                            'normalization_version': english['normalization_version']}]}
    response = client.post(f'/api/papers/{paper.id}/annotations/', json.dumps({
        'source': anchor, 'body': 'Revision rehearsal: unchanged English quote.', 'request_key': str(uuid.uuid4())}),
        content_type='application/json')
    assert response.status_code == 201, response.content
    en_id = response.json()['id']
    originals = {a.comment_id: a.source for a in AnnotationAnchor.objects.all()}
    chinese_id = next(i for i, a in originals.items() if a['kind'] == 'text' and a['source_language'] == 'zh')
    object_id = next(i for i, a in originals.items() if a['kind'] == 'object' and a['segments'][0]['unit_id'] == 'p-eq-1')
    raw = (folder / 'original.html').read_text(encoding='utf-8')
    stage = target / 'staging'
    css_file = stage / 'css-only.html'
    css_file.write_text(raw.replace('</head>', '<style>/* isolated appearance rehearsal */</style></head>'), encoding='utf-8')
    count = PaperRevision.objects.count()
    launcher.revise(target, str(paper.id), css_file, mapping=folder / 'paragraph_map.json')
    paper.refresh_from_db()
    assert paper.current_revision_id == revision.id and PaperRevision.objects.count() == count
    changed = BeautifulSoup(raw, 'html.parser')
    matches = [n for n in changed.find_all(string=True) if '能源系统与制造过' in str(n)]
    assert len(matches) == 1
    matches[0].replace_with(str(matches[0]).replace('能源系统与制造过', '能源系统与生产过'))
    formula = changed.find(id='eq-1')
    assert formula
    formula.decompose()
    correction = stage / 'isolated-correction.html'
    correction.write_text(str(changed), encoding='utf-8')
    launcher.revise(target, str(paper.id), correction)
    paper.refresh_from_db()
    assert paper.current_revision_id != revision.id and PaperRevision.objects.count() == count + 1
    assert old_files == {p.name: launcher.sha(p) for p in folder.iterdir() if p.is_file()}
    current = client.get(f'/api/papers/{paper.id}/annotations/', {'view': 'both'}).json()
    threads = {t['id']: t for t in current['threads']}
    assert any(p['precision'] == 'exact' for p in threads[en_id]['projections'])
    assert all(p['precision'] == 'stale' for p in threads[chinese_id]['projections'])
    assert all(p['precision'] == 'stale' for p in threads[object_id]['projections'])
    for key in [chinese_id, object_id, en_id]:
        assert client.get(threads[key]['source_url']).status_code == 200
    assert {a.comment_id: a.source for a in AnnotationAnchor.objects.all()} == originals
    # The two-page PDF drag must remain two independently anchored fragments.
    multipage = [a for a in originals.values() if a['kind'] == 'pdf_text' and len(a['segments']) > 1]
    assert multipage and all(len({s['page_index'] for s in a['segments']}) > 1 for a in multipage)
    launcher.verify_data(target)
    report = {'status': 'PASS', 'backup_sha256': launcher.sha(args.archive), 'source_data': str(source),
              'restored_data': str(target), 'restored_rows_identical': True,
              'restored_counts': {k: len(v) for k, v in expected.items()},
              'css_only_no_revision': 'PASS', 'text_correction_new_snapshot': 'PASS',
              'unchanged_english_exact': 'PASS', 'changed_chinese_stale': 'PASS',
              'removed_formula_stale': 'PASS', 'original_source_anchors_unchanged': 'PASS',
              'old_snapshot_bytes_unchanged': 'PASS', 'old_source_urls_accessible': 'PASS',
              'pdf_crosspage_independent_fragments': 'PASS',
              'note': 'Only isolated copies were modified. Browser acceptance is recorded separately.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
