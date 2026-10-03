"""One visibility rule for annotation lists, counters and source navigation."""
from django.db.models import Exists, OuterRef, Q
from .models import Comment


def visible_threads(queryset=None):
    roots = queryset if queryset is not None else Comment.objects.filter(annotation__isnull=False)
    replies = Comment.objects.filter(parent_id=OuterRef('pk'), hidden=False, deleted=False)
    return roots.annotate(has_visible_reply=Exists(replies)).filter(
        Q(hidden=False, deleted=False) | Q(has_visible_reply=True))
