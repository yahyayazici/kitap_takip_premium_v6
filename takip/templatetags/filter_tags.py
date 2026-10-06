from django import template

register = template.Library()


def tr_baslik(value) -> str:
    """Türkçe ad: büyük harf İ’yi bozmasın diye kelime başı büyük, gerisi küçük."""
    metin = str(value or "").strip()
    if not metin:
        return ""
    parcalar = []
    for kelime in metin.split():
        ilk = kelime[0]
        if ilk == "i":
            ilk = "İ"
        elif ilk == "ı":
            ilk = "I"
        else:
            ilk = ilk.upper()
        geri = kelime[1:].replace("İ", "i").replace("I", "ı").lower()
        parcalar.append(ilk + geri)
    return " ".join(parcalar)


@register.filter(name="tr_baslik")
def tr_baslik_filtre(value) -> str:
    return tr_baslik(value)


def harf_avatar(value) -> str:
    """Adın ilk ve son kelimesinin baş harfi. Ömer Kerem Sucu → ÖS."""
    parcalar = tr_baslik(value).split()
    if not parcalar:
        return ""
    if len(parcalar) == 1:
        return parcalar[0][:1]
    return parcalar[0][:1] + parcalar[-1][:1]


@register.filter(name="harf_avatar")
def harf_avatar_filtre(value) -> str:
    return harf_avatar(value)


@register.filter
def in_filter(value, selected) -> bool:
    """Seçili liste veya tekil değer içinde mi kontrol eder."""
    if selected is None:
        return False
    if isinstance(selected, (list, tuple, set)):
        return str(value) in {str(x) for x in selected} or value in selected
    return str(value) == str(selected)
