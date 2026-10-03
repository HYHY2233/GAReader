"""v3 controlled metadata, home indexing and preservation regression tests."""
import json
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from .models import Tag, Category, Paper, Comment, Rating, AnnotationAnchor
from .forms import MetadataForm
from .tests import UploadTests, make_paper

class TagWorkflowTests(TestCase):
    setUp=UploadTests.setUp
    upload=UploadTests.upload
    def test_normalized_unique_display(self):
        tag=Tag.objects.create(name='  ＰｙＴｈｏｎ　  模型  ')
        self.assertEqual(tag.name,'PyThon 模型');self.assertEqual(tag.normalized_name,'python 模型')
        duplicate=Tag(name='python   模型')
        with self.assertRaises(ValidationError):duplicate.full_clean()
        with self.assertRaises(IntegrityError),transaction.atomic():duplicate.save()
    def test_active_one_to_five_distinct_unknown_and_category(self):
        tags=[Tag.objects.create(name='标签'+str(n)) for n in range(6)]
        good={'categories':[self.category.pk],'tags':[tags[0].pk,tags[0].pk]}
        form=MetadataForm(good);self.assertTrue(form.is_valid(),form.errors);self.assertEqual(form.cleaned_data['tags'].count(),1)
        for ids in [[],[999999],[t.pk for t in tags]]:
            form=MetadataForm({**good,'tags':ids});self.assertFalse(form.is_valid());self.assertIn('tags',form.errors)
        tags[0].active=False;tags[0].save()
        self.assertFalse(MetadataForm(good).is_valid())
        self.assertFalse(MetadataForm({'tags':[tags[1].pk]}).is_valid())
    def test_direct_upload_missing_tags_and_preview_revalidation_metadata(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .tests import MINI
        response=self.client.post('/upload/',{'categories':[self.category.pk],'html':SimpleUploadedFile('paper.html',MINI.encode())})
        self.assertContains(response,'请至少选择1个标签');self.assertEqual(Paper.objects.count(),0)
        staged=self.upload()['Location'];self.tag.active=False;self.tag.save()
        self.assertContains(self.client.post(staged,{'confirm':'yes'}),'分类或标签无效');self.assertEqual(Paper.objects.count(),0)
        replacement=Tag.objects.create(name='新标签')
        saved=self.client.post(staged+'metadata/',{'categories':[self.category.pk],'tags':[replacement.pk], 'title_zh':'新题名'})
        self.assertEqual(saved.status_code,302)
        self.assertContains(self.client.get(staged),'新标签');self.assertContains(self.client.get(staged),'新题名')
        self.assertEqual(self.client.post(staged,{'confirm':'yes'}).status_code,302)
        paper=Paper.objects.get();self.assertEqual(list(paper.tags.all()),[replacement]);self.assertFalse(paper.has_pdf)
        self.assertContains(self.client.get(f'/papers/{paper.pk}/'),'未提供原版 PDF')
    def test_metadata_does_not_revise_or_bump_created_at_and_owner_permission(self):
        staged=self.upload()['Location'];self.client.post(staged,{'confirm':'yes'})
        paper=Paper.objects.get();before=(paper.created_at,paper.raw_hash,paper.content_hash,paper.current_revision_id,paper.revisions.count())
        tag=Tag.objects.create(name='第二个标签');category=Category.objects.create(name='另一个大类')
        response=self.client.post(f'/papers/{paper.pk}/metadata/',{'tags':[tag.pk],'categories':[category.pk],'title_zh':'更新中文题名'})
        self.assertEqual(response.status_code,302);paper.refresh_from_db()
        self.assertEqual(before,(paper.created_at,paper.raw_hash,paper.content_hash,paper.current_revision_id,paper.revisions.count()))
        self.client.force_login(self.other);self.assertEqual(self.client.get(f'/papers/{paper.pk}/metadata/').status_code,404)
    def test_expanded_home_empty_sections_flat_filters_and_independent_scores(self):
        p=make_paper();q=make_paper('另一篇');empty=Category.objects.create(name='空类',sort_order=-1)
        p.categories.add(self.category);q.categories.add(self.category);p.tags.add(self.tag)
        t=Tag.objects.create(name='另标签');p.tags.add(t)
        Rating.objects.create(paper=p,user=self.user,dimension='interesting',value=5)
        Rating.objects.create(paper=p,user=self.other,dimension='interesting',value=3)
        response=self.client.get('/');self.assertEqual(response.context['total'],2)
        self.assertIsNone(response.context['page']);self.assertEqual(response.context['sections'][0]['category'],empty)
        self.assertContains(response,'暂无论文');self.assertNotContains(response,'role="tab"')
        for params in [{'tag':self.tag.pk},{'category':self.category.pk,'q':p.title_zh,'sort':'interesting'}]:
            page=self.client.get('/',params).context['page'];self.assertEqual(len(page),1)
            self.assertEqual((page[0].interesting_avg,page[0].interesting_count),(4,2))
    def test_admin_merge_preserves_records_and_deactivation(self):
        from .admin import TagAdmin
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from unittest.mock import patch
        p=make_paper();other=Tag.objects.create(name='待合并');p.tags.add(other,self.tag)
        request=RequestFactory().post('/',{'confirm_merge':'1','target':str(self.tag.pk)})
        modeladmin=TagAdmin(Tag,AdminSite())
        with patch.object(modeladmin,'message_user'):
            modeladmin.merge(request,Tag.objects.filter(pk__in=[other.pk,self.tag.pk]))
        self.assertEqual(list(p.tags.all()),[self.tag]);other.refresh_from_db();self.assertFalse(other.active)
