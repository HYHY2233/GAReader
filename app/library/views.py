import functools
import difflib
import json
import re
import shutil
import time
import uuid
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError, DatabaseError
from django.db.models import Avg, Count, OuterRef, Subquery, Q, F, FloatField, IntegerField
from django.db.models.functions import Coalesce
from django.http import JsonResponse, FileResponse, Http404, HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_GET
from django.utils import timezone

from .article import load_article, FormatError, digest
from .forms import UploadForm
from .models import Paper, Category, Rating, Comment
from .storage import paper_dir, write_bundle, publish, cleanup_staging, rendered_body

DIMENSIONS = {'interesting':'有意思', 'importance':'重要性'}

def visible_paper(request, pk):
    qs=Paper.objects.all() if request.user.is_staff else Paper.objects.filter(visible=True)
    return get_object_or_404(qs,pk=pk)

def aggregates(qs):
    for dim in DIMENSIONS:
        votes=Rating.objects.filter(paper_id=OuterRef('pk'),dimension=dim).values('paper_id')
        qs=qs.annotate(**{dim+'_avg':Subquery(votes.annotate(v=Avg('value')).values('v'),output_field=FloatField()),
                          dim+'_count':Coalesce(Subquery(votes.annotate(v=Count('id')).values('v'),output_field=IntegerField()),0)})
    comments=Comment.objects.filter(paper_id=OuterRef('pk'),hidden=False,deleted=False).values('paper_id').annotate(v=Count('id')).values('v')
    return qs.annotate(comment_count=Coalesce(Subquery(comments,output_field=IntegerField()),0))

@login_required
@require_GET
def home(request):
    papers=Paper.objects.filter(visible=True)
    query=request.GET.get('q','').strip()[:200]
    category=request.GET.get('category','')
    if query: papers=papers.filter(Q(title_en__icontains=query)|Q(title_zh__icontains=query)|Q(authors__icontains=query)|Q(note__icontains=query))
    if category.isdecimal(): papers=papers.filter(categories=category)
    papers=aggregates(papers.distinct()).prefetch_related('categories')
    sort=request.GET.get('sort','new')
    if sort in DIMENSIONS: papers=papers.order_by(F(sort+'_avg').desc(nulls_last=True),'-'+sort+'_count','-created_at','id')
    else: papers=papers.order_by('-created_at','id')
    page=Paginator(papers,20).get_page(request.GET.get('page'))
    return render(request,'library/home.html',{'page':page,'categories':Category.objects.all(),'query':query,
                  'category':category,'sort':sort,'filters':urlencode({'q':query,'category':category,'sort':sort})})

@login_required
@require_GET
def reader(request,pk):
    paper=visible_paper(request,pk); folder=paper_dir(paper)
    body=rendered_body(folder,lambda name:reverse('paper-file',args=[pk,name]))
    return render(request,'library/reader.html',{'paper':paper,'body':body,'nav':json.loads((folder/'nav.json').read_text(encoding='utf-8'))})

def stage_folder(request, token):
    folder=settings.DATA_DIR/'staging'/str(request.user.id)/str(token)
    if not folder.is_dir() or folder.stat().st_mtime < time.time()-86400: raise Http404('暂存已过期，请重新上传。')
    return folder

@login_required
@require_http_methods(['GET','POST'])
def upload(request):
    form=UploadForm(request.POST or None,request.FILES or None)
    error=''
    if request.method=='POST':
        if getattr(request,'upload_limit_error',False): error='FMT_LIMIT：文件超过允许大小。'
        elif form.is_valid():
            folder=None
            try:
                data=form.cleaned_data
                raw=data['html'].read(); pdf=data['pdf'].read() if data['pdf'] else None
                mapping=data['mapping'].read() if data['mapping'] else None
                if data['pdf'] and not data['pdf'].name.lower().endswith('.pdf'): raise FormatError('FMT_FILE','附加原文必须为 PDF。')
                if data['mapping'] and not data['mapping'].name.lower().endswith('.json'): raise FormatError('FMT_MAP','映射必须为 JSON。')
                article=load_article(raw,data['html'].name,mapping,pdf)
                if Paper.objects.filter(raw_hash=article['raw_hash']).exists(): raise FormatError('FMT_DUPLICATE','同一 HTML 已存在，含隐藏论文。')
                metadata={k:data[k] for k in ['title_en','title_zh','note','authors','year','source_url']}
                metadata['title_en']=metadata['title_en'] or article['title_en']
                metadata['title_zh']=metadata['title_zh'] or article['title_zh']
                metadata['source_url']=metadata['source_url'] or article['source_url']
                if not metadata['title_en'] or not metadata['title_zh']: raise FormatError('FMT_PAIR','未提取到双语题名，请在表单补全。')
                cleanup_staging(); token=uuid.uuid4()
                folder=settings.DATA_DIR/'staging'/str(request.user.id)/str(token)
                write_bundle(folder,article,raw,pdf,mapping)
                summary={k:v for k,v in article.items() if k not in {'body','images','nav'}}
                (folder/'staging.json').write_text(json.dumps({'article':summary,'metadata':metadata,'categories':[c.id for c in data['categories']]},ensure_ascii=False),encoding='utf-8')
                return redirect('preview',token=token)
            except (FormatError,OSError) as exc:
                if folder and folder.exists(): shutil.rmtree(folder)
                error=str(exc) if isinstance(exc,FormatError) else '暂存写入失败，未发布。请检查磁盘空间。'
    return render(request,'library/upload.html',{'form':form,'error':error})

@login_required
@require_http_methods(['GET','POST'])
def preview(request,token):
    folder=stage_folder(request,token)
    info=json.loads((folder/'staging.json').read_text(encoding='utf-8')); error=''
    if request.method=='POST':
        if request.POST.get('confirm')!='yes': error='请先确认检查过预览。'
        else:
            try:
                paper=publish(folder,info['article'],info['metadata'],info['categories'],request.user)
                return redirect('reader',pk=paper.id)
            except FormatError as exc: error=str(exc)
            except (OSError,DatabaseError):
                error='发布失败或同一文件已经发布；没有创建残缺论文。'
                if not folder.exists():return render(request,'library/upload.html',{'form':UploadForm(),'error':error+' 请重新选择文件。'},status=409)
    candidates=Paper.objects.all() if request.user.is_staff else Paper.objects.filter(visible=True)
    metadata=info['metadata']
    normalize=lambda value:re.sub(r'\W','',value.casefold())
    similarity=any((metadata['source_url'] and p.source_url==metadata['source_url']) or
        difflib.SequenceMatcher(None,normalize(p.title_en),normalize(metadata['title_en'])).ratio()>=0.9 or
        difflib.SequenceMatcher(None,normalize(p.title_zh),normalize(metadata['title_zh'])).ratio()>=0.9
        for p in candidates.only('title_en','title_zh','source_url'))
    return render(request,'library/preview.html',{'token':token,'info':info,'error':error,'similarity':similarity,
                  'body':rendered_body(folder,lambda name:reverse('stage-file',args=[token,name]))})

def serve_file(folder,name,original_allowed=False):
    if re.fullmatch(r'image-\d+\.(png|jpeg|webp)',name):
        path=folder/name
        if not path.is_file(): raise Http404()
        return FileResponse(path.open('rb'),content_type='image/'+path.suffix[1:])
    if name not in {'original.html','original.pdf','paragraph_map.json'} or (name=='original.html' and not original_allowed): raise Http404()
    path=folder/name
    if not path.is_file(): raise Http404()
    response=FileResponse(path.open('rb'),as_attachment=True,filename=name,content_type='application/octet-stream')
    response['Content-Security-Policy']="sandbox; default-src 'none'; base-uri 'none'"
    response['X-Content-Type-Options']='nosniff'
    return response

@login_required
@require_GET
def paper_file(request,pk,name):
    paper=visible_paper(request,pk)
    return serve_file(paper_dir(paper),name,paper.trusted_original or request.user.is_staff)

@login_required
@require_GET
def stage_file(request,token,name):
    if not re.fullmatch(r'image-\d+\.(png|jpeg|webp)',name): raise Http404()
    return serve_file(stage_folder(request,token),name)

def api(view):
    @functools.wraps(view)
    def wrapped(request,*args,**kwargs):
        if not request.user.is_authenticated or not request.user.is_active: return JsonResponse({'error':'请先进入论文库。'},status=401)
        try: return view(request,*args,**kwargs)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError): return JsonResponse({'error':'请求字段或格式不正确。'},status=400)
    return wrapped

def payload(request,allowed):
    if len(request.body)>24000: raise ValueError()
    data=json.loads(request.body or '{}')
    if not isinstance(data,dict) or set(data)-set(allowed): raise ValueError()
    return data

def rating_data(paper,user):
    result={}
    for dim in DIMENSIONS:
        rows=Rating.objects.filter(paper=paper,dimension=dim)
        summary=rows.aggregate(average=Avg('value'),count=Count('id'))
        summary['mine']=rows.filter(user=user).values_list('value',flat=True).first()
        result[dim]=summary
    return result

@api
@require_GET
def ratings(request,pk): return JsonResponse(rating_data(visible_paper(request,pk),request.user))

@api
@require_http_methods(['PUT','DELETE'])
def rating(request,pk,dimension):
    paper=visible_paper(request,pk)
    if dimension not in DIMENSIONS: return JsonResponse({'error':'评分维度无效。'},status=400)
    data=payload(request,['value'] if request.method=='PUT' else [])
    with transaction.atomic():
        if request.method=='PUT':
            value=data.get('value')
            if type(value)!=int or not 1<=value<=5: raise ValueError()
            Rating.objects.update_or_create(paper=paper,user=request.user,dimension=dimension,defaults={'value':value})
        else: Rating.objects.filter(paper=paper,user=request.user,dimension=dimension).delete()
    return JsonResponse(rating_data(paper,request.user))

def comment_json(c,user):
    unavailable=c.deleted or c.hidden
    return {'id':c.id,'parent':c.parent_id,'body':None if unavailable else c.body,
            'placeholder':('评论已删除' if c.deleted else '评论已隐藏') if unavailable else '',
            'author':c.user.first_name or c.user.username,'created_at':timezone.localtime(c.created_at).strftime('%Y-%m-%d %H:%M'),
            'edited':c.edited,'can_edit':not unavailable and c.user_id==user.id,
            'can_hide':user.is_staff and not c.deleted,'hidden':c.hidden}

@api
@require_http_methods(['GET','POST'])
def comments(request,pk):
    paper=visible_paper(request,pk)
    if request.method=='POST':
        data=payload(request,['body','parent','request_key'])
        body=data.get('body')
        if not isinstance(body,str) or not 1<=len(body.strip())<=5000: raise ValueError()
        body=body.strip(); key=uuid.UUID(data['request_key']); parent=data.get('parent')
        if parent is not None and type(parent)!=int: raise ValueError()
        rhash=digest(json.dumps([str(paper.id),parent,body],ensure_ascii=False).encode())
        with transaction.atomic():
            existing=Comment.objects.filter(user=request.user,request_key=key).first()
            if existing:
                if existing.request_hash!=rhash: return JsonResponse({'error':'同一操作标识对应不同内容，请新建操作。'},status=409)
                return JsonResponse(comment_json(existing,request.user))
            root=None
            if parent is not None:
                root=get_object_or_404(Comment,pk=parent,paper=paper,parent=None)
            c=Comment.objects.create(paper=paper,user=request.user,body=body,parent=root,request_key=key,request_hash=rhash)
        return JsonResponse(comment_json(c,request.user),status=201)
    rows=Comment.objects.filter(paper=paper).select_related('user').order_by('created_at','id')
    return JsonResponse({'comments':[comment_json(c,request.user) for c in rows],
                         'count':rows.filter(hidden=False,deleted=False).count()})

@api
@require_http_methods(['PATCH','DELETE'])
def comment_detail(request,pk,comment_id):
    paper=visible_paper(request,pk); c=get_object_or_404(Comment,pk=comment_id,paper=paper)
    if c.user_id!=request.user.id or c.hidden or c.deleted: return JsonResponse({'error':'只能改删自己可见的评论。'},status=403)
    data=payload(request,['body'] if request.method=='PATCH' else [])
    if request.method=='DELETE': c.deleted=True; c.body=''
    else:
        body=data.get('body')
        if not isinstance(body,str) or not 1<=len(body.strip())<=5000: raise ValueError()
        c.body=body.strip(); c.edited=True
    c.save(update_fields=['body','edited','deleted','updated_at'])
    return JsonResponse(comment_json(c,request.user))

@api
@require_http_methods(['POST'])
def comment_hide(request,pk,comment_id):
    paper=visible_paper(request,pk)
    if not request.user.is_staff: return JsonResponse({'error':'仅管理员可隐藏评论。'},status=403)
    data=payload(request,['hidden'])
    if type(data.get('hidden'))!=bool: raise ValueError()
    c=get_object_or_404(Comment,pk=comment_id,paper=paper); c.hidden=data['hidden']; c.save(update_fields=['hidden'])
    return JsonResponse(comment_json(c,request.user))

@require_GET
def health(request):
    return JsonResponse({'application':'paper-library-v3','instance':settings.CONFIG['instance_id']})
