import base64
import io
import json
import secrets
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from PIL import Image
from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError,transaction
from django.test import TestCase,Client,SimpleTestCase,override_settings
from .models import Paper,Category,Rating,Comment
from .article import load_article,FormatError,ComplexityGuard
from .storage import write_bundle,publish,paper_dir
from .legacy import migrate_importance_rows

MINI='''<!doctype html><html><head><meta charset="utf-8"></head><body><main id="top"><header><div class="pair"><div class="en"><h2>Test paper</h2></div><div class="zh"><h2>格式测试论文</h2></div></div></header><section class="unit heading" id="h1"><div class="pair"><div class="en">Introduction</div><div class="zh">引言</div></div></section><section class="unit paragraph" id="p1"><div class="pair"><div class="en"><p>Complete English paragraph.</p></div><div class="zh"><p>完整中文段落。</p></div></div></section></main></body></html>'''

def make_paper(title='P'):
    return Paper.objects.create(title_en=title,title_zh=title+'论文',raw_hash=uuid.uuid4().hex,content_hash='a'*64,profile='idaes-pair-v1')

class CollaborationTests(TestCase):
    def setUp(self):
        self.a=User.objects.create_user('alpha',password=secrets.token_urlsafe(18))
        self.b=User.objects.create_user('beta',password=secrets.token_urlsafe(18))
        self.admin=User.objects.create_user('manager',is_staff=True,is_superuser=True)
        self.ca=Client();self.ca.force_login(self.a);self.cb=Client();self.cb.force_login(self.b)
        self.p=make_paper();self.q=make_paper('Q');self.base=f'/api/papers/{self.p.id}/'
    def put(self,client,dim,value):return client.put(self.base+'ratings/'+dim+'/',json.dumps({'value':value}),content_type='application/json')
    def vote(self):return self.ca.get(self.base+'ratings/').json()
    def post(self,client,body='comment',parent=None,key=None,paper=None):
        return client.post(f'/api/papers/{paper or self.p.id}/comments/',json.dumps({'body':body,'parent':parent,'request_key':key or str(uuid.uuid4())}),content_type='application/json')
    def test_C01_C13_full_independent_score_sequence(self):
        steps=[(None,None,None,(None,0,None,0)),(self.ca,'interesting',5,(5,1,None,0)),(self.cb,'interesting',4,(4.5,2,None,0)),
         (self.ca,'importance',3,(4.5,2,3,1)),(self.cb,'importance',5,(4.5,2,4,2)),(self.ca,'interesting',2,(3,2,4,2)),
         (self.cb,'interesting',None,(2,1,4,2)),(self.ca,'importance',None,(2,1,5,1)),(self.ca,'interesting',1,(1,1,5,1)),
         (self.ca,'interesting',None,(None,0,5,1)),(self.cb,'importance',None,(None,0,None,0))]
        for client,dim,value,expected in steps:
            if client:
                r=self.put(client,dim,value) if value is not None else client.delete(self.base+'ratings/'+dim+'/',data='{}',content_type='application/json')
                self.assertEqual(r.status_code,200)
            d=self.vote();self.assertEqual((d['interesting']['average'],d['interesting']['count'],d['importance']['average'],d['importance']['count']),expected)
        self.put(self.ca,'interesting',4);self.put(self.ca,'interesting',4)
        self.assertEqual(Rating.objects.count(),1)
        for _ in range(2):self.assertEqual(self.ca.delete(self.base+'ratings/importance/',data='{}',content_type='application/json').status_code,200)
    def test_C14_C15_invalid_spoof_csrf_and_db_checks(self):
        for value in [0,6,2.5,True,None,'3']:
            self.assertEqual(self.put(self.ca,'interesting',value).status_code,400)
        self.assertEqual(self.put(self.ca,'overall',5).status_code,400)
        self.assertEqual(self.ca.put(self.base+'ratings/interesting/',json.dumps({'value':3,'user_id':self.b.id}),content_type='application/json').status_code,400)
        self.assertEqual(Client().put(self.base+'ratings/interesting/',data='{}',content_type='application/json').status_code,401)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.a)
        self.assertEqual(strict.put(self.base+'ratings/interesting/',data='{"value":3}',content_type='application/json').status_code,403)
        for dim,val in [('interesting',0),('fake',4),('importance',6)]:
            with self.assertRaises(IntegrityError),transaction.atomic():Rating.objects.create(paper=self.p,user=self.a,dimension=dim,value=val)
    def test_C16_D01_aggregation_search_and_counts(self):
        c1=Category.objects.create(name='仿真');c2=Category.objects.create(name='AI');self.p.categories.set([c1,c2])
        self.put(self.ca,'interesting',5);self.put(self.cb,'interesting',4)
        root=self.post(self.ca).json()['id'];self.post(self.cb,parent=root);self.post(self.cb)
        from .views import aggregates
        p=aggregates(Paper.objects.filter(id=self.p.id)).get()
        self.assertEqual((p.interesting_avg,p.interesting_count,p.comment_count),(4.5,2,3))
        for params in [{'q':'论文','category':c1.id},{'q':'p'},{'q':'P','category':c2.id}]:
            response=self.ca.get('/',params);self.assertEqual(response.status_code,200)
            self.assertEqual([x.id for x in response.context['page']], [self.p.id])
    def test_C17_precise_sort_counts_and_pagination(self):
        papers=[make_paper('Sort'+str(i)) for i in range(24)]
        users=[User.objects.create_user('v'+str(i)) for i in range(25)]
        # Same displayed one decimal: 4.04 sorts above 4.00 even with fewer votes.
        for u in users:Rating.objects.create(paper=papers[0],user=u,dimension='interesting',value=4)
        for i,u in enumerate(users):Rating.objects.create(paper=papers[1],user=u,dimension='interesting',value=5 if i==0 else 4)
        Rating.objects.create(paper=papers[2],user=users[0],dimension='interesting',value=4)
        Rating.objects.create(paper=papers[3],user=users[0],dimension='importance',value=5)
        page=self.ca.get('/',{'sort':'interesting'}).context['page']
        self.assertEqual([p.id for p in page][:3],[papers[1].id,papers[0].id,papers[2].id])
        self.assertEqual(self.ca.get('/',{'sort':'importance'}).context['page'][0].id,papers[3].id)
        allids=[p.id for p in page]+[p.id for p in self.ca.get('/',{'sort':'interesting','page':2}).context['page']]
        self.assertEqual(len(set(allids)),26)
    def test_C18_C21_isolation_and_legacy_migration(self):
        self.put(self.ca,'interesting',4)
        migrate_importance_rows([{'paper_id':self.q.id,'user_id':self.b.id,'value':3}])
        self.assertEqual(Rating.objects.filter(paper=self.q,dimension='importance').get().value,3)
        self.assertFalse(Rating.objects.filter(paper=self.q,dimension='interesting').exists())
        migrate_importance_rows([{'paper_id':self.q.id,'user_id':self.b.id,'value':3}])
        with self.assertRaises(ValueError):migrate_importance_rows([{'paper_id':self.q.id,'user_id':self.b.id,'value':2}])
        self.assertEqual(Rating.objects.count(),2)
    def test_D02_D07_comments_authority_reply_and_idempotency(self):
        key=str(uuid.uuid4());r=self.post(self.ca,' <script>alert(1)</script> ',key=key);root=r.json()['id']
        self.assertEqual(r.status_code,201)
        self.assertEqual(self.post(self.ca,'<script>alert(1)</script>',key=key).json()['id'],root)
        self.assertEqual(self.post(self.ca,'different',key=key).status_code,409)
        reply=self.post(self.cb,parent=root).json()['id']
        self.assertEqual(self.post(self.cb,parent=reply).status_code,404)
        self.assertEqual(self.post(self.cb,parent=root,paper=self.q.id).status_code,404)
        path=self.base+f'comments/{root}/'
        self.assertEqual(self.cb.patch(path,data='{"body":"steal"}',content_type='application/json').status_code,403)
        self.assertEqual(self.ca.patch(path,data='{"body":"edited","version":1}',content_type='application/json').status_code,200)
        self.ca.delete(path,data='{"version":2}',content_type='application/json')
        result=self.cb.get(self.base+'comments/').json()
        self.assertEqual(result['count'],1);self.assertIsNone(result['comments'][0]['body']);self.assertEqual(len(result['comments']),2)
        for b in [' ','x'*5001,None,5]:self.assertEqual(self.post(self.ca,b).status_code,400)
    def test_D05_admin_hide_not_rewrite(self):
        root=self.post(self.ca,'secret hidden body').json()['id'];self.post(self.cb,parent=root)
        c=Client();c.force_login(self.admin)
        self.assertEqual(c.patch(self.base+f'comments/{root}/',data='{"body":"replacement"}',content_type='application/json').status_code,403)
        c.post(self.base+f'comments/{root}/hide/',data='{"hidden":true,"version":1}',content_type='application/json')
        response=self.cb.get(self.base+'comments/')
        self.assertNotContains(response,'secret hidden body');self.assertEqual(response.json()['count'],1)
    def test_D08_D09_hidden_paper_and_inactive(self):
        self.put(self.ca,'importance',3);self.post(self.ca)
        self.p.visible=False;self.p.save()
        for path in [f'/papers/{self.p.id}/',f'/papers/{self.p.id}/files/original.pdf',self.base+'ratings/',self.base+'comments/']:
            self.assertEqual(self.cb.get(path).status_code,404)
        self.assertEqual(self.put(self.cb,'interesting',4).status_code,404)
        self.assertEqual(self.post(self.cb).status_code,404)
        self.p.visible=True;self.p.save();self.a.is_active=False;self.a.save()
        self.assertEqual(self.put(self.ca,'importance',4).status_code,401)
        self.assertEqual(self.cb.get(self.base+'ratings/').json()['importance']['count'],1)
    def test_A06_host_boundary(self):self.assertEqual(self.ca.get('/',HTTP_HOST='evil.invalid').status_code,400)

class FormatTests(SimpleTestCase):
    def test_B03_no_optional_files(self):
        a=load_article(MINI.encode());self.assertEqual(a['validation']['counts']['images'],0)
    def test_B05_B06_B07_B08_B11_rejections(self):
        cases=[(MINI,'x.pdf','FMT_FILE'),('<main>Hello</main>','x.html','FMT_PROFILE'),
          (MINI.replace('完整中文段落。',''),'x.html','FMT_PAIR'),(MINI.replace('id="p1"','id="h1"'),'x.html','FMT_ID'),
          (MINI.replace('完整中文段落。','【待替换】'),'x.html','FMT_TEMPLATE')]
        for text,name,code in cases:
            with self.assertRaisesRegex(FormatError,code):load_article(text.encode(),name)
        for suffix in ['zip','md','docx','pdf']:
            with self.assertRaisesRegex(FormatError,'FMT_FILE'):load_article(MINI.encode(),'x.'+suffix)
        with self.assertRaisesRegex(FormatError,'FMT_MAP'):load_article(MINI.encode(),mapping=b'[{"id":"missing","kind":"paragraph"}]')
        for mapping in [b'[]',b'["bad"]',b'[1]',b'{"paragraphs":[]}',b'null',b'[{"id":"p1","kind":"paragraph"}]']:
            with self.assertRaisesRegex(FormatError,'FMT_MAP'):load_article(MINI.encode(),mapping=mapping)
    def test_B09_bad_images_and_oversized_pixels(self):
        for source in ['https://invalid/image.png','file:///C:/private.png','blob:abc','data:image/png;base64,YWJj']:
            text=MINI.replace('</main>',f'<img src="{source}"></main>')
            with self.assertRaisesRegex(FormatError,'FMT_RESOURCE'):load_article(text.encode())
        img=Image.new('1',(7000,6000));b=io.BytesIO();img.save(b,format='PNG')
        text=MINI.replace('</main>','<img src="data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()+'"></main>')
        with self.assertRaisesRegex(FormatError,'FMT_LIMIT'):load_article(text.encode())
    def test_B10_B13_math_complexity_limit(self):
        for text in [MINI.replace('</main>','<div class="equation" id="eq-1"></div></main>'),MINI.replace('Complete English paragraph.',r'\(x=1\)')]:
            with self.assertRaisesRegex(FormatError,'FMT_MATH'):load_article(text.encode())
        with self.assertRaisesRegex(FormatError,'FMT_LIMIT'):load_article((MINI+'<div>'*102).encode())
        with self.assertRaisesRegex(FormatError,'FMT_LIMIT'):load_article(b'x'*(50*1024**2+1))
        guard=ComplexityGuard()
        with self.assertRaisesRegex(FormatError,'FMT_LIMIT'):guard.feed('<br>'*180001)
    def test_B14_B15_script_events_encoded_urls_and_namespaces(self):
        payload='<script>fetch("https://invalid/")</script><a href="java&#x73;cript:alert(1)" onclick="alert(1)">link</a><iframe src="https://invalid/"></iframe>'
        a=load_article(MINI.replace('</main>',payload+'</main>').encode())
        self.assertNotIn('script',a['body']);self.assertNotIn('onclick',a['body']);self.assertNotIn('iframe',a['body'])
        for payload in ['<svg onload="alert(1)"></svg>','<math><annotation-xml encoding="text/html"><img src=x onerror=alert(1)></annotation-xml></math>','<custom-science>content</custom-science>']:
            with self.assertRaises(FormatError):load_article(MINI.replace('</main>',payload+'</main>').encode())
    def test_B01_B02_B04_B15_reference_fidelity(self):
        audit=json.loads((settings.ROOT/'reference_audit.json').read_text(encoding='utf-8'))
        results=[]
        for r in audit['papers']:
            p=settings.ROOT/r['html'];a=load_article(p.read_bytes(),p.name,(p.parent/'paragraph_map.json').read_bytes(),(settings.ROOT/r['original_pdf']).read_bytes())
            self.assertEqual(a['validation']['fidelity_before'],a['validation']['fidelity_after'])
            self.assertEqual(a['validation']['counts']['mathml'],r['counts']['mathml_nodes'])
            self.assertEqual(len(a['nav']['tables']),len(r['table_caption_ids']))
            for nav in a['nav'].values():self.assertTrue(all(f'id="{n["id"]}"' in a['body'] for n in nav))
            self.assertEqual(a['validation']['counts']['references'],r['counts']['references'])
            results.append({'paper':r['paper_key'],**a['validation']})
        out=settings.ROOT/'evidence';out.mkdir(exist_ok=True)
        (out/'content-fidelity.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

class UploadTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.override=override_settings(DATA_DIR=Path(self.temp.name));self.override.enable();self.addCleanup(self.override.disable)
        self.user=User.objects.create_user('uploader');self.other=User.objects.create_user('other')
        self.client.force_login(self.user);self.category=Category.objects.create(name='仿真')
    def upload(self,text=MINI):return self.client.post('/upload/',{'html':SimpleUploadedFile('paper.html',text.encode(),'text/html'),'categories':[self.category.id]})
    def test_upload_preview_publish_duplicate_and_download_auth(self):
        r=self.upload();self.assertEqual(r.status_code,302);url=r['Location']
        self.assertEqual(self.client.get(url).status_code,200);self.assertEqual(Paper.objects.count(),0)
        other=Client();other.force_login(self.other);self.assertEqual(other.get(url).status_code,404)
        self.assertEqual(self.client.post(url,{}).status_code,200)
        self.assertEqual(self.client.post(url,{'confirm':'yes'}).status_code,302)
        p=Paper.objects.get();self.assertEqual(self.client.get(f'/papers/{p.id}/').status_code,200)
        self.assertEqual(self.client.get(f'/papers/{p.id}/files/original.html').status_code,404)
        p.trusted_original=True;p.visible=False;p.save()
        self.assertContains(self.upload(),'FMT_DUPLICATE')
        p.visible=True;p.save()
        r=self.client.get(f'/papers/{p.id}/files/original.html');self.assertEqual(r.status_code,200)
        self.assertIn('attachment',r['Content-Disposition']);self.assertIn('sandbox',r['Content-Security-Policy']);r.close()
        self.assertEqual(Client().get(f'/papers/{p.id}/files/original.html').status_code,302)
    def test_B16_publication_disk_and_database_failure(self):
        a=load_article(MINI.encode());folder=Path(self.temp.name)/'staging'/'fail'
        write_bundle(folder,a,MINI.encode())
        with patch('pathlib.Path.rename',side_effect=OSError('disk')):
            with self.assertRaises(OSError):publish(folder,a,{'title_en':'EN','title_zh':'中文'},[self.category],self.user)
        self.assertFalse(Paper.objects.exists())
        with patch.object(Paper,'save',side_effect=IntegrityError('db')):
            with self.assertRaises(IntegrityError):publish(folder,a,{'title_en':'EN','title_zh':'中文'},[self.category],self.user)
        self.assertFalse(Paper.objects.exists());self.assertEqual(list((Path(self.temp.name)/'papers').iterdir()),[])
    def test_real_references_multipart_preview_publish_and_stage_images(self):
        audit=json.loads((settings.ROOT/'reference_audit.json').read_text(encoding='utf-8'))
        for ref in audit['papers']:
            path=settings.ROOT/ref['html']
            response=self.client.post('/upload/',{
                'html':SimpleUploadedFile(path.name,path.read_bytes(),'text/html'),
                'pdf':SimpleUploadedFile('original.pdf',(settings.ROOT/ref['original_pdf']).read_bytes(),'application/pdf'),
                'mapping':SimpleUploadedFile('paragraph_map.json',(path.parent/'paragraph_map.json').read_bytes(),'application/json'),
                'categories':[self.category.id]})
            self.assertEqual(response.status_code,302)
            preview=self.client.get(response['Location']);self.assertContains(preview,'格式检查通过')
            self.assertEqual(preview.content.count(b'<math '),ref['counts']['mathml_nodes'])
            img=self.client.get(response['Location']+'files/image-0.png');self.assertEqual(img.status_code,200);img.close()
            self.assertEqual(self.client.post(response['Location'],{'confirm':'yes'}).status_code,302)
        self.assertEqual(Paper.objects.count(),2)
    def test_stream_limit_does_not_trust_declared_length(self):
        from .upload_limits import LimitedUploadHandler
        from django.core.files.uploadhandler import StopUpload
        from django.test import RequestFactory
        request=RequestFactory().post('/upload/')
        handler=LimitedUploadHandler(request);handler.new_file('html','a.html','text/html',1)
        handler.size=50*1024**2
        with self.assertRaises(StopUpload):handler.receive_data_chunk(b'x',0)
        self.assertTrue(request.upload_limit_error)
