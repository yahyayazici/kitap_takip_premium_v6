from django import template

register = template.Library()


@register.filter
def in_filter(value, selected) -> bool:
    """Seçili liste veya tekil değer içinde mi kontrol eder."""
    if selected is None:
        return False
    if isinstance(selected, (list, tuple, set)):
        return str(value) in {str(x) for x in selected} or value in selected
    return str(value) == str(selected)
