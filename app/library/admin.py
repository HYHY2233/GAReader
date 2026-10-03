from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.db.models import F
from django.utils import timezone
from urllib.parse import urlsplit
from .models import Paper, Category, Tag, Comment
from django.db import transaction
from django.template.response import TemplateResponse

admin.site.site_header='论文库管理'
admin.site.site_title='论文库管理'
admin.site.index_title='账户、分类与论文'
admin.site.unregister(Group)
admin.site.unregister(User)

@admin.register(User)
class AccountAdmin(UserAdmin):
    list_display=('username','first_name','is_active','is_staff')
    fieldsets=((None,{'fields':('username','password','first_name')}),('权限',{'fields':('is_active','is_staff')}))
    add_fieldsets=((None,{'classes':('wide',),'fields':('username','first_name','password1','password2','is_staff')}),)
    filter_horizontal=()
    list_filter=('is_active','is_staff')
    def save_model(self,request,obj,form,change):
        obj.is_superuser=obj.is_staff
        super().save_model(request,obj,form,change)
    def has_delete_permission(self,request,obj=None): return False

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display=('name','sort_order')
    list_per_page=20
    def has_delete_permission(self,request,obj=None): return False

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display=('name','active','sort_order')
    # Edit metadata on the change form; keep action posts within the upload field limit.
    list_per_page=20
    search_fields=('name','normalized_name')
    list_filter=('active',)
    actions=('enable','disable','merge')
    @admin.action(description='启用所选标签（管理员已核对）')
    def enable(self,request,queryset): queryset.update(active=True)
    @admin.action(description='停用所选标签（保留论文关联）')
    def disable(self,request,queryset): queryset.update(active=False)
    @admin.action(description='合并所选标签到其中一项')
    def merge(self,request,queryset):
        choices=list(queryset)
        if len(choices)>20:
            self.message_user(request,'每次最多合并20个标签，请缩小选择范围。',level='error');return
        if len(choices)<2:
            self.message_user(request,'至少选择两个标签。',level='error');return
        target=request.POST.get('target')
        if request.POST.get('confirm_merge') and target and any(str(t.pk)==target and t.active for t in choices):
            ids=[t.pk for t in choices if str(t.pk)!=target]
            with transaction.atomic():
                through=Paper.tags.through
                papers=through.objects.filter(tag_id__in=ids).values_list('paper_id',flat=True).distinct()
                through.objects.bulk_create([through(paper_id=p,tag_id=int(target)) for p in papers],ignore_conflicts=True)
                through.objects.filter(tag_id__in=ids).delete()
                Tag.objects.filter(pk__in=ids).update(active=False)
            self.message_user(request,'标签已合并，原词条已停用；论文内容和批注未改变。');return
        return TemplateResponse(request,'admin/tag_merge.html',{**self.admin_site.each_context(request),
            'title':'合并标签','choices':choices,'opts':self.model._meta,'action_checkbox_name':admin.helpers.ACTION_CHECKBOX_NAME})
    def has_delete_permission(self,request,obj=None): return False

class PaperMetadataForm(forms.ModelForm):
    class Meta:
        model=Paper
        fields=('title_en','title_zh','categories','tags','authors','year','note','source_url','visible')
    def clean_tags(self):
        tags=self.cleaned_data['tags']
        if tags.count()>5: raise forms.ValidationError('最多选择5个标签。')
        original=set(self.instance.tags.values_list('pk',flat=True)) if self.instance.pk else set()
        if tags.filter(active=False).exclude(pk__in=original).exists(): raise forms.ValidationError('不能新增停用标签。')
        return tags
    def clean_source_url(self):
        url=self.cleaned_data['source_url']
        if url and urlsplit(url).scheme not in {'http','https'}:raise forms.ValidationError('仅支持 http / https 来源链接。')
        return url

@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    form=PaperMetadataForm
    list_display=('title_zh','visible','created_at')
    fields=('title_en','title_zh','categories','tags','authors','year','note','source_url','visible','profile','raw_hash','content_hash')
    readonly_fields=('profile','raw_hash','content_hash')
    filter_horizontal=('categories','tags')
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display=('id','paper','user','created_at','hidden','deleted')
    readonly_fields=('paper','user','parent','body','created_at','edited','deleted')
    fields=readonly_fields+('hidden',)
    def save_model(self,request,obj,form,change):
        # Moderation changes only visibility, never an author's concurrent body edit.
        Comment.objects.filter(pk=obj.pk).update(hidden=obj.hidden,version=F('version')+1,updated_at=timezone.now())
        obj.refresh_from_db()
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False
