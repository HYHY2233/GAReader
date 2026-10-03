from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from urllib.parse import urlsplit
from .models import Category, Tag


class LoginForm(AuthenticationForm):
    error_messages = {'invalid_login': '登录名或密码不正确。', 'inactive': '此账户已停用。'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = '登录名'
        self.fields['username'].widget.attrs['autocomplete'] = 'username'


class RegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = '登录名'
        self.fields['username'].help_text = '可用中文、字母、数字及 @ . + - _。'
        self.fields['username'].widget.attrs['autocomplete'] = 'username'
        self.fields['first_name'].label = '昵称（选填）'
        self.fields['first_name'].widget.attrs['autocomplete'] = 'nickname'
        self.fields['password1'].label = '密码'
        self.fields['password1'].help_text = '至少 10 位，请避免纯数字或常见密码。'
        self.fields['password2'].label = '确认密码'
        self.fields['password2'].help_text = ''

    def clean_username(self):
        username = super().clean_username()
        if username and username.casefold().startswith('guest_'):
            raise forms.ValidationError('此登录名前缀已保留，请换一个登录名。')
        return username


class MetadataForm(forms.Form):
    categories = forms.ModelMultipleChoiceField(label='分类（至少一项）', queryset=Category.objects.all(), widget=forms.CheckboxSelectMultiple)
    tags = forms.ModelMultipleChoiceField(label='标签（1—5 项）', queryset=Tag.objects.filter(active=True),
        widget=forms.SelectMultiple(attrs={'size': 6, 'data-tag-select': ''}),
        error_messages={'required': '请至少选择1个标签。', 'invalid_choice': '标签不存在或已停用，请重新选择。'})
    title_en = forms.CharField(label='英文题名（留空则提取）',max_length=1000,required=False)
    title_zh = forms.CharField(label='中文题名（留空则提取）',max_length=1000,required=False)
    note = forms.CharField(label='一句分享说明',max_length=500,required=False)
    authors = forms.CharField(label='作者',max_length=1000,required=False)
    year = forms.IntegerField(label='年份',min_value=1500,max_value=2200,required=False)
    source_url = forms.URLField(label='来源链接',required=False,max_length=2000)
    def clean_tags(self):
        values = self.cleaned_data['tags']
        if values.count() > 5: raise forms.ValidationError('最多选择5个标签。')
        return values
    def clean_source_url(self):
        value=self.cleaned_data['source_url']
        if value and urlsplit(value).scheme not in {'http','https'}:raise forms.ValidationError('来源链接仅支持 http 或 https。')
        return value

class PaperMetadataEditForm(MetadataForm):
    remove_inactive_tags = forms.ModelMultipleChoiceField(label='勾选要移除的历史停用标签',
        queryset=Tag.objects.none(), required=False, widget=forms.CheckboxSelectMultiple)

    def __init__(self, *args, paper, **kwargs):
        super().__init__(*args, **kwargs)
        self.inactive_tags = paper.tags.filter(active=False)
        self.fields['remove_inactive_tags'].queryset = self.inactive_tags
        # Existing inactive associations may be retained when only the title or note changes.
        self.fields['tags'].required = not self.inactive_tags.exists()

    def clean(self):
        values = super().clean()
        removed = values.get('remove_inactive_tags', Tag.objects.none())
        retained = list(self.inactive_tags.exclude(pk__in=removed))
        values['retained_inactive_tags'] = retained
        if 'tags' not in self.errors:
            count = len(values.get('tags', [])) + len(retained)
            if not count: self.add_error('tags', '请至少选择1个标签，或保留已有的历史标签。')
            if count > 5: self.add_error('tags', '新增与保留的历史标签合计最多5个，请明确选择要移除的旧标签。')
        return values


class UploadForm(MetadataForm):
    html = forms.FileField(label='标准双语 HTML', widget=forms.FileInput(attrs={'accept':'.html'}))
    pdf = forms.FileField(label='原文 PDF（可选）',required=False,widget=forms.FileInput(attrs={'accept':'.pdf'}))
    mapping = forms.FileField(label='段落映射 JSON（可选）',required=False,widget=forms.FileInput(attrs={'accept':'.json'}))
