"""Hatim Takip Merkezi görünümleri."""

from __future__ import annotations

import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.timezone import localdate

from takip.hatim_forms import HatimProgramTamamlaForm, HatimProgramiForm
from takip.hatim_models import CuzAtamasi, HatimDonemi, HatimProgrami
from takip.hatim_service import (
    aktif_donem,
    aktif_hatim_programlari,
    atama_basladi,
    atama_geri_al,
    atama_tamamla,
    cuz_cakisma_kontrolu,
    cuzleri_dagit,
    dagitilmayan_cuzler,
    donem_cuz_ozeti,
    donem_ilerleme_istatistik,
    gecmis_hatim_programlari,
    gecmis_rapor_satirlari,
    grup_mesaj_taslagi,
    hatim_gorebilir,
    hatim_yonetebilir,
    kisisel_mesaj_taslagi,
    personel_aktif_gorevleri,
    program_baslat,
    program_tamamla,
    whatsapp_paylas_url,
    yetkili_hatim_programlari,
    yeni_donem_baslat,
)
from takip.permissions.decorators import require_permission
from takip.permissions.service import can


def _program_erisim(request, pk: int) -> HatimProgrami:
    program = get_object_or_404(HatimProgrami, pk=pk)
    if not yetkili_hatim_programlari(request.user).filter(pk=pk).exists():
        messages.error(request, "Bu hatim programına erişiminiz yok.")
        raise PermissionError
    return program


@login_required
@require_permission("hatim_takip", "view")
def hatim_aktif_listesi(request):
    programlar = aktif_hatim_programlari(request.user).prefetch_related("donemler")
    taslaklar = []
    if hatim_yonetebilir(request.user):
        taslaklar = HatimProgrami.objects.filter(durum=HatimProgrami.Durum.TASLAK)
    return render(
        request,
        "hatim_aktif_listesi.html",
        {
            "programlar": programlar,
            "taslaklar": taslaklar,
            "yonetici": hatim_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("hatim_takip", "create")
def hatim_olustur(request):
    form = HatimProgramiForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        program = form.save(commit=False)
        program.olusturan = request.user
        program.durum = HatimProgrami.Durum.TASLAK
        program.save()
        katilimcilar = form.cleaned_data.get("katilimcilar") or []
        if program.tur == HatimProgrami.Tur.PERSONEL and katilimcilar:
            program_baslat(program, katilimcilar, olusturan=request.user)
            messages.success(request, f"“{program.ad}” oluşturuldu ve başlatıldı.")
        else:
            messages.success(request, f"“{program.ad}” taslak olarak kaydedildi.")
        return redirect("hatim_detay", pk=program.pk)
    return render(
        request,
        "hatim_form.html",
        {"form": form, "baslik": "Yeni Hatim Oluştur"},
    )


@login_required
@require_permission("hatim_takip", "view")
def hatim_detay(request, pk: int):
    try:
        program = _program_erisim(request, pk)
    except PermissionError:
        return redirect("hatim_aktif_listesi")

    donem_id = request.GET.get("donem")
    donemler = program.donemler.order_by("sira")
    donem = aktif_donem(program)
    if donem_id:
        donem = get_object_or_404(HatimDonemi, pk=donem_id, program=program)

    if donem:
        from takip.hatim_service import gecikmisleri_isaretle

        gecikmisleri_isaretle(donem)

    filtre_durum = request.GET.get("durum", "")
    filtre_katilimci = request.GET.get("katilimci", "")
    filtre_cuz = request.GET.get("cuz", "")

    atamalar = []
    cuz_ozet = []
    istat = {}
    if donem:
        atamalar = list(
            donem.cuz_atamalari.select_related("katilimci", "katilimci__personel")
        )
        if filtre_durum:
            atamalar = [a for a in atamalar if a.durum == filtre_durum]
        if filtre_katilimci:
            atamalar = [
                a
                for a in atamalar
                if str(a.katilimci_id) == filtre_katilimci
            ]
        if filtre_cuz:
            try:
                num = int(filtre_cuz)
                atamalar = [a for a in atamalar if num in a.cuz_numaralari()]
            except ValueError:
                pass
        cuz_ozet = donem_cuz_ozeti(donem)
        if filtre_durum:
            cuz_ozet = [c for c in cuz_ozet if c.durum == filtre_durum]
        if filtre_cuz:
            try:
                num = int(filtre_cuz)
                cuz_ozet = [c for c in cuz_ozet if c.numara == num]
            except ValueError:
                pass
        istat = donem_ilerleme_istatistik(donem)

    paylasim_metni = grup_mesaj_taslagi(program, donem) if donem else ""
    whatsapp_url = whatsapp_paylas_url(paylasim_metni) if paylasim_metni else ""
    iletisim_paylas = can(request.user, "iletisim_merkezi", "share")

    return render(
        request,
        "hatim_detay.html",
        {
            "program": program,
            "donem": donem,
            "donemler": donemler,
            "atamalar": atamalar,
            "cuz_ozet": cuz_ozet,
            "istat": istat,
            "cakismalar": cuz_cakisma_kontrolu(donem) if donem else [],
            "dagitilmayan": dagitilmayan_cuzler(donem) if donem else [],
            "yonetici": hatim_yonetebilir(request.user),
            "filtre_durum": filtre_durum,
            "filtre_katilimci": filtre_katilimci,
            "filtre_cuz": filtre_cuz,
            "paylasim_metni": paylasim_metni,
            "whatsapp_url": whatsapp_url,
            "iletisim_paylas": iletisim_paylas,
            "durum_secenekleri": CuzAtamasi.Durum.choices,
        },
    )


@login_required
@require_permission("hatim_takip", "view")
def hatim_cuz_dagitim(request, pk: int | None = None):
    if pk is None:
        aktif = list(aktif_hatim_programlari(request.user))
        if len(aktif) == 1:
            return redirect("hatim_cuz_dagitim", pk=aktif[0].pk)
        return render(
            request,
            "hatim_secim.html",
            {
                "baslik": "Cüz Dağıtımı",
                "programlar": aktif,
                "hedef": "hatim_cuz_dagitim",
            },
        )
    try:
        program = _program_erisim(request, pk)
    except PermissionError:
        return redirect("hatim_aktif_listesi")

    donem = aktif_donem(program)
    if not donem:
        messages.warning(request, "Aktif dönem bulunamadı.")
        return redirect("hatim_detay", pk=program.pk)

    if request.method == "POST" and hatim_yonetebilir(request.user):
        aksiyon = request.POST.get("aksiyon")
        if aksiyon == "yeniden_hesapla":
            cuzleri_dagit(program, donem)
            messages.success(request, "Cüz dağıtımı yeniden hesaplandı.")
        elif aksiyon == "manuel":
            manuel: dict[int, tuple[int, int]] = {}
            for kat in program.katilimcilar.filter(aktif=True):
                bas_key = f"cuz_bas_{kat.pk}"
                bit_key = f"cuz_bit_{kat.pk}"
                if bas_key in request.POST and bit_key in request.POST:
                    try:
                        manuel[kat.pk] = (
                            int(request.POST[bas_key]),
                            int(request.POST[bit_key]),
                        )
                    except ValueError:
                        pass
            if manuel:
                cuzleri_dagit(program, donem, manuel=manuel)
                messages.success(request, "Manuel dağıtım kaydedildi.")
        return redirect("hatim_cuz_dagitim", pk=program.pk)

    atamalar = donem.cuz_atamalari.select_related("katilimci").order_by(
        "katilimci__sira"
    )
    return render(
        request,
        "hatim_cuz_dagitim.html",
        {
            "program": program,
            "donem": donem,
            "atamalar": atamalar,
            "cakismalar": cuz_cakisma_kontrolu(donem),
            "dagitilmayan": dagitilmayan_cuzler(donem),
            "yonetici": hatim_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("hatim_takip", "view")
def hatim_tamamlanma(request, pk: int | None = None):
    if pk is None:
        aktif = list(aktif_hatim_programlari(request.user))
        if len(aktif) == 1:
            return redirect("hatim_tamamlanma", pk=aktif[0].pk)
        return render(
            request,
            "hatim_secim.html",
            {
                "baslik": "Tamamlanma Takibi",
                "programlar": aktif,
                "hedef": "hatim_tamamlanma",
            },
        )
    try:
        program = _program_erisim(request, pk)
    except PermissionError:
        return redirect("hatim_aktif_listesi")

    donem = aktif_donem(program)
    atamalar = []
    if donem:
        atamalar = donem.cuz_atamalari.select_related("katilimci").order_by(
            "katilimci__sira"
        )

    return render(
        request,
        "hatim_tamamlanma.html",
        {
            "program": program,
            "donem": donem,
            "atamalar": atamalar,
            "yonetici": hatim_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("hatim_takip", "view")
def hatim_gecmis(request):
    programlar = gecmis_hatim_programlari(request.user)
    satirlar = [gecmis_rapor_satirlari(p) for p in programlar]
    return render(
        request,
        "hatim_gecmis.html",
        {
            "programlar": programlar,
            "satirlar": satirlar,
            "yonetici": hatim_yonetebilir(request.user),
        },
    )


@login_required
@require_permission("hatim_takip", "edit")
def hatim_program_tamamla(request, pk: int):
    program = get_object_or_404(HatimProgrami, pk=pk)
    form = HatimProgramTamamlaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        program_tamamla(
            program,
            dua_yapildi=form.cleaned_data.get("dua_yapildi", False),
        )
        messages.success(request, "Hatim programı tamamlandı.")
        return redirect("hatim_gecmis")
    return render(
        request,
        "hatim_program_tamamla.html",
        {"program": program, "form": form},
    )


@login_required
@require_permission("hatim_takip", "edit")
def hatim_program_durdur(request, pk: int):
    program = get_object_or_404(HatimProgrami, pk=pk)
    program.durum = HatimProgrami.Durum.DURDURULDU
    program.save(update_fields=["durum", "guncellenme"])
    messages.info(request, "Program durduruldu.")
    return redirect("hatim_aktif_listesi")


@login_required
@require_permission("hatim_takip", "edit")
def hatim_yeni_donem(request, pk: int):
    program = get_object_or_404(HatimProgrami, pk=pk)
    donem = yeni_donem_baslat(program)
    if donem:
        messages.success(request, f"Dönem {donem.sira} oluşturuldu.")
    else:
        messages.warning(request, "Yeni dönem oluşturulamadı.")
    return redirect("hatim_detay", pk=program.pk)


@login_required
def hatim_atama_basladi(request, pk: int):
    if request.method != "POST":
        return redirect("dashboard")
    if not hatim_gorebilir(request.user):
        messages.error(request, "Yetkiniz yok.")
        return redirect("dashboard")
    atama = get_object_or_404(CuzAtamasi, pk=pk)
    try:
        atama_basladi(atama, request.user)
        messages.success(request, "Okumaya başladığınız kaydedildi.")
    except PermissionError:
        messages.error(request, "Bu işlemi yapamazsınız.")
    return redirect("dashboard")


@login_required
def hatim_atama_tamamla(request, pk: int):
    if request.method != "POST":
        return redirect("dashboard")
    if not hatim_gorebilir(request.user):
        messages.error(request, "Yetkiniz yok.")
        return redirect("dashboard")
    atama = get_object_or_404(CuzAtamasi, pk=pk)
    try:
        atama_tamamla(atama, request.user)
        messages.success(request, "Dönem tamamlamanız kaydedildi.")
    except PermissionError:
        messages.error(request, "Bu işlemi yapamazsınız.")
    return redirect("dashboard")


@login_required
@require_permission("hatim_takip", "edit")
def hatim_atama_geri_al(request, pk: int):
    atama = get_object_or_404(CuzAtamasi, pk=pk)
    atama_geri_al(atama, request.user)
    messages.info(request, "Tamamlama kaydı geri alındı.")
    return redirect("hatim_tamamlanma", pk=atama.donem.program_id)


@login_required
@require_permission("hatim_takip", "view")
def hatim_kisisel_mesaj(request, pk: int):
    atama = get_object_or_404(CuzAtamasi, pk=pk)
    if not hatim_yonetebilir(request.user):
        if atama.katilimci.user_id != request.user.pk:
            messages.error(request, "Yetkiniz yok.")
            return redirect("dashboard")
    metin = kisisel_mesaj_taslagi(atama)
    return render(
        request,
        "hatim_mesaj_taslak.html",
        {
            "metin": metin,
            "whatsapp_url": whatsapp_paylas_url(metin),
            "atama": atama,
        },
    )


@login_required
@require_permission("hatim_takip", "export_excel")
def hatim_gecmis_excel(request):
    import openpyxl

    programlar = gecmis_hatim_programlari(request.user)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Geçmiş Hatimler"
    ws.append(
        [
            "Hatim",
            "Tür",
            "Başlangıç",
            "Bitiş",
            "Tekrar",
            "Dönem",
            "Tamamlanan dönem",
            "Zamanında %",
            "Katılımcı",
        ]
    )
    for p in programlar:
        s = gecmis_rapor_satirlari(p)
        ws.append(
            [
                s["ad"],
                s["tur"],
                s["baslangic"].isoformat() if s["baslangic"] else "",
                s["bitis"].isoformat() if s["bitis"] else "",
                s["tekrar"],
                s["donem_sayisi"],
                s["tamamlanan_donem"],
                s["zamaninda_oran"],
                s["katilimci_sayisi"],
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="hatim_gecmis.xlsx"'
    return response


@login_required
@require_permission("hatim_takip", "export_pdf")
def hatim_gecmis_pdf(request):
    from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_error_response

    programlar = gecmis_hatim_programlari(request.user)
    satirlar = [gecmis_rapor_satirlari(p) for p in programlar]
    html = render(
        request,
        "hatim_gecmis_pdf.html",
        {"satirlar": satirlar, "bugun": localdate()},
    ).content.decode("utf-8")
    try:
        pdf = html_to_pdf(html)
    except Exception as exc:
        return pdf_error_response(str(exc))
    return make_pdf_response(pdf, "hatim_gecmis.pdf")
