from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from urllib.parse import urlsplit
from .models import Category


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


class UploadForm(forms.Form):
    html = forms.FileField(label='标准双语 HTML', widget=forms.FileInput(attrs={'accept':'.html'}))
    categories = forms.ModelMultipleChoiceField(label='分类（至少一项）', queryset=Category.objects.all(), widget=forms.CheckboxSelectMultiple)
    title_en = forms.CharField(label='英文题名（留空则提取）',max_length=1000,required=False)
    title_zh = forms.CharField(label='中文题名（留空则提取）',max_length=1000,required=False)
    note = forms.CharField(label='一句分享说明',max_length=500,required=False)
    authors = forms.CharField(label='作者',max_length=1000,required=False)
    year = forms.IntegerField(label='年份',min_value=1500,max_value=2200,required=False)
    source_url = forms.URLField(label='来源链接',required=False,max_length=2000)
    pdf = forms.FileField(label='原文 PDF（可选）',required=False,widget=forms.FileInput(attrs={'accept':'.pdf'}))
    mapping = forms.FileField(label='段落映射 JSON（可选）',required=False,widget=forms.FileInput(attrs={'accept':'.json'}))
    def clean_source_url(self):
        value=self.cleaned_data['source_url']
        if value and urlsplit(value).scheme not in {'http','https'}:raise forms.ValidationError('来源链接仅支持 http 或 https。')
        return value
