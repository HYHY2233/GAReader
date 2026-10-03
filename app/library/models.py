import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

class Category(models.Model):
    name = models.CharField('分类', max_length=60, unique=True)
    class Meta:
        verbose_name = '分类'
        verbose_name_plural = '分类'
        ordering = ['id']
    def __str__(self): return self.name

class Paper(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title_en = models.CharField('英文题名', max_length=1000)
    title_zh = models.CharField('中文题名', max_length=1000)
    authors = models.CharField('作者', max_length=1000, blank=True)
    year = models.PositiveSmallIntegerField('年份', null=True, blank=True)
    note = models.CharField('分享说明', max_length=500, blank=True)
    source_url = models.URLField('来源链接', max_length=2000, blank=True)
    categories = models.ManyToManyField(Category, verbose_name='分类')
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    visible = models.BooleanField('公开给成员', default=True)
    raw_hash = models.CharField(max_length=64, unique=True)
    content_hash = models.CharField(max_length=64)
    profile = models.CharField(max_length=40)
    has_pdf = models.BooleanField(default=False)
    has_map = models.BooleanField(default=False)
    trusted_original = models.BooleanField(default=False)
    validation = models.JSONField(default=dict)
    current_revision = models.ForeignKey('PaperRevision', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    class Meta:
        verbose_name = '论文'
        verbose_name_plural = '论文'
    def __str__(self): return self.title_zh

class Rating(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='ratings')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    dimension = models.CharField(max_length=12, choices=[('interesting', '有意思'), ('importance', '重要性')])
    value = models.IntegerField()
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['paper', 'user', 'dimension'], name='rating_one_per_dimension'),
                       models.CheckConstraint(condition=Q(dimension__in=['interesting', 'importance']), name='rating_valid_dimension'),
                       models.CheckConstraint(condition=Q(value__in=[1,2,3,4,5]), name='rating_valid_value')]

class Comment(models.Model):
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='replies')
    body = models.TextField('评论')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    edited = models.BooleanField(default=False)
    deleted = models.BooleanField(default=False)
    hidden = models.BooleanField('已隐藏', default=False)
    request_key = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'request_key'], name='comment_idempotency_key')]
        verbose_name = '评论'
        verbose_name_plural = '评论'


class PaperRevision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='revisions')
    identity = models.CharField(max_length=64)
    content_hash = models.CharField(max_length=64)
    pdf_sha256 = models.CharField(max_length=64, blank=True)
    manifest_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    title_en = models.CharField(max_length=1000)
    title_zh = models.CharField(max_length=1000)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['paper', 'identity'], name='paper_revision_identity')]
        ordering = ['created_at', 'id']


class AnnotationAnchor(models.Model):
    comment = models.OneToOneField(Comment, on_delete=models.CASCADE, primary_key=True, related_name='annotation')
    revision = models.ForeignKey(PaperRevision, on_delete=models.PROTECT, related_name='anchors')
    source = models.JSONField()
    schema_version = models.PositiveSmallIntegerField(default=1)
