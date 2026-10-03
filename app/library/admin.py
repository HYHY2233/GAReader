from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin
from django import forms
from django.db.models import F
from django.utils import timezone
from urllib.parse import urlsplit
from .models import Paper, Category, Comment

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
    list_display=('name',)
    def has_delete_permission(self,request,obj=None): return False

class PaperMetadataForm(forms.ModelForm):
    class Meta:
        model=Paper
        fields=('title_en','title_zh','categories','authors','year','note','source_url','visible')
    def clean_source_url(self):
        url=self.cleaned_data['source_url']
        if url and urlsplit(url).scheme not in {'http','https'}:raise forms.ValidationError('仅支持 http / https 来源链接。')
        return url

@admin.register(Paper)
class PaperAdmin(admin.ModelAdmin):
    form=PaperMetadataForm
    list_display=('title_zh','visible','created_at')
    fields=('title_en','title_zh','categories','authors','year','note','source_url','visible','profile','raw_hash','content_hash')
    readonly_fields=('profile','raw_hash','content_hash')
    filter_horizontal=('categories',)
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
