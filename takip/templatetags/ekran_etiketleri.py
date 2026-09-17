"""Ekran modülü şablon yardımcıları."""

from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="kisi_adi")
def kisi_adi(kullanici, bos_deger: str = "—") -> str:
    """Kullanıcının görünen adı; kayıt yoksa ``bos_deger``.

    Şablonda ``{{ x.get_full_name|default:x.username }}`` yazmak, ``x`` None
    olduğunda ``VariableDoesNotExist`` fırlatır: ``default`` filtresinin
    ARGÜMANI her durumda çözülür ve None üzerinde ``username`` araması
    hata verir. İlgili kullanıcılar ``on_delete=SET_NULL`` ile
    boşalabildiği için (silinen personel, sistem tarafından yazılan kayıt)
    bu gerçek bir 500 yoludur. Bu filtre o durumu tek yerde ele alır.
    """
    if not kullanici:
        return bos_deger

    tam_ad = (getattr(kullanici, "get_full_name", lambda: "")() or "").strip()
    if tam_ad:
        return tam_ad

    kullanici_adi = (getattr(kullanici, "username", "") or "").strip()
    return kullanici_adi or bos_deger
