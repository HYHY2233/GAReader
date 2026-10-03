"""Installation defaults, distinct from administrators' existing vocabulary decisions."""
DEFAULT_TAG_NAMES = ('绿氨', '成本模型', '敏感性分析', '动态仿真', '稳态仿真', 'NMPC',
                     '容量优化', '代理模型', '参数辨识', 'IDAES', 'Pyomo', 'Aspen', 'Python')


def initialize_vocabulary(*, new_install):
    from .models import Tag
    if not new_install:
        return []  # Repeated setup must not reactivate manually disabled vocabulary.
    enabled = []
    for order, name in enumerate(DEFAULT_TAG_NAMES):
        tag, _ = Tag.objects.get_or_create(normalized_name=name.casefold(),
                                           defaults={'name': name, 'sort_order': order})
        tag.active = True
        tag.save(update_fields=['active'])
        enabled.append(tag.name)
    return enabled
