"""Bounded structural import. Input scripts/CSS are never trusted site code."""
import base64
import binascii
import hashlib
import io
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString
from PIL import Image

MIB = 1024**2
Image.MAX_IMAGE_PIXELS = 40_000_000
HTML_TAGS = set('main header footer section article div span p a aside details summary nav figure figcaption img table thead tbody tfoot tr td th colgroup col h1 h2 h3 h4 h5 h6 ul ol li dl dt dd strong b em i u s sub sup code pre blockquote br hr small'.split())
MATH_TAGS = set('math semantics mrow mi mn mo mtext mfrac msub msup msubsup mover munder munderover mtable mtr mtd mspace mstyle annotation msqrt mroot menclose mpadded mphantom mmultiscripts mprescripts none'.split())
MATH_ATTRS = set('display xmlns mathvariant form stretchy accent accentunder fence separator lspace rspace width height depth displaystyle scriptlevel columnalign rowalign columnspacing rowspacing columnspan rowspan encoding linethickness notation'.split())
CLASSES = set('ai-note authors basis cell-zh check-table column-head cover doi en equation equation-line equation-math equation-number equation-shared-note eyebrow figure-labels heading item layout-note numeric orcid pair paragraph reader-update reading-note reference shared-figure shared-table source subhead summary-data table-scroll toc unit zh caption caption-wrap column-labels contents edition edition-label heading-pair nomenclature nomenclature-list original-figure publication source-table table-wrap verification paper'.split())
DROP = set('script style iframe object embed base meta link form input button textarea select option audio video source track canvas template noscript'.split())

class FormatError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f'{code}：{message}')

def digest(data): return hashlib.sha256(data).hexdigest()
def norm(text): return ' '.join(text.split())
def effective(tag):
    return norm(''.join(x for x in tag.strings if x.parent.name not in {'annotation', 'script', 'style'}))

class ComplexityGuard(HTMLParser):
    def __init__(self): super().__init__(); self.nodes = 0; self.stack = []
    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 180000 or len(attrs) > 40:
            raise FormatError('FMT_LIMIT', '节点或属性过多。')
        if tag not in {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}:
            self.stack.append(tag)
        if len(self.stack) > 100:
            raise FormatError('FMT_LIMIT', '嵌套层数超过 100。')
    def handle_endtag(self, tag):
        if tag in self.stack:
            idx = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[idx:]

def decode_image(tag):
    source = tag.get('src', '')
    match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\s]+)', source, re.I)
    if not match:
        raise FormatError('FMT_RESOURCE', f'图片 {tag.get("alt", "未命名")[:100]} 必须内嵌 PNG/JPEG/WebP。')
    try:
        data = base64.b64decode(re.sub(r'\s', '', match[2]), validate=True)
        if len(data) > 20*MIB: raise FormatError('FMT_LIMIT', '单张图片超过 20 MiB。')
        with Image.open(io.BytesIO(data)) as im:
            if im.width*im.height > 40_000_000: raise FormatError('FMT_LIMIT', '单张图片超过 4000 万像素。')
            if im.format.lower() != match[1].lower(): raise ValueError('type')
            im.verify()
        with Image.open(io.BytesIO(data)) as im: im.load()
    except FormatError: raise
    except (ValueError, OSError, binascii.Error, Image.DecompressionBombError) as exc:
        raise FormatError('FMT_RESOURCE', '图片数据损坏或真实格式不符。') from exc
    return data, match[1].lower()

def math_tree(tag):
    return [tag.name, sorted((k, str(v)) for k,v in tag.attrs.items() if k in MATH_ATTRS),
            [math_tree(c) if getattr(c,'name',None) else norm(str(c)) for c in tag.children
             if getattr(c,'name',None) or norm(str(c))]]

def fingerprint(main):
    """All ordered bilingual text, every math tree and every table cell, not just counts."""
    math = [math_tree(x) for x in main.find_all('math')]
    tables = [[[[(c.name, c.get('rowspan','1'), c.get('colspan','1'), effective(c))
                 for c in row.find_all(['td','th'], recursive=False)]
                for row in t.find_all('tr')], len(t.find_all('col'))] for t in main.find_all('table')]
    pairs = [[effective(x) for x in p.find_all(recursive=False) if 'en' in x.get('class',[]) or 'zh' in x.get('class',[])] for p in main.select('.pair')]
    images = [digest(decode_image(x)[0]) for x in main.find_all('img')]
    objects = {kind: [x.get('id') for x in main.select(selector)] for kind,selector in {
        'equations': '.equation', 'references': '.reference',
        'figures': '.shared-figure, .caption-wrap[id^="figure-"]',
        'tables': '.shared-table, .caption-wrap[id^="table-"]'}.items()}
    values = {'text':effective(main), 'pairs':pairs, 'math':math, 'tables':tables, 'images':images, 'objects':objects}
    return {k: digest(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()) for k,v in values.items()}

def load_article(raw, filename='article.html', mapping=None, pdf=None):
    if not filename.lower().endswith('.html'):
        raise FormatError('FMT_FILE', '只接受标准双语 .html 文件。')
    if len(raw) > 50*MIB: raise FormatError('FMT_LIMIT', 'HTML 超过 50 MiB。')
    try: text = raw.decode('utf-8-sig')
    except UnicodeError as exc: raise FormatError('FMT_FILE', 'HTML 必须使用 UTF-8 编码。') from exc
    guard = ComplexityGuard(); guard.feed(text)
    soup = BeautifulSoup(text, 'html5lib')
    if soup.select('meta[name="paper-library-template"][content="incomplete"]') or '【待替换】' in text:
        raise FormatError('FMT_TEMPLATE', '仍有未完成标记或【待替换】内容。')
    mains = soup.find_all('main')
    if len(mains) != 1: raise FormatError('FMT_PROFILE', '必须且只能有一个 main 正文。')
    main = mains[0]
    if main.get('id') == 'top' and main.select('.unit.paragraph, .unit.heading'):
        profile = 'idaes-pair-v1'; heading_selector = '.unit.heading'
    elif 'paper' in main.get('class',[]) and main.select('.paragraph') and main.select('.heading-pair'):
        profile = 'ammonia-pair-v2'; heading_selector = '.heading-pair'
    else: raise FormatError('FMT_PROFILE', '未识别为 IDAES 或 ammonia 双语结构。')
    if main.find(['svg', 'annotation-xml']):
        raise FormatError('FMT_RESOURCE', '不支持 SVG 或主动 MathML 扩展。')
    pairs = main.select('.pair')
    if not pairs: raise FormatError('FMT_PAIR', '缺少英中对照段落。')
    for i,p in enumerate(pairs):
        children = p.find_all(recursive=False)
        en = [x for x in children if 'en' in x.get('class',[])]
        zh = [x for x in children if 'zh' in x.get('class',[])]
        location = p.get('id') or (p.find_parent(id=True) or {}).get('id') or f'pair-{i+1}'
        if len(en)!=1 or len(zh)!=1 or len(children)!=2 or en[0] is zh[0] or not effective(en[0]) or not effective(zh[0]):
            raise FormatError('FMT_PAIR', f'{location} 需要各一个非空英文栏和中文栏。')
    if not re.search(r'[\u3400-\u9fff]', ' '.join(effective(p.select_one('.zh')) for p in pairs)) or not re.search(r'[A-Za-z]', ' '.join(effective(p.select_one('.en')) for p in pairs)):
        raise FormatError('FMT_PAIR', '未识别到完整的英文与中文双语内容。')
    for p in main.select('.paragraph, '+heading_selector):
        if not p.get('id') or not p.select('.pair'):
            raise FormatError('FMT_ID', '段落／标题缺少 ID 或双语对照。')
    ids = [x['id'] for x in [main]+main.select('[id]') if x.get('id')]
    if len(ids)!=len(set(ids)): raise FormatError('FMT_ID', '正文存在重复 ID。')
    if any(not re.fullmatch(r'[\w.:-]{1,200}',x) for x in ids):
        raise FormatError('FMT_ID', 'ID 含不支持字符。')
    for obj in main.select('.shared-figure, .shared-table, .caption-wrap, .reference'):
        if not obj.get('id'):raise FormatError('FMT_ID', '图、编号表或参考文献缺少 ID。')
    for figure in main.select('.shared-figure'):
        if not figure.find('img') or not figure.select_one('.pair') or not figure.select_one('.figure-labels'):
            raise FormatError('FMT_RESOURCE', f'{figure["id"]} 缺少原图、双语图注或图内文字对照。')
    for figure in main.select('.original-figure'):
        caption=figure.find_next(class_='caption-wrap')
        if not figure.find('img') or not caption or not caption.get('id','').startswith('figure-') or not caption.select_one('.pair'):
            raise FormatError('FMT_RESOURCE', '原图缺少对应的双语 figure 图注。')
    for eq in main.select('.equation'):
        if not eq.get('id') or not eq.select_one('.equation-math math') or not eq.select_one('.equation-number') or not eq.select_one('.equation-shared-note'):
            raise FormatError('FMT_MATH', f'{eq.get("id", "未编号公式")} 缺少数学体、编号或中文共用说明。')
        if not effective(eq.select_one('.equation-number')) or not re.search(r'[\u3400-\u9fff]',effective(eq.select_one('.equation-shared-note'))):
            raise FormatError('FMT_MATH', f'{eq["id"]} 编号或说明为空。')
    for s in main.find_all(string=True):
        if s.parent.name not in {'annotation','code','script','style'} and re.search(r'\\\(|\\\[|\$\$', str(s)):
            raise FormatError('FMT_MATH', '正文存在未渲染 LaTeX。')
    if pdf is not None and (len(pdf)>100*MIB or not pdf.startswith(b'%PDF-')):
        raise FormatError('FMT_FILE', '附加 PDF 格式或大小不符。')
    map_count = 0
    if mapping is not None:
        if len(mapping)>5*MIB: raise FormatError('FMT_LIMIT', '映射超过 5 MiB。')
        try:
            obj = json.loads(mapping.decode('utf-8-sig'))
            entries = obj if isinstance(obj,list) else obj['paragraphs']
            if not isinstance(entries,list): raise ValueError()
            if not entries:raise ValueError()
            for entry in entries:
                if not isinstance(entry,dict):raise ValueError()
                expected={'id':str,'kind':str,'source':list,'en':str,'zh':str} if isinstance(obj,list) else {'id':str,'kind':str,'section':str,'source':str,'source_ast_range':list,'equations':list,'english_fragments':list,'chinese_fragments':list}
                if any(not isinstance(entry.get(k),typ) for k,typ in expected.items()):raise ValueError()
            if isinstance(obj,dict) and (not isinstance(obj.get('source_file'),str) or not re.fullmatch(r'[a-fA-F0-9]{64}',obj.get('source_sha256',''))):raise ValueError()
            map_ids = [x['id'] for x in entries]
            if len(map_ids)!=len(set(map_ids)) or not set(map_ids)<=set(ids): raise ValueError()
            if any(not isinstance(x,dict) or not isinstance(x.get('kind'),str) for x in entries): raise ValueError()
            if isinstance(obj,dict) and pdf is not None and obj.get('source_sha256') and obj['source_sha256']!=digest(pdf): raise ValueError()
            map_count=len(entries)
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise FormatError('FMT_MAP', '映射结构、唯一 ID、正文定位或 PDF 哈希不符。') from exc
    images = [decode_image(x) for x in main.find_all('img')]
    if sum(len(d) for d,_ in images)>120*MIB: raise FormatError('FMT_LIMIT', '图片总量超过 120 MiB。')
    # Drop executable material before the scientific fidelity baseline.
    for tag in list(main.find_all(DROP)): tag.decompose()
    before = fingerprint(main)
    footer = soup.find('footer')
    attribution = effective(footer) if footer and footer not in main.descendants else ''
    for comment in main.find_all(string=lambda s:isinstance(s,Comment)): comment.extract()
    for tag in [main]+list(main.find_all()):
        if tag.name not in HTML_TAGS | MATH_TAGS:
            raise FormatError('FMT_SANITIZE_LOSS', f'不支持的正文元素 {tag.name}，请先转为标准格式。')
        old = dict(tag.attrs); tag.attrs.clear()
        if old.get('id'): tag['id']=old['id']
        classes = [x for x in old.get('class',[]) if x in CLASSES]
        if classes: tag['class']=classes
        for key in ['lang','title','data-source','data-parent']:
            if key in old: tag[key]=str(old[key])[:2000]
        if tag.name in MATH_TAGS:
            for key in MATH_ATTRS:
                if key in old and re.fullmatch(r'[A-Za-z0-9 .,:/#%+()_\-]*',str(old[key])):
                    tag[key]=old[key]
            if tag.name=='annotation' and (tag.find() or old.get('encoding') not in {'application/x-tex','text/latex'}):
                raise FormatError('FMT_MATH','仅允许纯文本 LaTeX annotation。')
        if tag.name in {'td','th','col'}:
            for key in ['colspan','rowspan','span']:
                if key in old and re.fullmatch(r'\d{1,3}',str(old[key])): tag[key]=str(old[key])
        if tag.name=='img': tag['src']=old['src']; tag['alt']=str(old.get('alt','论文图片'))[:1000]
        if tag.name=='a' and old.get('href'):
            href=str(old['href']).strip()
            if href.startswith('#') and href[1:] in ids: tag['href']=href
            elif urlsplit(href).scheme.lower() in {'https','http'} and not re.search(r'[\x00-\x20]',href):
                tag['href']=href; tag['rel']='noopener noreferrer'; tag['target']='_blank'
        for part in old.get('style','').split(';'):
            if ':' not in part: continue
            key,val=(x.strip().lower() for x in part.split(':',1))
            extra=None
            if key=='width' and re.fullmatch(r'\d{1,3}%',val) and int(val[:-1])<=100: extra='width-'+val[:-1]
            if key=='text-align' and val in {'left','right','center'}: extra='align-'+val
            if extra: tag['class']=tag.get('class',[])+[extra]
    after = fingerprint(main)
    if before!=after: raise FormatError('FMT_SANITIZE_LOSS', '清理前后文本／数学／图像／表格比对不一致。')
    if attribution:
        f=soup.new_tag('footer'); f.string=attribution; main.append(f)
    title_pair = main.select_one('header .pair') if profile=='idaes-pair-v1' else main.select_one('.heading-pair .pair')
    titles = {lang:effective(title_pair.select_one('.'+lang)) if title_pair else '' for lang in ['en','zh']}
    for tag in [main]+main.select('[id]'):
        if tag.get('id'): tag['id']='p-'+tag['id']
    for a in main.select('a[href^="#"]'): a['href']='#p-'+a['href'][1:]
    for tag in main.select('[data-parent]'): tag['data-parent']='p-'+tag['data-parent']
    for n,im in enumerate(main.find_all('img')): im['src']=f'@@IMAGE:{n}@@'
    nav={}
    for kind,selector in {'sections':heading_selector, 'figures':'.shared-figure, .caption-wrap[id^="p-figure-"]',
                          'tables':'.shared-table, .caption-wrap[id^="p-table-"]','equations':'.equation'}.items():
        nav[kind]=[{'id':x['id'],'label':effective(x.select_one('.zh') or x.select_one('.equation-number') or x)[:140]} for x in main.select(selector) if x.get('id')]
    counts={'pairs':len(pairs),'paragraphs':len(main.select('.paragraph')),'images':len(images),
            'mathml':len(main.find_all('math')),'equations':len(nav['equations']), 'figures':len(nav['figures']),
            'tables':len(nav['tables']), 'table_blocks':len(main.find_all('table')),'references':len(main.select('.reference')),'map_entries':map_count}
    body=str(main)
    doi=next((a.get('href','') for a in main.find_all('a') if a.get('href','').startswith('https://doi.org/')),'')
    return {'body':body,'images':images,'nav':nav,'title_en':titles['en'],'title_zh':titles['zh'],
            'source_url':doi,
            'profile':profile,'raw_hash':digest(raw),'content_hash':digest(body.encode()),
            'validation':{'counts':counts,'fidelity_before':before,'fidelity_after':after,'fidelity':'PASS','attribution':attribution}}
