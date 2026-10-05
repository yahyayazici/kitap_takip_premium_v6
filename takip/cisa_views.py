"""ÇİSA raporu — deneme seçimi ve PDF."""

from __future__ import annotations

import io
import re
import zipfile

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.http import require_POST

from takip.cisa_service import (
    cisa_deneme_listesi,
    cisa_rapor,
    cisa_sinif_denemeleri,
    cisa_sinif_raporu,
)
from takip.deneme_kontrol_service import (
    deneme_kontrol_hocalari,
    hoca_sinif_secenekleri,
)
from takip.models import SinifSube
from takip.ogretmen_not_service import ogretmen_sinif_ogrencileri
from takip.pdf_utils import (
    html_to_pdf,
    make_pdf_response,
    pdf_engine_status,
    pdf_error_response,
)
from takip.permissions.decorators import require_permission
from takip.permissions.scope import yetkili_talebeler


def _talebe(request, talebe_id: int):
    return get_object_or_404(
        yetkili_talebeler(request.user, aktif_only=True).select_related("sinif_sube"),
        id=talebe_id,
    )


def _cisa_gruplar(request) -> list[dict]:
    """Hocanın sorumlu sınıfları. Etüt mesulü yalnız kendi sınıfını görür."""
    gruplar = []
    gorulen: set[int] = set()
    for hoca in deneme_kontrol_hocalari(request.user):
        for kart in hoca_sinif_secenekleri(hoca):
            if kart.id in gorulen:
                continue
            gorulen.add(kart.id)
            sinif = SinifSube.objects.filter(pk=kart.id, aktif=True).first()
            if sinif is None:
                continue
            gruplar.append(
                {
                    "id": sinif.id,
                    "etiket": kart.etiket,
                    "seviye": sinif.sinif,
                    "talebeler": ogretmen_sinif_ogrencileri(hoca, sinif),
                }
            )
    return gruplar


def _istenan_sinif_idleri(request) -> list[int]:
    """Tek şube, ya da virgülle birleşik tüm sınıf. Yalnız kendi sınıfları kalır."""
    if request.method == "POST":
        hamlar = request.POST.getlist("sinif")
    else:
        ham = request.GET.get("sinif") or ""
        hamlar = [ham] if ham else []
    ids: list[int] = []
    for ham in hamlar:
        for parca in str(ham).split(","):
            parca = parca.strip()
            if parca.isdigit():
                ids.append(int(parca))
    return ids


def _gorunen_gruplar(request, gruplar: list[dict]) -> tuple[list[dict], int | None]:
    ids = _istenan_sinif_idleri(request)
    if ids:
        izinli = {grup["id"] for grup in gruplar}
        secili = [sinif_id for sinif_id in ids if sinif_id in izinli]
        if secili:
            dar = [grup for grup in gruplar if grup["id"] in secili]
            return dar, secili[0] if len(secili) == 1 else None
    return gruplar, None


def _talebe_listesi(gruplar: list[dict]):
    talebeler = []
    gorulen: set[int] = set()
    for grup in gruplar:
        for talebe in grup["talebeler"]:
            if talebe.id in gorulen:
                continue
            gorulen.add(talebe.id)
            talebeler.append(talebe)
    return talebeler


def _secilen_denemeler(request) -> list[int]:
    secilen = []
    for ham in request.POST.getlist("deneme"):
        if str(ham).isdigit():
            secilen.append(int(ham))
    return secilen


def _cisa_adres(sinif_id: int | None) -> str:
    adres = reverse("cisa_denemeler")
    if sinif_id:
        return f"{adres}?sinif={sinif_id}"
    return adres


def _pdf_bayt(request, talebe, secilen: list[int]) -> tuple[bytes | None, bool]:
    """PDF baytı ve seçilen denemelerde sonuç olup olmadığı."""
    rapor = cisa_rapor(talebe, secilen)
    if rapor is None:
        return None, False
    html = render(
        request,
        "cisa_pdf.html",
        {"rapor": rapor, "olusturma_tarihi": now()},
    ).content.decode("utf-8")
    return html_to_pdf(html, base_url=request.build_absolute_uri("/")) or None, True


def _pdf_adi(ad_soyad: str) -> str:
    ad = re.sub(r'[\\/:*?"<>|\r\n]+', " ", (ad_soyad or "").strip())
    ad = re.sub(r"\s+", " ", ad).strip() or "Talebe"
    return f"{ad} CISA.pdf"


@login_required
@require_permission("deneme", "export_pdf")
def cisa_denemeler(request):
    """Denemeler sekmesi. Üstte deneme seçimi, altta sınıfın talebeleri."""
    gruplar = _cisa_gruplar(request)
    gorunen, sinif_id = _gorunen_gruplar(request, gruplar)
    talebeler = _talebe_listesi(gorunen)
    denemeler = cisa_sinif_denemeleri([t.id for t in talebeler])

    if request.method == "POST":
        secilen = _secilen_denemeler(request)
        if not secilen:
            messages.warning(request, "Rapora girecek deneme seç.")
            return redirect(_cisa_adres(sinif_id))

        ham_talebe = request.POST.get("talebe", "")
        if str(ham_talebe).isdigit():
            talebe = next((t for t in talebeler if t.id == int(ham_talebe)), None)
            if talebe is None:
                messages.warning(request, "Bu talebe senin sınıfında değil.")
                return redirect(_cisa_adres(sinif_id))
            pdf_verisi, sonucu_var = _pdf_bayt(request, talebe, secilen)
            if pdf_verisi:
                return make_pdf_response(pdf_verisi, _pdf_adi(talebe.ad_soyad))
            if not sonucu_var:
                messages.warning(request, "Bu talebenin seçilen denemelerde sonucu yok.")
                return redirect(_cisa_adres(sinif_id))
            return pdf_error_response(
                f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
            )

        ham_rapor = request.POST.get("sinif_rapor", "")
        if str(ham_rapor).strip():
            return _sinif_raporu_pdf(request, gruplar, ham_rapor, secilen, sinif_id)

        return _toplu_pdf(request, talebeler, secilen, sinif_id)

    return render(
        request,
        "cisa_denemeler.html",
        {
            "gruplar": gruplar,
            "gorunen": gorunen,
            "sinif_id": sinif_id,
            "denemeler": denemeler,
            "ogrenci_sayisi": len(talebeler),
        },
    )


def _toplu_pdf(request, talebeler, secilen: list[int], sinif_id: int | None):
    buffer = io.BytesIO()
    yazilan = 0
    motor_hata = False
    kullanilan: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as arsiv:
        for talebe in talebeler:
            pdf_verisi, sonucu_var = _pdf_bayt(request, talebe, secilen)
            if not pdf_verisi:
                motor_hata = motor_hata or sonucu_var
                continue
            ad = _benzersiz_ad(_pdf_adi(talebe.ad_soyad), kullanilan)
            arsiv.writestr(ad, pdf_verisi)
            yazilan += 1
    if not yazilan:
        if motor_hata:
            return pdf_error_response(
                f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
            )
        messages.warning(request, "Seçilen denemelerde raporu olan talebe yok.")
        return redirect(_cisa_adres(sinif_id))
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="CISA sinif.zip"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "no-store"
    return response


def _benzersiz_ad(ad: str, kullanilan: set[str]) -> str:
    if ad not in kullanilan:
        kullanilan.add(ad)
        return ad
    kok, _, uzanti = ad.rpartition(".")
    sira = 2
    while True:
        aday = f"{kok}-{sira}.{uzanti}"
        if aday not in kullanilan:
            kullanilan.add(aday)
            return aday
        sira += 1


def _rapor_basligi(secili: list[dict]) -> str:
    if len(secili) == 1:
        return secili[0]["etiket"]
    seviyeler = []
    for grup in secili:
        seviye = grup.get("seviye") or ""
        if seviye not in seviyeler:
            seviyeler.append(seviye)
    if len(seviyeler) == 1:
        ham = seviyeler[0]
        return f"{ham}. Sınıf" if str(ham).isdigit() else (ham or "Sınıf")
    return " · ".join(grup["etiket"] for grup in secili)


def _sinif_raporu_pdf(request, gruplar, ham_rapor: str, secilen: list[int], sinif_id: int | None):
    istenen = []
    for parca in str(ham_rapor).split(","):
        parca = parca.strip()
        if parca.isdigit():
            istenen.append(int(parca))
    izinli = {grup["id"]: grup for grup in gruplar}
    secili = [izinli[sinif] for sinif in istenen if sinif in izinli]
    if not secili:
        messages.warning(request, "Bu sınıf senin sorumluluğunda değil.")
        return redirect(_cisa_adres(sinif_id))
    talebeler = _talebe_listesi(secili)
    baslik = _rapor_basligi(secili)
    rapor = cisa_sinif_raporu(talebeler, secilen, baslik)
    if rapor is None:
        messages.warning(request, "Seçilen denemelerde sınıf raporu oluşmadı.")
        return redirect(_cisa_adres(sinif_id))
    html = render(
        request,
        "cisa_sinif_pdf.html",
        {"rapor": rapor},
    ).content.decode("utf-8")
    pdf_verisi = html_to_pdf(html, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
        )
    return make_pdf_response(pdf_verisi, _pdf_adi(baslik))


@login_required
@require_permission("deneme", "export_pdf")
def cisa_sec(request, talebe_id: int):
    talebe = _talebe(request, talebe_id)
    return render(
        request,
        "cisa_sec.html",
        {
            "talebe": talebe,
            "denemeler": cisa_deneme_listesi(talebe),
        },
    )


@login_required
@require_permission("deneme", "export_pdf")
@require_POST
def cisa_pdf(request, talebe_id: int):
    talebe = _talebe(request, talebe_id)
    secilen = _secilen_denemeler(request)
    pdf_verisi, sonucu_var = _pdf_bayt(request, talebe, secilen)
    if pdf_verisi:
        return make_pdf_response(pdf_verisi, _pdf_adi(talebe.ad_soyad))
    if not sonucu_var:
        messages.warning(request, "Rapora girecek deneme seç.")
        return redirect("cisa_sec", talebe_id=talebe.id)
    return pdf_error_response(
        f"PDF oluşturulamadı. (Motor: {pdf_engine_status()})",
    )
