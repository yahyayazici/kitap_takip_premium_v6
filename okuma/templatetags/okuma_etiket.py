from django import template

register = template.Library()


@register.filter
def get_item(sozluk, anahtar):
    return sozluk.get(anahtar, 0) if sozluk else 0
