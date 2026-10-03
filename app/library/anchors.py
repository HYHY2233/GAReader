"""Validate source anchors and project one thread without guessing translations."""
import math

from .logical_text import NORMALIZATION, normalize, occurrences, resolve_quote
from .pdf_index import quads_for

MAX_SEGMENTS = 32
MAX_QUOTE = 20000


class AnchorError(ValueError):
    pass


def bounded_json(value, depth=0):
    if depth > 10:
        raise AnchorError('批注定位数据层级过深。')
    if isinstance(value,dict):
        if len(value)>40: raise AnchorError('定位字段过多。')
        for key,item in value.items():
            if not isinstance(key,str) or len(key)>100: raise AnchorError('定位字段无效。')
            bounded_json(item,depth+1)
    elif isinstance(value,list):
        if len(value)>512: raise AnchorError('定位片段过多。')
        for item in value: bounded_json(item,depth+1)
    elif isinstance(value,str):
        if len(value)>MAX_QUOTE: raise AnchorError('所选文字过长，请分段批注。')
    elif value is not None and type(value) not in {int,float,bool}:
        raise AnchorError('定位数据类型无效。')


def validate_quads(quads, page):
    if not isinstance(quads,list) or not 1<=len(quads)<=256:
        raise AnchorError('PDF 选区需要独立的行内几何片段。')
    left,bottom,right,top=page['view_box']
    for quad in quads:
        if not isinstance(quad,list) or len(quad)!=8:
            raise AnchorError('PDF 坐标无效。')
        if any(type(x) not in {int,float} or not math.isfinite(x) for x in quad):
            raise AnchorError('PDF 坐标无效。')
        if any(not left-2<=x<=right+2 for x in quad[::2]) or any(not bottom-2<=y<=top+2 for y in quad[1::2]):
            raise AnchorError('PDF 坐标超出原页面边界。')


def geometry_agrees(page, start, end, quads):
    boxes=[b for b in page['boxes'][start:end] if b]
    if not boxes: return False
    hits=0
    for box in boxes:
        x,y=(box[0]+box[2])/2,(box[1]+box[3])/2
        if any(min(q[::2])-3<=x<=max(q[::2])+3 and min(q[1::2])-3<=y<=max(q[1::2])+3 for q in quads): hits+=1
    return hits/len(boxes)>=.8


def context_agrees(text, start, quote, prefix, suffix):
    """Require literal adjacent context; no case, punctuation or hyphen guessing."""
    before=text[max(0,start-40):start];after=text[start+len(quote):start+len(quote)+40]
    left=0;right=0
    for a,b in zip(reversed(before),reversed(prefix)):
        if a!=b:break
        left+=1
    for a,b in zip(after,suffix):
        if a!=b:break
        right+=1
    return (len(quote)>=12 and max(left,right)>=12) or left>=8 and right>=8


def validate_source(source, revision, manifest, pdf):
    bounded_json(source)
    if not isinstance(source,dict): raise AnchorError('缺少原始锚点。')
    if str(source.get('revision_id'))!=str(revision.id): raise AnchorError('批注所属修订不正确。')
    view=source.get('created_view');language=source.get('source_language');kind=source.get('kind')
    if view not in {'both','zh','en','pdf'} or language not in {'en','zh','shared','und'}:
        raise AnchorError('来源视图或语言无效。')
    segments=source.get('segments')
    if not isinstance(segments,list) or not 1<=len(segments)<=MAX_SEGMENTS:
        raise AnchorError('请选择 1—32 个连续内容片段。')
    cleaned={'schema_version':1,'revision_id':str(revision.id),'created_view':view,
             'source_language':language,'kind':kind,'segments':[],'offset_unit':'unicode_code_point',
             'normalization_version':NORMALIZATION}
    quote_length=0; seen=set(); last_order=(-1,-1)
    if view!='pdf':
        if kind not in {'text','object'}: raise AnchorError('HTML 批注类型无效。')
        if kind=='object' and language!='shared':raise AnchorError('对象批注使用共用内容单元。')
        if kind=='text' and (language not in {'en','zh'} or view in {'en','zh'} and view!=language):
            raise AnchorError('一次只能选择同一种语言的正文。')
        for segment in segments:
            if not isinstance(segment,dict): raise AnchorError('片段无效。')
            unit=manifest['units'].get(segment.get('unit_id'))
            if not unit: raise AnchorError('内容单元不属于当前论文修订。')
            if kind=='object':
                if len(segments)!=1: raise AnchorError('一次请选择一个段落或对象。')
                cleaned['segments'].append({'unit_id':unit['id'],'alignment_group_id':unit['alignment_group_id'],
                                            'label':unit['label'],'kind':unit['kind']})
                continue
            rid=segment.get('representation_id');rep=manifest['representations'].get(rid)
            if not rep or rep['unit_id']!=unit['id'] or rep['language']!=language or rid in seen:
                raise AnchorError('选区包含不同语言、重复片段或无效表示。')
            seen.add(rid)
            order=(unit['order'],unit['representations'].index(rid))
            if order<last_order: raise AnchorError('片段次序与正文不一致。')
            last_order=order
            if segment.get('text_hash')!=rep['text_hash'] or segment.get('normalization_version')!=NORMALIZATION:
                raise AnchorError('正文已变化，请刷新后重新选择。')
            start,end=segment.get('start'),segment.get('end');quote=segment.get('quote')
            if type(start)!=int or type(end)!=int or not 0<=start<end<=len(rep['text']):
                raise AnchorError('字符位置超出内容范围。')
            if not isinstance(quote,str) or rep['text'][start:end]!=quote:
                raise AnchorError('所选文字与源位置不一致。')
            if segment.get('contains_math') or any(start<b and end>a for a,b in rep.get('math_ranges',[])) or rep.get('contains_math') and 'math_ranges' not in rep:
                raise AnchorError('复杂公式请使用公式对象批注。')
            quote_length+=len(quote)
            cleaned['segments'].append({'unit_id':unit['id'],'alignment_group_id':unit['alignment_group_id'],
                'representation_id':rid,'quote':quote,'raw_quote':str(segment.get('raw_quote',quote)),
                'prefix':rep['text'][max(0,start-40):start],'suffix':rep['text'][end:end+40],
                'start':start,'end':end,'text_hash':rep['text_hash'],'normalization_version':NORMALIZATION})
    else:
        if kind not in {'pdf_text','pdf_page'} or not revision.pdf_sha256 or source.get('pdf_sha256')!=revision.pdf_sha256:
            raise AnchorError('PDF 来源文件不匹配。')
        if language not in {'en','und'}:raise AnchorError('PDF 原文来源语言无效。')
        if source.get('coordinate_system')!='pdf-user-space': raise AnchorError('PDF 坐标系不正确。')
        if not pdf.get('pages'): raise AnchorError('当前 PDF 无可靠文字／页面索引，暂不能创建定位批注。')
        cleaned.update(pdf_sha256=revision.pdf_sha256,coordinate_system='pdf-user-space',extractor_version=pdf['extractor_version'])
        last_page=-1
        for segment in segments:
            if not isinstance(segment,dict): raise AnchorError('PDF 片段格式无效。')
            page_index=segment.get('page_index')
            if type(page_index)!=int or not 0<=page_index<len(pdf['pages']) or page_index<=last_page:
                raise AnchorError('PDF 物理页索引或阅读次序无效。')
            last_page=page_index;page=pdf['pages'][page_index]
            if kind=='pdf_page':
                cleaned['segments'].append({'page_index':page_index,'page_label':page['page_label']});continue
            quote=normalize(segment.get('quote',''))
            if not quote or len(quote)>MAX_QUOTE: raise AnchorError('未选中可提取的 PDF 文字。')
            quads=segment.get('quads');validate_quads(quads,page)
            hits=[p for p in occurrences(page['text'],quote) if geometry_agrees(page,p,p+len(quote),quads)]
            if len(hits)!=1:
                raise AnchorError('PDF 文字与几何不能唯一对应；请缩小选区，或改用整页批注。')
            start=hits[0];end=start+len(quote);quote_length+=len(quote)
            cleaned['segments'].append({'page_index':page_index,'page_label':page['page_label'],
                'quote':quote,'raw_quote':segment.get('raw_quote',quote),'prefix':page['text'][max(0,start-40):start],
                'suffix':page['text'][end:end+40],'start':start,'end':end,'text_hash':page['text_hash'],
                'quads':quads_for(page,start,end)})
    if quote_length>MAX_QUOTE: raise AnchorError('总选区超过 20000 字，请分段批注。')
    return cleaned


def project(source, old_manifest, manifest, pdf, view):
    targets=[]; same=source['revision_id']==manifest['revision_id']
    is_pdf=source['created_view']=='pdf'
    if is_pdf:
        if source.get('pdf_sha256')!=manifest['pdf_sha256']:
            return [{'precision':'stale','reason':'原版 PDF 来源修订已改变。'}]
        if view=='pdf':
            return [{'precision':'exact' if source['kind']=='pdf_text' else 'page',
                     'method':'source-pdf-geometry','page_index':s['page_index'],
                     'quads':s.get('quads',[]),'reason':'同一源 PDF 的原始选区。'} for s in source['segments']]
        for segment in source['segments']:
            quote=segment.get('quote')
            if not quote:
                continue
            matches=[]
            for rid,rep in manifest['representations'].items():
                if rep['language']!='en': continue
                positions=occurrences(rep['text'],quote)
                # Repeated quotations are accepted only when the already-verified PDF range identifies a unit.
                for pos in positions:
                    ranges=rep.get('pdf',{}).get('fragments',[])
                    verified_range=any(f['page_index']==segment['page_index'] and f['start']<=segment['start'] and f['end']>=segment['end'] for f in ranges)
                    context_match=context_agrees(rep['text'],pos,quote,segment['prefix'],segment['suffix'])
                    if verified_range or context_match:
                        matches.append((rid,rep,pos))
            if len(matches)==1:
                rid,rep,pos=matches[0];unit=manifest['units'][rep['unit_id']]
                if view in {'both','en'}:
                    targets.append({'precision':'exact','language':'en','unit_id':unit['id'],
                        'representation_id':rid,'start':pos,'end':pos+len(quote),'quote':quote,'method':'unique-source-text-context'})
                if view in {'both','zh'} and any(manifest['representations'][r]['language']=='zh' for r in unit['representations']):
                    targets.append({'precision':'block','language':'zh','unit_id':unit['id'],'method':'bilingual-unit',
                                    'reason':'对应段落；原批注来自原版 PDF。'})
            else:
                # A multi-paragraph PDF selection can intersect several verified units.
                # Preserve those blocks, without claiming an exact HTML phrase.
                for unit in manifest['units'].values():
                    ranges=unit.get('pdf',{}).get('fragments',[])
                    if not any(f['page_index']==segment['page_index'] and f['start']<segment['end'] and f['end']>segment['start'] for f in ranges):
                        continue
                    for language in ('en','zh') if view=='both' else (view,):
                        if any(manifest['representations'][r]['language']==language for r in unit['representations']):
                            targets.append({'precision':'block','language':language,'unit_id':unit['id'],
                                            'method':'verified-pdf-range-overlap','reason':'原 PDF 选区覆盖此段；没有唯一短语对应。'})
    else:
        for segment in source['segments']:
            unit=manifest['units'].get(segment['unit_id'])
            if not unit:
                targets.append({'precision':'stale' if not same else 'unmapped','reason':'当前修订没有原内容单元。'});continue
            if source['kind']=='object':
                if unit['kind']=='note' and view=='en':
                    targets.append({'precision':'unmapped','reason':'此中文补充说明没有英文原文对应。'});continue
                old=old_manifest['units'].get(segment['unit_id'],{})
                if not same and (not old.get('fingerprint') or old.get('fingerprint')!=unit.get('fingerprint')):
                    targets.append({'precision':'stale','reason':'原对象内容已改变，待重新确认。'});continue
                if view=='pdf':
                    mapping=unit['pdf']
                    if mapping['precision']=='block':
                        targets.extend({'precision':'block','method':mapping['method'],**f,'reason':'对应原文内容单元。'} for f in mapping['fragments'])
                    elif mapping['precision']=='page':
                        targets.extend({'precision':'page','page_index':p,'reason':'仅定位到页。'} for p in mapping['pages'])
                    else: targets.append(mapping)
                else:
                    targets.append({'precision':'object' if unit['kind'] in {'figure','table','formula','object'} else 'block',
                                    'unit_id':unit['id'],'language':'shared','method':'canonical-object'})
                continue
            rep=manifest['representations'].get(segment['representation_id'])
            found=resolve_quote(rep['text'],segment['quote'],segment['prefix'],segment['suffix'],
                segment['start'] if same else None,segment['end'] if same else None) if rep else None
            if not found:
                targets.append({'precision':'stale' if not same else 'unmapped','reason':'原引用无法在当前修订唯一恢复。'});continue
            start,end=found
            if view=='pdf':
                quote_matches=[]
                if source['source_language']=='en' and rep.get('pdf',{}).get('precision')!='exact':
                    for page in pdf.get('pages',[]):
                        for pos in occurrences(page['text'],segment['quote']):
                            if context_agrees(page['text'],pos,segment['quote'],rep['text'][max(0,start-40):start],rep['text'][end:end+40]):
                                quote_matches.append((page,pos))
                if len(quote_matches)==1:
                    page,pos=quote_matches[0]
                    targets.append({'precision':'exact','page_index':page['page_index'],
                        'quads':quads_for(page,pos,pos+len(segment['quote'])),
                        'method':'unique-source-text-context','reason':'同源原文引用及相邻文字唯一匹配。'})
                    continue
                if source['source_language']=='en' and rep.get('pdf',{}).get('precision')=='exact':
                    remaining_start,remaining_end=start,end; consumed=0
                    for fragment in rep['pdf']['fragments']:
                        length=fragment['end']-fragment['start']
                        lo,hi=max(0,remaining_start-consumed),min(length,remaining_end-consumed)
                        if lo<hi:
                            page=pdf['pages'][fragment['page_index']]
                            targets.append({'precision':'exact','page_index':fragment['page_index'],
                                'quads':quads_for(page,fragment['start']+lo,fragment['start']+hi),
                                'method':'unique-equivalent-english-text','reason':'同源英文文字唯一匹配。'})
                        consumed+=length+1
                elif unit['pdf']['precision']=='block':
                    targets.extend({'precision':'block','method':unit['pdf']['method'],**f,
                        'reason':'对应段落；没有跨语言短语级对齐。'} for f in unit['pdf']['fragments'])
                elif unit['pdf']['precision']=='page':
                    targets.extend({'precision':'page','page_index':p,'reason':'仅定位到页。'} for p in unit['pdf']['pages'])
                else: targets.append(unit['pdf'])
                continue
            if view in {'both',source['source_language']}:
                targets.append({'precision':'exact','language':source['source_language'],'unit_id':unit['id'],
                    'representation_id':rep['id'],'start':start,'end':end,'quote':segment['quote'],
                    'method':'source-text' if same else 'unique-quote-context'})
            other='en' if source['source_language']=='zh' else 'zh'
            if view in {'both',other} and any(manifest['representations'][r]['language']==other for r in unit['representations']):
                targets.append({'precision':'block','language':other,'unit_id':unit['id'],'method':'bilingual-unit',
                                'reason':'对应段落；原批注来自'+('中文' if other=='en' else '英文')+'。'})
    if not targets: targets=[{'precision':'unmapped','reason':'当前视图未定位；可返回来源查看。'}]
    unique=[];seen=set()
    for target in targets:
        key=str(target)
        if key not in seen:unique.append(target);seen.add(key)
    return unique
