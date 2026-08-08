"""Bildirim gönderme, listeleme ve e-posta kanalı."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, User
from django.core.mail import send_mail
from django.db.models import Q, QuerySet
from django.urls import reverse
from django.utils.timezone import localdate

from takip.bildirim_models import Bildirim

logger = logging.getLogger(__name__)


def email_kanali_aktif() -> bool:
    if not getattr(settings, "BILDIRIM_EMAIL_AKTIF", True):
        return False
    # Host tanımlıysa veya console backend ile geliştirme açıksa gönder
    backend = getattr(settings, "EMAIL_BACKEND", "") or ""
    if "console" in backend or "locmem" in backend or "filebased" in backend:
        return True
    host = (getattr(settings, "EMAIL_HOST", "") or "").strip()
    return bool(host)


def aktif_bildirimler_qs(
    user: AbstractBaseUser | User,
    *,
    bugun: date | None = None,
) -> QuerySet[Bildirim]:
    bugun = bugun or localdate()
    return (
        Bildirim.objects.filter(alici=user)
        .filter(Q(bitis__isnull=True) | Q(bitis__gte=bugun))
        .order_by("-olusturulma", "-id")
    )


def okunmamis_sayisi(user: AbstractBaseUser | User | None) -> int:
    if not user or not getattr(user, "is_authenticated", False):
        return 0
    return aktif_bildirimler_qs(user).filter(okundu=False).count()


def bildirim_listesi(
    user: AbstractBaseUser | User,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    items = []
    for b in aktif_bildirimler_qs(user)[:limit]:
        items.append(
            {
                "id": b.pk,
                "baslik": b.baslik,
                "mesaj": b.mesaj,
                "tur": b.tur,
                "tur_etiket": b.get_tur_display(),
                "link": b.link or "",
                "okundu": b.okundu,
                "bitis": b.bitis.isoformat() if b.bitis else None,
                "bitis_etiket": b.bitis.strftime("%d.%m.%Y") if b.bitis else "",
                "zaman": b.olusturulma.isoformat(),
                "zaman_etiket": b.olusturulma.strftime("%d.%m %H:%M"),
            }
        )
    return items


def bildirim_gonder(
    alici: User | AbstractBaseUser | None,
    *,
    baslik: str,
    mesaj: str = "",
    tur: str = Bildirim.Tur.GENEL,
    link: str = "",
    bitis: date | None = None,
    olusturan: User | AbstractBaseUser | None = None,
    kaynak_model: str = "",
    kaynak_id: int | None = None,
    email: bool | None = None,
    dedupe: bool = True,
) -> Bildirim | None:
    """Tek kullanıcıya uygulama içi (+ isteğe bağlı e-posta) bildirim."""
    if not alici or not getattr(alici, "pk", None):
        return None

    if dedupe and kaynak_model and kaynak_id:
        mevcut = (
            Bildirim.objects.filter(
                alici=alici,
                kaynak_model=kaynak_model,
                kaynak_id=kaynak_id,
                okundu=False,
            )
            .order_by("-id")
            .first()
        )
        if mevcut:
            # Güncelle (bitiş / metin değişmiş olabilir)
            mevcut.baslik = baslik[:200]
            mevcut.mesaj = mesaj
            mevcut.tur = tur
            mevcut.link = (link or "")[:500]
            mevcut.bitis = bitis
            mevcut.save(
                update_fields=["baslik", "mesaj", "tur", "link", "bitis"]
            )
            return mevcut

    kayit = Bildirim.objects.create(
        alici=alici,
        baslik=(baslik or "Bildirim")[:200],
        mesaj=mesaj or "",
        tur=tur or Bildirim.Tur.GENEL,
        link=(link or "")[:500],
        bitis=bitis,
        olusturan=olusturan if getattr(olusturan, "pk", None) else None,
        kaynak_model=(kaynak_model or "")[:80],
        kaynak_id=kaynak_id,
    )

    gonder_email = email if email is not None else email_kanali_aktif()
    if gonder_email:
        _email_gonder(kayit)

    return kayit


def bildirim_gonder_coklu(
    alicilar: Iterable[User | AbstractBaseUser | None],
    **kwargs,
) -> int:
    sayac = 0
    seen: set[int] = set()
    for alici in alicilar:
        if not alici or not getattr(alici, "pk", None):
            continue
        if alici.pk in seen:
            continue
        seen.add(alici.pk)
        if bildirim_gonder(alici, **kwargs):
            sayac += 1
    return sayac


def vazife_bildirimi_gonder(vazife, *, olusturan=None) -> Bildirim | None:
    """Personel vazife atanınca bildirim + mail."""
    profil = getattr(vazife, "atanan", None)
    user = getattr(profil, "user", None) if profil else None
    if not user:
        return None

    bitis = getattr(vazife, "bitis", None)
    bitis_txt = bitis.strftime("%d.%m.%Y") if bitis else "belirtilmedi"
    try:
        link = reverse("vazife_personel")
    except Exception:
        link = "/panel/vazifelerim/"

    return bildirim_gonder(
        user,
        baslik=f"Yeni vazife: {vazife.baslik}",
        mesaj=(
            f"Size “{vazife.baslik}” vazifesi atandı. "
            f"Şu güne kadar: {bitis_txt}."
            + (f"\n\n{vazife.aciklama}" if (vazife.aciklama or "").strip() else "")
        ),
        tur=Bildirim.Tur.VAZIFE,
        link=link,
        bitis=bitis,
        olusturan=olusturan or getattr(vazife, "atayan", None),
        kaynak_model="PersonelVazife",
        kaynak_id=vazife.pk,
        email=True,
    )


def bildirim_okundu(user, bildirim_id: int) -> bool:
    b = Bildirim.objects.filter(pk=bildirim_id, alici=user).first()
    if not b:
        return False
    b.okundu_isaretle()
    return True


def tumunu_okundu(user) -> int:
    qs = aktif_bildirimler_qs(user).filter(okundu=False)
    n = qs.count()
    from django.utils.timezone import now

    qs.update(okundu=True, okunma_zamani=now())
    return n


def _email_gonder(bildirim: Bildirim) -> bool:
    email = (getattr(bildirim.alici, "email", "") or "").strip()
    if not email:
        return False
    if not email_kanali_aktif():
        return False

    site = getattr(settings, "PANEL_PUBLIC_URL", "") or ""
    link = bildirim.link or ""
    if site and link.startswith("/"):
        link = urljoin(site.rstrip("/") + "/", link.lstrip("/"))

    govde = bildirim.mesaj or bildirim.baslik
    if link:
        govde = f"{govde}\n\nAç: {link}"
    if bildirim.bitis:
        govde += f"\n\nGeçerlilik: {bildirim.bitis.strftime('%d.%m.%Y')} tarihine kadar."

    try:
        from config.branding import PANEL_SHORT as _panel_short
    except Exception:
        _panel_short = "Panel"
    try:
        send_mail(
            subject=f"[{_panel_short}] {bildirim.baslik}",
            message=govde,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None)
            or "noreply@localhost",
            recipient_list=[email],
            fail_silently=True,
        )
        bildirim.email_gonderildi = True
        bildirim.save(update_fields=["email_gonderildi"])
        return True
    except Exception:
        logger.exception("Bildirim e-postası gönderilemedi id=%s", bildirim.pk)
        return False
