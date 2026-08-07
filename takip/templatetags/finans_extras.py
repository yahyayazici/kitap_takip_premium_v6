from django import template

register = template.Library()


@register.filter
def para(deger):
    if deger is None:
        return "0 ₺"
    try:
        return f"{float(deger):,.0f} ₺".replace(",", ".")
    except (TypeError, ValueError):
        return str(deger)
