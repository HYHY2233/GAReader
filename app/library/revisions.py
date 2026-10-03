"""Immutable article snapshots and explicit, evidence-based representations."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from bs4 import BeautifulSoup
from django.conf import settings
from django.db import transaction

from .logical_text import NORMALIZATION, normalize, normalized_map, occurrences, text_hash
from .models import Paper, PaperRevision
from .pdf_index import index_pdf, quads_for

SCHEMA = 1


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ''


def revision_dir(revision):
    return settings.DATA_DIR/'papers'/str(revision.paper_id)/'revisions'/str(revision.id)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def manifest_for(revision):
    path = revision_dir(revision)/'representation-manifest.json'
    if file_hash(path) != revision.manifest_sha256:
        raise ValueError('内容定位清单校验失败，未使用不一致的坐标。')
    return read_json(path)


def pdf_for(revision):
    folder = revision_dir(revision)
    if revision.pdf_sha256 and file_hash(folder/'original.pdf') != revision.pdf_sha256:
        raise ValueError('原版 PDF 哈希不一致，未复用坐标。')
    manifest=manifest_for(revision)
    if manifest.get('pdf_index_sha256') and file_hash(folder/'pdf-index.json')!=manifest['pdf_index_sha256']:
        raise ValueError('PDF 文字索引校验失败。')
    return read_json(folder/'pdf-index.json') if (folder/'pdf-index.json').exists() else {'pages': [], 'status': 'absent'}


def element_text(element):
    return ''.join(str(s) for s in element.strings if not any(p.name in {'annotation','script','style'} for p in s.parents))


def build_manifest(folder, revision_id, pdf):
    soup = BeautifulSoup((folder/'body.html').read_text(encoding='utf-8'), 'html.parser')
    main = soup.find('main')
    units, unit_tags, representations = {}, {}, {}
    original_ids = {t.get('id') for t in main.find_all(id=True)}
    generated_counts = Counter()

    def unit_for(tag, kind='paragraph'):
        dom_id = tag.get('id')
        if not dom_id:
            base = 'content-'+text_hash(kind+'|'+element_text(tag))[:18]
            generated_counts[base] += 1
            dom_id = base+'-'+str(generated_counts[base])
            while dom_id in original_ids:
                dom_id += '-u'
            tag['id'] = dom_id; original_ids.add(dom_id)
        if dom_id not in units:
            inferred = 'formula' if 'equation' in tag.get('class',[]) else kind
            if tag.name == 'figure' or dom_id.startswith('figure-'): inferred = 'figure'
            if 'shared-table' in tag.get('class',[]) or dom_id.startswith('table-'): inferred = 'table'
            if tag.find_parent(class_='ai-note') or 'ai-note' in tag.get('class',[]): inferred = 'note'
            label = normalize(element_text(tag))[:100] or dom_id
            # Object anchors need the entire scientific object, including its image bytes.
            image_hashes = []
            for image in tag.find_all('img'):
                match = re.fullmatch(r'@@IMAGE:(\d+)@@', image.get('src',''))
                if match:
                    image_hashes.extend(file_hash(p) for p in sorted(folder.glob('image-'+match[1]+'.*')))
            units[dom_id] = {'id': dom_id, 'alignment_group_id': dom_id, 'kind': inferred,
                             'label': label, 'order': 0, 'representations': [], 'origin': 'validated-html',
                             'fingerprint': text_hash(str(tag)+'|'+('|'.join(image_hashes))),
                             'pdf': {'precision': 'unmapped', 'reason': '未找到可靠的 PDF 对应内容。', 'method': 'none'}}
            tag['data-unit'] = dom_id; tag['data-kind'] = inferred; unit_tags[dom_id] = tag
        return units[dom_id]

    def representation(unit, tag, language):
        number = sum(representations[r]['language'] == language for r in unit['representations'])
        rid = unit['id']+'::'+language+'::'+str(number)
        raw = element_text(tag); text = normalize(raw)
        if not text:
            return
        tag['data-representation'] = rid; tag['data-rep-language'] = language
        raw_offset=0;raw_math=[]
        for string in tag.strings:
            if any(p.name in {'annotation','script','style'} for p in string.parents): continue
            length=len(str(string))
            if any(p.name=='math' for p in string.parents): raw_math.append((raw_offset,raw_offset+length))
            raw_offset+=length
        _,reverse=normalized_map(raw)
        math_positions=[i for i,(a,b) in enumerate(reverse) if any(a<end and b>start for start,end in raw_math)]
        math_ranges=[]
        for position in math_positions:
            if math_ranges and math_ranges[-1][1]==position: math_ranges[-1][1]=position+1
            else: math_ranges.append([position,position+1])
        representations[rid] = {'id': rid, 'unit_id': unit['id'], 'language': language,
                                'raw_text': raw, 'text': text, 'text_hash': text_hash(text),
                                'normalization_version': NORMALIZATION, 'contains_math': bool(tag.find('math')),
                                'math_ranges':math_ranges}
        unit['representations'].append(rid)

    structural = {'paragraph','heading','heading-pair','item','shared-figure','shared-table','caption-wrap','equation'}
    for pair in main.select('.pair'):
        owner = pair
        for parent in pair.parents:
            if parent is main:
                break
            if set(parent.get('class',[])) & structural or parent.name == 'header':
                owner = parent; break
        kind = 'heading' if any(x in owner.get('class',[]) for x in ['heading','heading-pair']) or owner.name=='header' else 'paragraph'
        unit = unit_for(owner, kind)
        for side in pair.find_all(recursive=False):
            language = 'en' if 'en' in side.get('class',[]) else 'zh' if 'zh' in side.get('class',[]) else None
            if language:
                representation(unit, side, language)
    for tag in main.select('.equation, .shared-figure, .shared-table, .caption-wrap[id], .reference[id]'):
        kind = 'reference' if 'reference' in tag.get('class',[]) else 'object'
        unit = unit_for(tag, kind)
        if kind == 'reference' and not unit['representations']:
            representation(unit, tag, 'en')
    for tag in main.select('.ai-note, .reading-note, .reader-update'):
        if tag.select('.pair') or tag.find_parent(attrs={'data-representation':True}):
            continue
        unit=unit_for(tag,'note')
        representation(unit,tag,'zh')
    # The order is derived once from the immutable document; IDs never use page progress.
    for order, tag in enumerate(main.select('[data-unit]')):
        units[tag['data-unit']]['order'] = order

    mapping_path = folder/'paragraph_map.json'
    supplied = read_json(mapping_path) if mapping_path.exists() else []
    supplied_sha = next((supplied[k] for k in ['pdf_sha256','source_pdf_sha256','original_pdf_sha256'] if isinstance(supplied,dict) and supplied.get(k)),None)
    map_source_ok = supplied_sha is None or str(supplied_sha).lower()==pdf.get('pdf_sha256','').lower()
    records = supplied if isinstance(supplied,list) else supplied.get('paragraphs', supplied.get('entries', []))
    if not isinstance(records,list): records = []
    map_by_id = {str(r.get('id')): r for r in records if isinstance(r,dict)}
    map_audit = []
    for unit_id, unit in units.items():
        # The sanitizer prefixes original DOM IDs to isolate the article from reader controls.
        record = map_by_id.get(unit_id.removeprefix('p-'))
        if not record:
            continue
        expected_en = record.get('en') or ' '.join(record.get('english_fragments',[]))
        actual_en = ' '.join(representations[r]['text'] for r in unit['representations'] if representations[r]['language']=='en')
        matched = bool(expected_en) and normalize(expected_en)==normalize(actual_en)
        unit['map_text_status'] = ('verified' if matched else 'text-differs') if map_source_ok else 'source-hash-mismatch'
        source = record.get('source', [])
        unit['source_hint'] = source
        map_audit.append({'unit_id':unit_id,'text_status':unit['map_text_status']})

    pages = pdf.get('pages', [])
    page_offsets, combined = [], ''
    for page in pages:
        page_offsets.append(len(combined)); combined += page['text']+' '

    def fragments(start, end):
        result = []
        for page, offset in zip(pages,page_offsets):
            lo, hi = max(start,offset)-offset, min(end,offset+len(page['text']))-offset
            if lo < hi:
                result.append({'page_index':page['page_index'],'start':lo,'end':hi,
                               'quads':quads_for(page,lo,hi)})
        return result

    for unit in units.values():
        aligned = []
        if unit['kind'] == 'note':
            unit['pdf']['reason'] = '译者或补充说明未确认有原文对应。'
            continue
        for rid in unit['representations']:
            rep = representations[rid]
            if rep['language'] != 'en' or len(rep['text']) < 12:
                continue
            matches = occurrences(combined, rep['text'])
            if len(matches) == 1:
                start = matches[0]
                rep['pdf'] = {'precision':'exact','method':'unique-full-text-nfc',
                              'global_start':start,'fragments':fragments(start,start+len(rep['text']))}
                aligned.extend(rep['pdf']['fragments'])
            elif len(matches)>1:
                rep['pdf'] = {'precision':'unmapped','method':'ambiguous-text','reason':'原文中存在多处相同文字。'}
        if aligned:
            unit['pdf'] = {'precision':'block','method':'unique-english-representation','fragments':aligned,
                           'reason':'英文表示与原版文字唯一匹配；中文仅按内容单元对应。'}
        elif pages and unit.get('map_text_status')=='verified':
            hints = json.dumps(unit.get('source_hint'),ensure_ascii=False)
            indices = set()
            for match in re.finditer(r'PDF\s*(\d+)(?:\s*[-–—]\s*(\d+))?',hints,re.I):
                first,last=int(match[1]),int(match[2] or match[1])
                indices.update(range(first-1,min(last,len(pages))))
            indices={i for i in indices if 0<=i<len(pages)}
            if indices:
                unit['pdf']={'precision':'page','method':'validated-map-physical-page-hint',
                             'pages':sorted(indices),'reason':'仅确认映射中注明的 PDF 物理页，没有可靠段落几何。'}
    manifest = {'schema_version':SCHEMA,'normalization_version':NORMALIZATION,'offset_unit':'unicode_code_point',
                'revision_id':str(revision_id),'content_hash':file_hash(folder/'body.html'),
                'raw_hash':file_hash(folder/'original.html'),'pdf_sha256':pdf.get('pdf_sha256',''),
                'units':units,'representations':representations,'map_validation':map_audit,
                'pdf':{'status':pdf.get('status'),'extractor_version':pdf.get('extractor_version',''),
                       'coordinate_system':'pdf-user-space','pages':[
                           {k:p[k] for k in ['page_index','page_label','view_box','rotation','text_hash']} for p in pages]},
                'coverage':dict(Counter(u['pdf']['precision'] for u in units.values()))}
    manifest['coverage']['total_units']=len(units)
    manifest['coverage']['exact_representations']=sum(r.get('pdf',{}).get('precision')=='exact' for r in representations.values())
    (folder/'reader.html').write_text(str(soup),encoding='utf-8')
    manifest['reader_sha256']=file_hash(folder/'reader.html')
    manifest['pdf_index_sha256']=file_hash(folder/'pdf-index.json')
    (folder/'alignment.json').write_text(json.dumps({'schema_version':SCHEMA,'revision_id':str(revision_id),
        'pdf_sha256':manifest['pdf_sha256'],'coverage':manifest['coverage'],
        'units':{k:v['pdf'] for k,v in units.items()}},ensure_ascii=False,indent=2),encoding='utf-8')
    manifest['assets']={p.name:file_hash(p) for p in sorted(folder.iterdir()) if p.is_file() and p.name!='representation-manifest.json'}
    (folder/'representation-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    return manifest


def ensure_revision(paper, source=None, activate=True):
    root = settings.DATA_DIR/'papers'/str(paper.id)
    source = Path(source) if source else root
    content_hash = file_hash(source/'body.html')
    if not content_hash:
        raise ValueError('缺少待建立快照的正文。')
    pdf_sha = file_hash(source/'original.pdf')
    scientific_assets = [file_hash(p) for p in sorted(source.glob('image-*')) if p.is_file()]
    identity = text_hash('|'.join([content_hash,pdf_sha,file_hash(source/'paragraph_map.json'),*scientific_assets]))
    old = PaperRevision.objects.filter(paper=paper,identity=identity).first()
    if old:
        if activate and paper.current_revision_id!=old.id:
            paper.current_revision=old; paper.content_hash=old.content_hash
            paper.save(update_fields=['current_revision','content_hash'])
        return old
    rid = uuid.uuid4()
    staging = settings.DATA_DIR/'staging'/'revisions'/str(rid)
    staging.mkdir(parents=True,exist_ok=False)
    dest=root/'revisions'/str(rid)
    try:
        for path in source.iterdir():
            if path.is_file() and (path.name in {'original.html','original.pdf','paragraph_map.json','body.html','nav.json','validation.json'} or re.fullmatch(r'image-\d+\.(png|jpeg|webp)',path.name)):
                shutil.copyfile(path,staging/path.name)
        pdf=index_pdf(staging)
        manifest=build_manifest(staging,rid,pdf)
        with transaction.atomic():
            revision=PaperRevision.objects.create(id=rid,paper=paper,identity=identity,content_hash=content_hash,
                pdf_sha256=pdf_sha,manifest_sha256=file_hash(staging/'representation-manifest.json'),
                title_en=paper.title_en,title_zh=paper.title_zh)
            dest.parent.mkdir(parents=True,exist_ok=True)
            staging.rename(dest)
            if activate:
                paper.current_revision=revision; paper.content_hash=content_hash
                paper.save(update_fields=['current_revision','content_hash'])
        return revision
    except Exception:
        for folder in [staging,dest]:
            if folder.exists() and folder.name==str(rid) and folder.resolve().is_relative_to(settings.DATA_DIR.resolve()):
                shutil.rmtree(folder)
        raise


def initialize_revisions():
    for paper in Paper.objects.filter(current_revision=None):
        ensure_revision(paper)
