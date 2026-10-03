"""Isolated regression tests: actual PDF extraction, anchors, revisions and permissions."""
import copy
import json
import secrets
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings

from .anchors import AnchorError, project, validate_source
from .article import load_article
from .logical_text import normalize, normalized_map, resolve_quote
from .models import AnnotationAnchor, Comment, Paper, PaperRevision, Rating
from .pdf_index import quads_for
from .revisions import ensure_revision, file_hash, manifest_for, pdf_for, revision_dir
from .storage import publish, write_bundle
from .tests import MINI


def fixture_pdf(scanned=False):
    """A real, tiny two-page PDF with crop boxes, rotation, labels and repeated text."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R /PageLabels << /Nums [0 << /S /r >> 1 << /S /D /St 17 >>] >> >>',
               b'<< /Type /Pages /Kids [3 0 R 5 0 R] /Count 2 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 7 0 R >> >> /Contents 4 0 R >>',
               b'',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /CropBox [20 30 592 812] /Rotate 90 /Resources << /Font << /F1 7 0 R >> >> /Contents 6 0 R >>',
               b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    for index, text in [(3, b'Complete English paragraph.'), (5, b'Second page sentence.')]:
        stream = b'q .8 g 50 50 100 100 re f Q' if scanned else b'BT /F1 12 Tf 60 730 Td ('+text+b') Tj 0 -24 Td (repeat repeat) Tj ET'
        objects[index] = b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream'
    output = b'%PDF-1.7\n'; positions = [0]
    for number, obj in enumerate(objects, 1):
        positions.append(len(output)); output += f'{number} 0 obj\n'.encode()+obj+b'\nendobj\n'
    xref = len(output)
    output += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    output += b''.join(f'{p:010d} 00000 n \n'.encode() for p in positions[1:])
    output += f'trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF'.encode()
    return output


UNICODE_HTML = MINI.replace('</main>', '''<section class="unit paragraph" id="unicode"><div class="pair">
<div class="en"><p>A 🐈 <em>café</em> α H<sub>2</sub>O <sup>[2]</sup> repeat; repeat.</p></div>
<div class="zh"><p>中文🐈组合字符 café 与变量 α。</p></div></div></section>
<section class="unit paragraph" id="math"><div class="pair"><div class="en">Before <math><mi>x</mi><mo>=</mo><mn>1</mn></math> after.</div><div class="zh">式前 <math><mi>x</mi><mo>=</mo><mn>1</mn></math> 式后。</div></div></section></main>''')


class AnnotationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        cls.override = override_settings(DATA_DIR=cls.data)
        cls.override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass(); cls.override.disable(); cls.tmp.cleanup()

    @classmethod
    def setUpTestData(cls):
        cls.a = User.objects.create_user('annotation_a', password=secrets.token_urlsafe(20))
        cls.b = User.objects.create_user('annotation_b', password=secrets.token_urlsafe(20))
        cls.manager = User.objects.create_user('annotation_manager', is_staff=True, is_superuser=True)
        cls.p = cls.add_paper(UNICODE_HTML, fixture_pdf())
        cls.q = cls.add_paper(MINI.replace('Test paper','Another paper'))
        cls.rev = cls.p.current_revision
        cls.manifest = manifest_for(cls.rev)
        cls.pdf = pdf_for(cls.rev)

    @classmethod
    def add_paper(cls, html, pdf=None):
        raw = html.encode(); article = load_article(raw, pdf=pdf)
        folder = cls.data/'staging'/str(uuid.uuid4())
        write_bundle(folder, article, raw, pdf)
        return publish(folder, article, {'title_en':article['title_en'],'title_zh':article['title_zh']}, [], trusted=True)

    def setUp(self):
        self.ca=Client();self.ca.force_login(self.a)
        self.cb=Client();self.cb.force_login(self.b)
        self.cm=Client();self.cm.force_login(self.manager)
        self.base=f'/api/papers/{self.p.id}/'

    def source(self, unit='p1', language='zh', quote=None, view=None):
        unit='p-'+unit
        rid=f'{unit}::{language}::0';rep=self.manifest['representations'][rid]
        quote=quote or rep['text'][1:5];start=rep['text'].index(quote)
        return {'revision_id':str(self.rev.id),'created_view':view or language,'source_language':language,'kind':'text',
                'segments':[{'unit_id':unit,'representation_id':rid,'quote':quote,'start':start,'end':start+len(quote),
                             'text_hash':rep['text_hash'],'normalization_version':'nfc-whitespace-v1'}]}

    def send(self, source=None, client=None, key=None, body='A <script>only text</script>'):
        return (client or self.ca).post(self.base+'annotations/',json.dumps({'body':body,'source':source or self.source(),
                    'request_key':key or str(uuid.uuid4())}),content_type='application/json')

    def threads(self, view='both', client=None, revision=None):
        return (client or self.cb).get(self.base+'annotations/',{'view':view,'revision':str(revision or self.rev.id)}).json()

    def test_four_views_one_thread_and_replies(self):
        created=self.send();self.assertEqual(created.status_code,201,created.content)
        thread=created.json()['id']
        response=self.cb.post(self.base+'comments/',json.dumps({'body':'reply','parent':thread,'request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(response.status_code,201)
        for view in ['both','zh','en','pdf']:
            data=self.threads(view);self.assertEqual(data['count'],1)
            item=data['threads'][0];self.assertEqual(item['id'],thread);self.assertEqual(len(item['replies']),1)
            precision=[p['precision'] for p in item['projections']]
            self.assertIn('exact' if view in ['both','zh'] else 'block',precision)
            if view=='pdf':self.assertNotIn('exact',precision)
        self.assertEqual(self.ca.get(self.base+'comments/').json()['comments'],[])

    def test_en_pdf_bidirectional_exact_with_real_extracted_coordinates(self):
        source=self.source(language='en',quote='English paragraph')
        self.assertEqual(self.send(source).status_code,201)
        projection=self.threads('pdf')['threads'][0]['projections'][0]
        self.assertEqual(projection['precision'],'exact');self.assertTrue(projection['quads'])
        page=self.pdf['pages'][0];start=page['text'].index('English paragraph')
        pdf_source={'revision_id':str(self.rev.id),'created_view':'pdf','source_language':'en','kind':'pdf_text',
                    'pdf_sha256':self.rev.pdf_sha256,'coordinate_system':'pdf-user-space','segments':[
                    {'page_index':0,'quote':'English paragraph','quads':quads_for(page,start,start+17)}]}
        response=self.send(pdf_source);self.assertEqual(response.status_code,201,response.content)
        item=self.threads('en')['threads'][-1]
        self.assertEqual(item['projections'][0]['precision'],'exact')
        self.assertEqual(item['projections'][0]['quote'],'English paragraph')
        self.assertEqual(self.threads('zh')['threads'][-1]['projections'][0]['precision'],'block')

    def test_unicode_codepoints_inline_math_and_repeated_quote(self):
        for lang,quote in [('en','🐈 café α H2O [2]'),('zh','🐈组合字符 café')]:
            source=self.source('unicode',lang,quote)
            response=self.send(source);self.assertEqual(response.status_code,201,response.content)
            anchor=AnnotationAnchor.objects.get(pk=response.json()['id']).source['segments'][0]
            self.assertEqual(anchor['end']-anchor['start'],len(quote));self.assertEqual(anchor['quote'],quote)
        self.assertEqual(normalize(' e\u0301\n α\t🐈 '),'é α 🐈')
        for value in ['\u1100\u1161\u11a8', '\ufeffA\u00a0B ', '👩\u200d🔬 α\u0301', 'e\u0301']:
            self.assertEqual(normalized_map(value)[0],normalize(value))
        text,indices=normalized_map(' e\u0301\n α\t🐈 ');self.assertEqual(text,'é α 🐈');self.assertEqual(indices[0],[1,3])
        self.assertIsNone(resolve_quote('repeat; repeat.','repeat','',''))
        self.assertEqual(resolve_quote('repeat; repeat.','repeat','repeat; ','.'),(8,14))
        self.assertEqual(self.send(self.source('math','en','Before')).status_code,201)
        self.assertEqual(self.send(self.source('math','en','x=1')).status_code,400)

    def test_multisegment_language_and_scope_validation(self):
        source=self.source(language='en');source['segments'].extend(self.source('unicode','en')['segments'])
        self.assertEqual(self.send(source).status_code,201)
        for mutation in [lambda s:s['segments'].extend(self.source('unicode','en')['segments']),
                         lambda s:s['segments'][0].update(start=-1),lambda s:s['segments'][0].update(end=100000),
                         lambda s:s['segments'][0].update(quote='wrong'),lambda s:s['segments'][0].update(unit_id='../../private'),
                         lambda s:s.update(source_language='en'),lambda s:s['segments'][0].update(text_hash='0'*64)]:
            bad=self.source();mutation(bad);self.assertEqual(self.send(bad).status_code,400)
        foreign=self.source();foreign['revision_id']=str(self.q.current_revision_id)
        self.assertEqual(self.send(foreign).status_code,404)

    def test_pdf_hash_bounds_page_labels_and_ambiguity(self):
        self.assertEqual(self.pdf['pages'][0]['page_label'],'i')
        self.assertEqual(self.pdf['pages'][1]['page_label'],'17')
        self.assertEqual(self.pdf['pages'][1]['rotation'],90)
        page=self.pdf['pages'][0];start=page['text'].index('repeat')
        source={'revision_id':str(self.rev.id),'created_view':'pdf','source_language':'en','kind':'pdf_text',
                'pdf_sha256':self.rev.pdf_sha256,'coordinate_system':'pdf-user-space',
                'segments':[{'page_index':0,'quote':'repeat','quads':quads_for(page,start,start+6)}]}
        response=self.send(source);self.assertEqual(response.status_code,201,response.content)
        for mutate in [lambda s:s.update(pdf_sha256='f'*64),lambda s:s['segments'][0].update(page_index=2),
                       lambda s:s.update(segments=['invalid']),
                       lambda s:s['segments'][0].update(quads=[[-200,0,1,0,1,1,0,1]]),
                       lambda s:s['segments'][0].update(quads=[[0,842,612,842,612,0,0,0]])]:
            bad=copy.deepcopy(source);mutate(bad);self.assertEqual(self.send(bad).status_code,400)
        source['kind']='pdf_page';source['segments']=[{'page_index':1}]
        self.assertEqual(self.send(source).status_code,201)
        self.assertEqual(self.threads('pdf')['threads'][-1]['projections'][0]['precision'],'page')

    def test_retry_idempotency_database_failure_and_size_limits(self):
        key=str(uuid.uuid4());first=self.send(key=key)
        self.assertEqual(self.send(key=key).json()['id'],first.json()['id'])
        self.assertEqual(self.send(key=key,body='changed').status_code,409)
        with patch('library.annotation_views.AnnotationAnchor.objects.create',side_effect=DatabaseError('test rollback')):
            self.assertEqual(self.send().status_code,503)
        self.assertEqual(Comment.objects.count(),1);self.assertEqual(AnnotationAnchor.objects.count(),1)
        self.assertEqual(self.send(body='x'*5001).status_code,400)
        source=self.source();source['segments']*=33;self.assertEqual(self.send(source).status_code,400)

    def test_edit_conflict_hide_delete_permissions_and_reply_retention(self):
        root=self.send().json()['id'];path=self.base+f'comments/{root}/'
        self.assertEqual(self.cb.patch(path,json.dumps({'body':'stolen','version':1}),content_type='application/json').status_code,403)
        self.assertEqual(self.ca.patch(path,json.dumps({'body':'first','version':1}),content_type='application/json').status_code,200)
        self.assertEqual(self.ca.patch(path,json.dumps({'body':'stale','version':1}),content_type='application/json').status_code,409)
        self.assertEqual(Comment.objects.get(pk=root).body,'first')
        self.cb.post(self.base+'comments/',json.dumps({'body':'reply survives','parent':root,'request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(self.ca.post(path+'hide/',json.dumps({'hidden':True,'version':2}),content_type='application/json').status_code,403)
        self.assertEqual(self.cm.post(path+'hide/',json.dumps({'hidden':True,'version':2}),content_type='application/json').status_code,200)
        hidden=self.threads()['threads'][0];self.assertIsNone(hidden['body']);self.assertIsNone(hidden['source']);self.assertEqual(hidden['projections'],[])
        self.assertEqual(self.cm.post(path+'hide/',json.dumps({'hidden':False,'version':3}),content_type='application/json').status_code,200)
        self.assertEqual(self.ca.delete(path,json.dumps({'version':4}),content_type='application/json').status_code,200)
        deleted=self.threads()['threads'][0];self.assertIsNone(deleted['body']);self.assertEqual(len(deleted['replies']),1)

    def test_visibility_login_csrf_and_no_pdf(self):
        source=self.send().json()
        for path in [self.base+'annotations/',self.base+'representation/',f'/papers/{self.p.id}/revisions/{self.rev.id}/',
                     self.base+f'revisions/{self.rev.id}/pdf/']:
            self.p.visible=False;self.p.save(update_fields=['visible']);self.assertEqual(self.cb.get(path).status_code,404)
        self.p.visible=True;self.p.save(update_fields=['visible'])
        self.assertEqual(Client().get(self.base+'annotations/').status_code,401)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.a)
        self.assertEqual(self.send(client=strict).status_code,403)
        self.assertContains(self.ca.get(f'/papers/{self.q.id}/'),'未提供原版 PDF')
        self.assertEqual(self.ca.get(f'/api/papers/{self.q.id}/revisions/{self.q.current_revision_id}/pdf/').status_code,404)

    def test_revision_stability_relocation_stale_and_snapshot_access(self):
        unchanged=self.send(self.source(language='en',quote='English paragraph')).json()['id']
        changed=self.send(self.source(language='zh',quote='完整中文')).json()['id']
        old_hash=file_hash(revision_dir(self.rev)/'reader.html')
        self.assertEqual(ensure_revision(self.p).id,self.rev.id)
        # CSS and scripts in the raw translation do not enter the sanitized scientific body.
        styled=UNICODE_HTML.replace('</head>','<style>.pair{color:red}</style></head>')
        article=load_article(styled.encode(),pdf=fixture_pdf());folder=self.data/'staging'/str(uuid.uuid4())
        write_bundle(folder,article,styled.encode(),fixture_pdf())
        self.assertEqual(ensure_revision(self.p,folder).id,self.rev.id)
        revised=UNICODE_HTML.replace('完整中文段落。','修正后的中文段落。').replace('Complete English','New prefix. Complete English')
        article=load_article(revised.encode(),pdf=fixture_pdf());folder=self.data/'staging'/str(uuid.uuid4())
        write_bundle(folder,article,revised.encode(),fixture_pdf());revision=ensure_revision(self.p,folder)
        self.assertNotEqual(revision.id,self.rev.id)
        items={t['id']:t for t in self.threads('both',revision=revision.id)['threads']}
        self.assertIn('exact',[p['precision'] for p in items[unchanged]['projections']])
        self.assertEqual(items[changed]['projections'][0]['precision'],'stale')
        self.assertEqual(file_hash(revision_dir(self.rev)/'reader.html'),old_hash)
        self.assertEqual(self.ca.get(items[changed]['source_url']).status_code,200)

    def test_integrity_error_never_reuses_replaced_pdf(self):
        target=revision_dir(self.rev)/'original.pdf';original=target.read_bytes()
        try:
            target.write_bytes(original+b'\nreplacement')
            response=self.ca.get(self.base+f'revisions/{self.rev.id}/pdf/')
            self.assertEqual(response.status_code,409)
            self.assertIn('来源校验失败',response.json()['error'])
        finally:target.write_bytes(original)

    def test_incremental_poll_returns_reply_changed_thread(self):
        root=self.send().json()['id'];cursor=self.threads()['cursor']
        self.assertEqual(self.cb.get(self.base+'annotations/',{'since':cursor}).json()['threads'],[])
        self.cb.post(self.base+'comments/',json.dumps({'body':'new reply','parent':root,'request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(self.cb.get(self.base+'annotations/',{'since':cursor}).json()['threads'][0]['id'],root)

    def test_subrange_context_alignment_and_ambiguity(self):
        manifest=copy.deepcopy(self.manifest)
        rep=manifest['representations']['p-p1::en::0'];rep.pop('pdf',None)
        manifest['units']['p-p1']['pdf']={'precision':'page','pages':[0],'method':'verified-hint'}
        source=validate_source(self.source(language='en',quote='English'),self.rev,self.manifest,self.pdf)
        target=project(source,self.manifest,manifest,self.pdf,'pdf')[0]
        self.assertEqual(target['precision'],'exact');self.assertEqual(target['method'],'unique-source-text-context')
        page=self.pdf['pages'][0];start=page['text'].index('English')
        reverse=validate_source({'revision_id':str(self.rev.id),'created_view':'pdf','source_language':'en','kind':'pdf_text',
            'pdf_sha256':self.rev.pdf_sha256,'coordinate_system':'pdf-user-space','segments':[{'page_index':0,'quote':'English',
            'quads':quads_for(page,start,start+7)}]},self.rev,self.manifest,self.pdf)
        self.assertEqual(project(reverse,self.manifest,manifest,self.pdf,'en')[0]['precision'],'exact')
        manifest['representations']['duplicate']=copy.deepcopy(rep)
        self.assertNotIn('exact',[p['precision'] for p in project(reverse,self.manifest,manifest,self.pdf,'en')])

    def test_translator_note_has_no_fabricated_english_or_pdf_target(self):
        paper=self.add_paper(MINI.replace('</main>','<blockquote class="ai-note">[AI补充] 仅在译文中提供的说明。</blockquote></main>'))
        manifest=manifest_for(paper.current_revision)
        unit=next(u for u in manifest['units'].values() if u['kind']=='note')
        rep=manifest['representations'][unit['representations'][0]]
        source={'revision_id':str(paper.current_revision_id),'created_view':'zh','source_language':'zh','kind':'text',
                'segments':[{'unit_id':unit['id'],'representation_id':rep['id'],'start':0,'end':6,'quote':rep['text'][:6],
                             'text_hash':rep['text_hash'],'normalization_version':'nfc-whitespace-v1'}]}
        source=validate_source(source,paper.current_revision,manifest,{'pages':[]})
        self.assertEqual(project(source,manifest,manifest,{'pages':[]},'zh')[0]['precision'],'exact')
        for view in ['en','pdf']:self.assertEqual(project(source,manifest,manifest,{'pages':[]},view)[0]['precision'],'unmapped')

    def test_scan_without_text_allows_only_page_anchor(self):
        paper=self.add_paper(MINI.replace('Test paper','Scanned source'),fixture_pdf(scanned=True))
        revision=paper.current_revision;manifest=manifest_for(revision);pdf=pdf_for(revision)
        self.assertEqual(pdf['pages'][0]['text'],'')
        source={'revision_id':str(revision.id),'created_view':'pdf','source_language':'und','kind':'pdf_page',
                'pdf_sha256':revision.pdf_sha256,'coordinate_system':'pdf-user-space','segments':[{'page_index':0}]}
        self.assertEqual(validate_source(source,revision,manifest,pdf)['kind'],'pdf_page')
        source['kind']='pdf_text';source['segments'][0].update(quote='guessed OCR',quads=[[50,100,150,100,150,50,50,50]])
        with self.assertRaises(AnchorError):validate_source(source,revision,manifest,pdf)

    def test_object_full_fingerprint_and_removed_unit_are_stale(self):
        source=validate_source({'revision_id':str(self.rev.id),'created_view':'both','source_language':'shared','kind':'object',
                               'segments':[{'unit_id':'p-p1'}]},self.rev,self.manifest,self.pdf)
        manifest=copy.deepcopy(self.manifest);manifest['revision_id']=str(uuid.uuid4())
        manifest['units']['p-p1']['fingerprint']='changed after first one hundred characters'
        self.assertEqual(project(source,self.manifest,manifest,self.pdf,'both')[0]['precision'],'stale')
        manifest['units'].pop('p-p1')
        self.assertEqual(project(source,self.manifest,manifest,self.pdf,'both')[0]['precision'],'stale')

    def test_deleted_and_hidden_thread_count_projection_and_source_access(self):
        from .views import aggregates
        first=self.send(body='删除根线程').json()['id']
        root=Comment.objects.get(pk=first);root.deleted=True;root.body='';root.save()
        result=self.threads();self.assertEqual(result['count'],0);self.assertIn(first,result['removed_ids'])
        self.assertEqual(aggregates(Paper.objects.filter(pk=self.p.pk)).get().annotation_count,0)
        self.assertEqual(self.ca.get(f'/papers/{self.p.pk}/revisions/{self.rev.pk}/?thread={first}&view=zh').status_code,404)
        Comment.objects.create(paper=self.p,user=self.b,parent=root,body='仍然可见的回复',request_key=uuid.uuid4(),request_hash='b'*64)
        result=self.threads();self.assertEqual(result['count'],1);self.assertIsNone(result['threads'][0]['body'])
        self.assertIsNotNone(result['threads'][0]['source'])
        root.hidden=True;root.save();result=self.threads()['threads'][0]
        self.assertIsNone(result['source']);self.assertIsNone(result['source_url']);self.assertEqual(result['projections'],[])
        self.assertEqual(self.ca.get(f'/papers/{self.p.pk}/revisions/{self.rev.pk}/?thread={first}&view=zh').status_code,404)

    def test_source_segment_cross_paper_missing_pdf_and_incremental_removal(self):
        created=self.send().json()['id'];before=self.threads()
        url=before['threads'][0]['source_url']
        self.assertEqual(self.ca.get(url+'&segment=55').status_code,404)
        self.assertEqual(self.ca.get(url.replace(str(self.p.pk),str(self.q.pk))).status_code,404)
        self.assertEqual(self.ca.get(f'/papers/{self.q.pk}/?view=pdf').status_code,404)
        root=Comment.objects.get(pk=created);root.hidden=True;root.save()
        result=self.ca.get(self.base+'annotations/',{'view':'zh','since':before['cursor']}).json()
        self.assertEqual(result['removed_ids'],[created]);self.assertEqual(result['threads'],[])
        response=self.ca.post(self.base+'comments/',json.dumps({'body':'reply','parent':created,'request_key':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(response.status_code,403)

    def test_every_projection_retains_its_source_segment_without_mutation(self):
        source=self.source('p1','en')
        source['segments']+=self.source('unicode','en',quote='🐈')['segments']
        created=self.send(source);self.assertEqual(created.status_code,201,created.content)
        anchor=AnnotationAnchor.objects.get(comment_id=created.json()['id'])
        original=json.dumps(anchor.source,sort_keys=True)
        for view in ['both','en','zh','pdf']:
            projections=self.threads(view)['threads'][0]['projections']
            self.assertEqual({p['source_segment_index'] for p in projections},{0,1})
            if view=='both':
                for index in (0,1):
                    self.assertEqual({p['precision'] for p in projections if p['source_segment_index']==index},{'exact','block'})
        anchor.refresh_from_db();self.assertEqual(json.dumps(anchor.source,sort_keys=True),original)

    def test_pdf_read_download_and_html_download_have_distinct_headers(self):
        read=self.ca.get(self.base+f'revisions/{self.rev.id}/pdf/')
        self.assertEqual(read.status_code,200);self.assertEqual(read['Content-Type'],'application/pdf')
        self.assertTrue(read['Content-Disposition'].startswith('inline'))
        read.close()
        for name in ['original.pdf','original.html']:
            from django.urls import reverse
            response=self.ca.get(reverse('revision-file',args=[self.p.pk,self.rev.pk,name]))
            self.assertEqual(response.status_code,200)
            self.assertTrue(response['Content-Disposition'].startswith('attachment'))
            self.assertIn('sandbox',response['Content-Security-Policy']);response.close()

    def test_pdf_missing_and_absent_return_actionable_errors(self):
        from .revisions import revision_dir
        self.assertEqual(self.ca.get(f'/api/papers/{self.q.pk}/revisions/{self.q.current_revision_id}/pdf/').status_code,404)
        file=revision_dir(self.rev)/'original.pdf';original=file.read_bytes()
        try:
            file.unlink()
            result=self.ca.get(self.base+f'revisions/{self.rev.id}/pdf/')
            self.assertEqual(result.status_code,404);self.assertIn('不可访问',result.json()['error'])
        finally:file.write_bytes(original)
