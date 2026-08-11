"""TC kimlik doğrulama yardımcıları."""

from __future__ import annotations

import re

from django.core.exceptions import ValidationError


def tc_normalize(deger: str) -> str:
    return re.sub(r"\D", "", deger or "")


def tc_dogrula(deger: str, *, zorunlu: bool = True) -> str:
    tc = tc_normalize(deger)
    if not tc:
        if zorunlu:
            raise ValidationError("TC kimlik no zorunludur.")
        return ""
    if len(tc) != 11:
        raise ValidationError("TC kimlik no 11 haneli olmalıdır.")
    if tc[0] == "0":
        raise ValidationError("Geçersiz TC kimlik no.")
    return tc


def veli_sifre_tc_son4(tc: str) -> str:
    tc = tc_dogrula(tc)
    return tc[-4:]


def talebe_tc_cakisma_var_mi(
    tc: str,
    *,
    haric_pk: int | None = None,
    sadece_aktif: bool = True,
) -> bool:
    from takip.models import Talebe

    qs = Talebe.objects.filter(tc_kimlik=tc)
    if sadece_aktif:
        qs = qs.filter(aktif=True)
    if haric_pk:
        qs = qs.exclude(pk=haric_pk)
    return qs.exists()


def pasif_talebe_tc_temizle(tc: str, *, haric_pk: int | None = None) -> int:
    """Yeni kayıt için pasif talebedeki eski TC'yi boşalt."""
    from takip.models import Talebe

    qs = Talebe.objects.filter(tc_kimlik=tc, aktif=False)
    if haric_pk:
        qs = qs.exclude(pk=haric_pk)
    return qs.update(tc_kimlik="")
