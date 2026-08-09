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
