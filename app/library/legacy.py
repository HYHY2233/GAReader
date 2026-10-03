"""Explicit, transactional adapter for a future reviewed single-score migration.
No legacy table is created. Existing rows are mapped only to importance.
"""
from django.db import transaction
from .models import Rating

def migrate_importance_rows(rows):
    with transaction.atomic():
        for row in rows:
            value=row['value']
            if type(value)!=int or value not in range(1,6):raise ValueError('旧评分不是 1—5 的整数。')
            existing,created=Rating.objects.get_or_create(user_id=row['user_id'],paper_id=row['paper_id'],dimension='importance',defaults={'value':value})
            if not created and existing.value!=value:raise ValueError('现有重要性评分冲突，迁移回滚。')
