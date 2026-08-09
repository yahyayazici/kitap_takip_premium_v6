from django import template

register = template.Library()


@register.inclusion_tag("includes/talebe_foto.html")
def talebe_foto(talebe, size="md"):
    foto = getattr(talebe, "biyometrik_foto", None)
    ad = getattr(talebe, "ad_soyad", "") or ""
    return {
        "foto_url": foto.url if foto else "",
        "bas_harf": ad[:1].upper() if ad else "?",
        "ad_soyad": ad,
        "size": size,
    }
