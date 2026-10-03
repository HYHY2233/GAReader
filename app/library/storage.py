import json
import shutil
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from .article import FormatError
from .models import Paper

def paper_dir(paper): return settings.DATA_DIR / 'papers' / str(paper.id)
def write_bundle(folder, article, raw, pdf=None, mapping=None):
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'original.html').write_bytes(raw)
    (folder/'body.html').write_bytes(article['body'].encode('utf-8'))
    (folder/'nav.json').write_text(json.dumps(article['nav'],ensure_ascii=False),encoding='utf-8')
    (folder/'validation.json').write_text(json.dumps(article['validation'],ensure_ascii=False,indent=2),encoding='utf-8')
    for i,(data,ext) in enumerate(article['images']): (folder/f'image-{i}.{ext}').write_bytes(data)
    if pdf is not None: (folder/'original.pdf').write_bytes(pdf)
    if mapping is not None: (folder/'paragraph_map.json').write_bytes(mapping)

def publish(folder, article, metadata, categories, user=None, trusted=False):
    if Paper.objects.filter(raw_hash=article['raw_hash']).exists():
        raise FormatError('FMT_DUPLICATE','该 HTML 已在库中（包括隐藏论文）。')
    paper = Paper(id=uuid.uuid4(), submitter=user, trusted_original=trusted,
        raw_hash=article['raw_hash'], content_hash=article['content_hash'], profile=article['profile'],
        has_pdf=(folder/'original.pdf').exists(),has_map=(folder/'paragraph_map.json').exists(),
        validation=article['validation'], **metadata)
    dest = paper_dir(paper); dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        with transaction.atomic():
            paper.save(force_insert=True); paper.categories.set(categories)
            folder.rename(dest)
    except Exception:
        # Only this unpublished UUID's directory can be removed on rollback.
        if dest.exists(): shutil.rmtree(dest)
        raise
    return paper

def cleanup_staging():
    root=settings.DATA_DIR/'staging'
    if root.exists():
        for p in root.glob('*/*'):
            if p.is_dir() and not p.is_symlink() and p.stat().st_mtime < time.time()-86400:
                shutil.rmtree(p)

def rendered_body(folder, image_url):
    body=(folder/'body.html').read_text(encoding='utf-8')
    for path in folder.glob('image-*'):
        num=path.stem.split('-')[1]
        body=body.replace(f'@@IMAGE:{num}@@', image_url(path.name))
    return body
