import json
import uuid

from django.contrib.auth.decorators import login_required
from django.db import transaction, DatabaseError
from django.db.models import Q
from django.http import FileResponse, JsonResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_http_methods

from .anchors import AnchorError, project, validate_source
from .article import digest
from .models import AnnotationAnchor, Comment, PaperRevision
from .revisions import file_hash, manifest_for, pdf_for, read_json, revision_dir
from .views import api, comment_json, serve_file, visible_paper


def get_revision(request, paper, revision_id=None):
    value=revision_id or request.GET.get('revision') or paper.current_revision_id
    if not value: raise Http404('尚未完成内容快照升级。')
    try: key=uuid.UUID(str(value))
    except ValueError: raise Http404()
    return get_object_or_404(PaperRevision,pk=key,paper=paper)


@login_required
@require_GET
def revision_reader(request,pk,revision_id=None):
    paper=visible_paper(request,pk);revision=get_revision(request,paper,revision_id)
    folder=revision_dir(revision);manifest=manifest_for(revision)
    if manifest.get('reader_sha256') and file_hash(folder/'reader.html')!=manifest['reader_sha256']:
        raise ValueError('阅读快照校验失败。')
    body=(folder/'reader.html').read_text(encoding='utf-8')
    for image in folder.glob('image-*'):
        body=body.replace('@@IMAGE:'+image.stem.split('-')[1]+'@@',reverse('revision-file',args=[pk,revision.id,image.name]))
    return render(request,'library/reader.html',{'paper':paper,'revision':revision,'body':body,'manifest':manifest,
        'old_revision':revision.id!=paper.current_revision_id,'revision_has_map':(folder/'paragraph_map.json').is_file(),
        'nav':read_json(folder/'nav.json')})


@login_required
@require_GET
def revision_file(request,pk,revision_id,name):
    paper=visible_paper(request,pk);revision=get_revision(request,paper,revision_id)
    manifest=manifest_for(revision);expected=manifest.get('assets',{}).get(name)
    if expected and file_hash(revision_dir(revision)/name)!=expected:
        raise Http404('内容快照附件校验失败。')
    return serve_file(revision_dir(revision),name,paper.trusted_original or request.user.is_staff)


@api
@require_GET
def pdf_document(request,pk,revision_id):
    paper=visible_paper(request,pk);revision=get_revision(request,paper,revision_id)
    if not revision.pdf_sha256: raise Http404()
    pdf_for(revision)  # A replacement file must never silently inherit old geometry.
    response=FileResponse((revision_dir(revision)/'original.pdf').open('rb'),content_type='application/pdf')
    response['Content-Disposition']='inline; filename="original.pdf"'
    response['ETag']='"'+revision.pdf_sha256+'"'
    return response


@api
@require_GET
def representation(request,pk):
    paper=visible_paper(request,pk);revision=get_revision(request,paper)
    return JsonResponse(manifest_for(revision))


@api
@require_GET
def pdf_page_text(request,pk,revision_id,page_index):
    paper=visible_paper(request,pk);revision=get_revision(request,paper,revision_id)
    pdf=pdf_for(revision)
    if not 0<=page_index<len(pdf['pages']): raise Http404()
    page=pdf['pages'][page_index]
    return JsonResponse({k:page[k] for k in ['page_index','page_label','text','text_hash','view_box','rotation']})


@api
@require_http_methods(['GET','POST'])
def annotations(request,pk):
    paper=visible_paper(request,pk)
    if request.method=='POST':
        if len(request.body)>180000: return JsonResponse({'error':'批注定位数据过大。'},status=400)
        try:
            data=json.loads(request.body)
            if not isinstance(data,dict) or set(data)!={'body','source','request_key'}: raise AnchorError('批注字段不完整。')
            if not isinstance(data['source'],dict): raise AnchorError('原始锚点格式无效。')
            body=data['body']
            if not isinstance(body,str) or not 1<=len(body.strip())<=5000: raise AnchorError('批注正文须为 1—5000 字。')
            revision=get_revision(request,paper,data['source'].get('revision_id'))
            source=validate_source(data['source'],revision,manifest_for(revision),pdf_for(revision))
            body=body.strip();key=uuid.UUID(data['request_key'])
            rhash=digest(json.dumps([str(paper.id),body,source],ensure_ascii=False,sort_keys=True).encode())
            with transaction.atomic():
                old=Comment.objects.filter(user=request.user,request_key=key).first()
                if old:
                    if old.request_hash!=rhash:
                        return JsonResponse({'error':'同一操作标识对应不同内容。'},status=409)
                    return JsonResponse({'id':old.id,'version':old.version},status=200)
                comment=Comment.objects.create(paper=paper,user=request.user,body=body,request_key=key,request_hash=rhash)
                AnnotationAnchor.objects.create(comment=comment,revision=revision,source=source)
            return JsonResponse({'id':comment.id,'version':comment.version},status=201)
        except AnchorError as exc:
            return JsonResponse({'error':str(exc)},status=400)
        except RecursionError:
            return JsonResponse({'error':'定位数据层级过深。'},status=400)
        except DatabaseError:
            return JsonResponse({'error':'数据库暂时无法保存；草稿仍保留，请稍后重试。'},status=503)
    revision=get_revision(request,paper);view=request.GET.get('view','both')
    if view not in {'both','zh','en','pdf'}: raise ValueError()
    cursor=timezone.now()
    all_anchors=AnnotationAnchor.objects.filter(comment__paper=paper).select_related('revision','comment','comment__user')
    count=all_anchors.count();anchors=all_anchors
    since=request.GET.get('since')
    if since:
        timestamp=parse_datetime(since)
        if not timestamp or timezone.is_naive(timestamp): raise ValueError()
        anchors=anchors.filter(Q(comment__updated_at__gte=timestamp)|Q(comment__replies__updated_at__gte=timestamp)).distinct()
    current_manifest=manifest_for(revision);pdf=pdf_for(revision)
    cache={revision.id:current_manifest};threads=[]
    root_ids=list(anchors.values_list('comment_id',flat=True))
    replies={}
    for reply in Comment.objects.filter(parent_id__in=root_ids).select_related('user').order_by('created_at','id'):
        replies.setdefault(reply.parent_id,[]).append(comment_json(reply,request.user))
    for anchor in anchors.order_by('comment__created_at','comment_id'):
        root=anchor.comment
        item=comment_json(root,request.user)
        item['replies']=replies.get(root.id,[])
        item['source_url']=reverse('revision-reader',args=[pk,anchor.revision_id])+'?view='+anchor.source['created_view']+'&thread='+str(root.id)
        if root.hidden:
            item['source']=None;item['projections']=[]
        else:
            old=cache.get(anchor.revision_id)
            if old is None:
                old=cache[anchor.revision_id]=manifest_for(anchor.revision)
            item['source']=anchor.source
            item['projections']=project(anchor.source,old,current_manifest,pdf,view)
        threads.append(item)
    return JsonResponse({'threads':threads,'count':count,'cursor':cursor.isoformat(),'revision_id':str(revision.id),'view':view})
