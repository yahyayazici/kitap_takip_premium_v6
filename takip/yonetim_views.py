from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import (
    Duyuru,
    EtutHocasi,
    ImamMuezzinHavuzKaydi,
    ImamMuezzinListesi,
    PersonelProfili,
    ProgramPlan,
    SinifSube,
    Talebe,
    TemizlikAlani,
    TemizlikGorevlisi,
    TemizlikKati,
    TemizlikListesi,
    YemekciListesi,
    YemekOgun,
    Zimmet,
)
from .imam_muezzin_service import bugunun_atamasi, otomatik_dagit
from .imam_muezzin_yonetim_service import (
    atamalari_temizle,
    ay_araligi,
    gecen_ayi_kopyala,
    gorev_paneli,
    havuz_ekle,
    havuz_sil,
    havuz_temizle,
    havuz_yeniden_dagit,
    liste_olustur,
    ornek_havuz_yukle,
    pdf_baglami,
)
from .temizlik_service import bugunun_atamalari, otomatik_dagit as temizlik_dagit
from .temizlik_yonetim_service import (
    gorevleri_dengele,
    gorevli_ekle,
    gorevli_sil,
    gorevli_tasi,
    kat_ekle,
    kat_sil,
    kontrol_guncelle,
    mahal_ekle,
    mahal_sil,
    mahal_sorumlu_ekle,
    mahal_sorumlu_sil,
    otomatik_gorev_rotasyonu,
    rapor_satirlari,
    sorumlu_ekle,
    sorumlu_sil,
    talebe_ara,
    yonetim_merkezi,
)
from .yemekci_service import bugunun_atamalari as bugunun_yemek_atamalari
from .yemekci_service import otomatik_dagit as yemekci_dagit
from .panel_permissions import yonetim_erisimi_var
from .program_service import bugunun_programi
from .talebe_excel import (
    mevcut_talebeler_xlsx_olustur,
    sablon_xlsx_olustur,
    talebe_excel_ice_aktar,
)
from .yonetim_forms import (
    DuyuruForm,
    ImamMuezzinAtamaFormSet,
    ImamMuezzinListesiForm,
    PersonelProfiliForm,
    ProgramPlanForm,
    ProgramSatirFormSet,
    SinifSubeForm,
    TalebeExcelForm,
    TalebeForm,
    TemizlikAlaniForm,
    TemizlikAtamaFormSet,
    TemizlikListesiForm,
    YemekciAtamaFormSet,
    YemekciListesiForm,
    YemekOgunForm,
)


def yonetici_mi(user):
    return user.is_authenticated and yonetim_erisimi_var(user)


def yonetici_gerekli(view_func):
    return login_required(
        user_passes_test(yonetici_mi)(view_func)
    )


@yonetici_gerekli
def dashboard(request):
    son_talebeler = (
        Talebe.objects
        .select_related("sinif_sube", "etut_hocasi", "dini_ders_hocasi")
        .order_by("-id")[:6]
    )

    son_personeller = (
        EtutHocasi.objects
        .select_related("user")
        .prefetch_related("sorumlu_sinif_subeler")
        .annotate(talebe_sayisi=Count("talebeler"))
        .order_by("-id")[:6]
    )

    siniflar = (
        SinifSube.objects
        .annotate(
            talebe_sayisi=Count("talebeler", distinct=True),
            hoca_sayisi=Count("etut_hocalari", distinct=True),
        )
        .order_by("sinif", "sube")
    )

    context = {
        "toplam_talebe": Talebe.objects.count(),
        "aktif_talebe": Talebe.objects.filter(aktif=True).count(),
        "toplam_personel": PersonelProfili.objects.count(),
        "aktif_personel": PersonelProfili.objects.filter(aktif=True).count(),
        "toplam_sinif": SinifSube.objects.filter(aktif=True).count(),
        "son_talebeler": son_talebeler,
        "son_personeller": son_personeller,
        "siniflar": siniflar[:8],
    }

    return render(
        request,
        "yonetim/dashboard.html",
        context,
    )


@yonetici_gerekli
def sinif_listesi(request):
    siniflar = (
        SinifSube.objects
        .annotate(
            talebe_sayisi=Count("talebeler", distinct=True),
            hoca_sayisi=Count("etut_hocalari", distinct=True),
        )
        .order_by("sinif", "sube")
    )

    return render(
        request,
        "yonetim/sinif_listesi.html",
        {"siniflar": siniflar},
    )


@yonetici_gerekli
def sinif_ekle(request):
    form = SinifSubeForm(request.POST or None)

    if form.is_valid():
        sinif = form.save()
        messages.success(
            request,
            f"{sinif} sınıfı başarıyla eklendi.",
        )
        return redirect("yonetim:sinif_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Sınıf / Şube Ekle",
            "sayfa_aciklama": (
                "Kurumda kullanılacak sınıfı ve şubeyi tanımlayın."
            ),
            "geri_url": "yonetim:sinif_listesi",
        },
    )


@yonetici_gerekli
def sinif_duzenle(request, pk):
    sinif = get_object_or_404(SinifSube, pk=pk)
    form = SinifSubeForm(request.POST or None, instance=sinif)

    if form.is_valid():
        sinif = form.save()
        messages.success(
            request,
            f"{sinif} sınıfı güncellendi.",
        )
        return redirect("yonetim:sinif_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Sınıf / Şube Düzenle",
            "sayfa_aciklama": (
                "Sınıf ve şube bilgilerini güncelleyin."
            ),
            "geri_url": "yonetim:sinif_listesi",
        },
    )


@yonetici_gerekli
def personel_listesi(request):
    personeller = (
        PersonelProfili.objects
        .select_related("user", "etut_hocasi")
        .prefetch_related("etut_hocasi__sorumlu_sinif_subeler")
        .annotate(
            talebe_sayisi=Count("etut_hocasi__talebeler", distinct=True)
        )
        .order_by("ad_soyad")
    )

    return render(
        request,
        "yonetim/personel_listesi.html",
        {"personeller": personeller},
    )


@yonetici_gerekli
def personel_ekle(request):
    form = PersonelProfiliForm(request.POST or None)

    if form.is_valid():
        personel = form.save()
        messages.success(
            request,
            f"{personel.ad_soyad} başarıyla eklendi.",
        )
        return redirect("yonetim:personel_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Personel Ekle",
            "sayfa_aciklama": (
                "Rol, giriş bilgileri ve yetkileri belirleyin."
            ),
            "geri_url": "yonetim:personel_listesi",
        },
    )


@yonetici_gerekli
def personel_duzenle(request, pk):
    personel = get_object_or_404(PersonelProfili, pk=pk)
    form = PersonelProfiliForm(
        request.POST or None,
        instance=personel,
    )

    if form.is_valid():
        personel = form.save()
        messages.success(
            request,
            f"{personel.ad_soyad} güncellendi.",
        )
        return redirect("yonetim:personel_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Personel Düzenle",
            "sayfa_aciklama": (
                "Personel bilgilerini, rolünü ve yetkilerini güncelleyin."
            ),
            "geri_url": "yonetim:personel_listesi",
        },
    )


@yonetici_gerekli
def talebe_listesi(request):
    talebeler = (
        Talebe.objects
        .select_related("sinif_sube", "etut_hocasi", "dini_ders_hocasi")
        .order_by("sinif", "sube", "ad_soyad")
    )

    arama = request.GET.get("q", "").strip()
    sinif_id = request.GET.get("sinif", "").strip()

    if sinif_id.isdigit():
        talebeler = talebeler.filter(sinif_sube_id=int(sinif_id))

    if arama:
        talebeler = talebeler.filter(
            Q(ad_soyad__icontains=arama)
            | Q(talebe_no__icontains=arama)
            | Q(etut_hocasi__ad_soyad__icontains=arama)
            | Q(dini_ders_hocasi__ad_soyad__icontains=arama)
            | Q(sinif_sube__sinif__icontains=arama)
            | Q(sinif_sube__sube__icontains=arama)
        )

    from .talebe_liste_raporu_service import erisilebilir_siniflar

    rapor_kaynak = Talebe.objects.all()
    return render(
        request,
        "yonetim/talebe_listesi.html",
        {
            "talebeler": talebeler,
            "arama": arama,
            "sinif_id": sinif_id,
            "rapor_siniflar": erisilebilir_siniflar(rapor_kaynak),
            "rapor_pdf_url": reverse("yonetim:talebe_liste_raporu_pdf"),
            "kurum_raporu_goster": True,
        },
    )


@yonetici_gerekli
def talebe_liste_raporu_pdf(request):
    from .filter_utils import get_int_list
    from .talebe_liste_raporu_service import talebe_liste_raporu_pdf_yanit

    rapor_turu = request.GET.get("tur", "").strip()
    sinif_sube_ids = get_int_list(request.GET, "sinif_sube")

    return talebe_liste_raporu_pdf_yanit(
        request,
        rapor_turu=rapor_turu,
        sinif_sube_id=sinif_sube_ids[0] if len(sinif_sube_ids) == 1 else None,
        sinif_sube_ids=sinif_sube_ids,
        talebe_qs=Talebe.objects.all(),
    )


@yonetici_gerekli
def talebe_ekle(request):
    form = TalebeForm(request.POST or None)

    if form.is_valid():
        talebe = form.save()
        messages.success(
            request,
            f"{talebe.ad_soyad} başarıyla eklendi. "
            f"Talebe no: {talebe.talebe_no}.",
        )
        return redirect("yonetim:talebe_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Talebe Ekle",
            "sayfa_aciklama": (
                "Talebenin sınıfını ve etüt hocasını belirleyin."
            ),
            "geri_url": "yonetim:talebe_listesi",
        },
    )


@yonetici_gerekli
def talebe_duzenle(request, pk):
    talebe = get_object_or_404(Talebe, pk=pk)
    form = TalebeForm(
        request.POST or None,
        instance=talebe,
    )

    if form.is_valid():
        talebe = form.save()
        messages.success(
            request,
            f"{talebe.ad_soyad} güncellendi.",
        )
        return redirect("yonetim:talebe_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Talebe Düzenle",
            "sayfa_aciklama": (
                "Talebenin kayıt bilgilerini güncelleyin."
            ),
            "geri_url": "yonetim:talebe_listesi",
        },
    )


@yonetici_gerekli
def talebe_excel_mevcut_indir(request):
    try:
        icerik = mevcut_talebeler_xlsx_olustur()
    except ImportError:
        messages.error(
            request,
            "Excel dışa aktarma için openpyxl paketi gerekli.",
        )
        return redirect("yonetim:hizli_kayit")

    response = HttpResponse(
        icerik,
        content_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        'attachment; filename="talebe-veli-listesi.xlsx"'
    )
    return response


@yonetici_gerekli
def talebe_excel_sablon_indir(request):
    try:
        icerik = sablon_xlsx_olustur()
    except ImportError:
        messages.error(
            request,
            "Excel şablonu için openpyxl paketi gerekli. "
            "Sunucuda 'pip install openpyxl' çalıştırın.",
        )
        return redirect("yonetim:talebe_excel_yukle")

    response = HttpResponse(
        icerik,
        content_type=(
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        ),
    )
    response["Content-Disposition"] = (
        'attachment; filename="talebe-sablonu.xlsx"'
    )
    return response


@yonetici_gerekli
def talebe_excel_yukle(request):
    form = TalebeExcelForm(request.POST or None, request.FILES or None)
    sonuc = None

    if request.method == "POST" and form.is_valid():
        try:
            sonuc = talebe_excel_ice_aktar(form.cleaned_data["excel_dosyasi"])
        except ImportError:
            messages.error(
                request,
                "Excel yükleme için openpyxl paketi gerekli. "
                "Sunucuda 'pip install openpyxl' çalıştırın.",
            )
            return redirect("yonetim:talebe_excel_yukle")

        if sonuc.eklenen:
            messages.success(
                request,
                f"{sonuc.eklenen} talebe Excel'den eklendi.",
            )
        if sonuc.guncellenen:
            messages.success(
                request,
                f"{sonuc.guncellenen} talebe güncellendi.",
            )
        if sonuc.veli_hesap:
            messages.success(
                request,
                f"{sonuc.veli_hesap} veli panel hesabı oluşturuldu/güncellendi "
                "(kullanıcı adı: talebe TC, şifre: son 4 hane).",
            )
        if not sonuc.eklenen and not sonuc.guncellenen and not sonuc.hatalar:
            messages.warning(request, "İşlenecek satır bulunamadı.")

        if sonuc.atlanan:
            messages.warning(
                request,
                f"{sonuc.atlanan} satır atlandı.",
            )

        for mesaj in sonuc.bilgi[:8]:
            messages.info(request, mesaj)
        if len(sonuc.bilgi) > 8:
            messages.info(request, f"... ve {len(sonuc.bilgi) - 8} bilgi mesajı daha.")

        if (sonuc.eklenen or sonuc.guncellenen) and not sonuc.hatalar:
            return redirect("yonetim:talebe_listesi")

    return render(
        request,
        "yonetim/talebe_excel_yukle.html",
        {
            "form": form,
            "sonuc": sonuc,
        },
    )


@yonetici_gerekli
def duyuru_listesi(request):
    duyurular = Duyuru.objects.select_related("olusturan").order_by(
        "sira",
        "-baslangic",
        "-id",
    )

    return render(
        request,
        "yonetim/duyuru_listesi.html",
        {"duyurular": duyurular},
    )


@yonetici_gerekli
def duyuru_ekle(request):
    form = DuyuruForm(request.POST or None, request.FILES or None)

    if form.is_valid():
        duyuru = form.save(commit=False)
        duyuru.olusturan = request.user
        duyuru.save()
        messages.success(request, f"“{duyuru.baslik}” duyurusu yayınlandı.")
        return redirect("yonetim:duyuru_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Duyuru Ekle",
            "sayfa_aciklama": (
                "Sol tarafa fotoğraf/video, sağ tarafa metin gelecek şekilde duyuru oluşturun."
            ),
            "geri_url": "yonetim:duyuru_listesi",
            "form_multipart": True,
        },
    )


@yonetici_gerekli
def duyuru_duzenle(request, pk):
    duyuru = get_object_or_404(Duyuru, pk=pk)
    form = DuyuruForm(request.POST or None, request.FILES or None, instance=duyuru)

    if form.is_valid():
        duyuru = form.save()
        messages.success(request, f"“{duyuru.baslik}” güncellendi.")
        return redirect("yonetim:duyuru_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Duyuru Düzenle",
            "sayfa_aciklama": "Duyuru metnini, medyasını, tarihini ve görünürlüğünü güncelleyin.",
            "geri_url": "yonetim:duyuru_listesi",
            "form_multipart": True,
        },
    )


@yonetici_gerekli
@require_POST
def duyuru_sil(request, pk):
    duyuru = get_object_or_404(Duyuru, pk=pk)
    baslik = duyuru.baslik
    duyuru.delete()
    messages.success(request, f"“{baslik}” duyurusu silindi.")
    return redirect("yonetim:duyuru_listesi")


def _program_pdf_yanit(request, program):
    from .views import program_plan_pdf_yanit

    return program_plan_pdf_yanit(request, program)


@yonetici_gerekli
def program_listesi(request):
    programlar = (
        ProgramPlan.objects.prefetch_related("satirlar")
        .annotate(satir_sayisi=Count("satirlar"))
        .order_by("-baslangic_tarihi", "ad")
    )

    return render(
        request,
        "yonetim/program_listesi.html",
        {
            "programlar": programlar,
            "bugun_program": bugunun_programi(),
        },
    )


@yonetici_gerekli
def program_ekle(request):
    form = ProgramPlanForm(request.POST or None)

    if form.is_valid():
        program = form.save(commit=False)
        program.olusturan = request.user
        program.save()
        messages.success(
            request,
            f"“{program.ad}” oluşturuldu. Şimdi saat satırlarını ekleyin.",
        )
        return redirect("yonetim:program_duzenle", pk=program.pk)

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Program Ekle",
            "sayfa_aciklama": "Program adını ve geçerlilik tarihlerini belirleyin.",
            "geri_url": "yonetim:program_listesi",
        },
    )


@yonetici_gerekli
def program_duzenle(request, pk):
    program = get_object_or_404(ProgramPlan, pk=pk)
    form = ProgramPlanForm(request.POST or None, instance=program)
    formset = ProgramSatirFormSet(
        request.POST or None,
        instance=program,
        prefix="satirlar",
    )

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()

        messages.success(request, f"“{program.ad}” güncellendi.")
        return redirect("yonetim:program_duzenle", pk=program.pk)

    return render(
        request,
        "yonetim/program_form.html",
        {
            "form": form,
            "formset": formset,
            "program": program,
        },
    )


@yonetici_gerekli
def program_pdf(request, pk):
    program = get_object_or_404(
        ProgramPlan.objects.prefetch_related("satirlar"),
        pk=pk,
    )
    return _program_pdf_yanit(request, program)


def _imam_pdf_yanit(request, liste):
    from .views import imam_muezzin_pdf_yanit

    return imam_muezzin_pdf_yanit(request, liste)


@yonetici_gerekli
def imam_listesi(request):
    listeler = (
        ImamMuezzinListesi.objects.prefetch_related("atamalar")
        .annotate(gun_sayisi=Count("atamalar"))
        .order_by("-baslangic_tarihi", "ad")
    )

    return render(
        request,
        "yonetim/imam_listesi.html",
        {
            "listeler": listeler,
            "bugun_atama": bugunun_atamasi(),
        },
    )


@yonetici_gerekli
def imam_ekle(request):
    form = ImamMuezzinListesiForm(request.POST or None)

    if form.is_valid():
        liste = form.save(commit=False)
        liste.olusturan = request.user
        liste.save()
        form.save_m2m()
        adet = otomatik_dagit(liste)
        messages.success(
            request,
            f"“{liste.ad}” oluşturuldu. {adet} güne otomatik atama yapıldı.",
        )
        return redirect("yonetim:imam_gorev_panel", pk=liste.pk)

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "İmam / Müezzin Listesi Ekle",
            "sayfa_aciklama": "Tarih aralığı ve talebe havuzunu belirleyin.",
            "geri_url": "yonetim:imam_listesi",
        },
    )


@yonetici_gerekli
def imam_gorev_panel(request, pk):
    liste = get_object_or_404(ImamMuezzinListesi, pk=pk)
    yil_param = request.GET.get("yil", "").strip()
    ay_param = request.GET.get("ay", "").strip()
    yil = int(yil_param) if yil_param.isdigit() else None
    ay = int(ay_param) if ay_param.isdigit() else None

    if request.method == "POST":
        action = request.POST.get("action", "")
        post_yil = request.POST.get("yil", "")
        post_ay = request.POST.get("ay", "")
        if post_yil.isdigit():
            yil = int(post_yil)
        if post_ay.isdigit():
            ay = int(post_ay)

        if action == "olustur" and yil and ay:
            baslangic, bitis = ay_araligi(yil, ay)
            liste.baslangic_tarihi = baslangic
            liste.bitis_tarihi = bitis
            liste.ad = f"İmam Müezzin — {baslangic.strftime('%m.%Y')}"
            liste.save(update_fields=["baslangic_tarihi", "bitis_tarihi", "ad", "guncellenme"])
            imam_s, muezzin_s = ornek_havuz_yukle(liste)
            adet = otomatik_dagit(liste)
            messages.success(
                request,
                f"Örnek liste yüklendi ({imam_s} imam, {muezzin_s} müezzin). {adet} güne atama yapıldı.",
            )
        elif action == "gecen_ayi":
            if gecen_ayi_kopyala(liste):
                adet = havuz_yeniden_dagit(liste)
                msg = "Geçen ayın havuz listesi kopyalandı."
                if adet:
                    msg += f" {adet} günlük atama güncellendi."
                messages.success(request, msg)
            else:
                messages.warning(request, "Kopyalanacak önceki ay listesi bulunamadı.")
        elif action == "temizle":
            havuz_temizle(liste)
            atamalari_temizle(liste)
            messages.success(request, "Tüm listeler ve günlük atamalar temizlendi.")
        elif action == "temizle_imam":
            havuz_temizle(liste, ImamMuezzinHavuzKaydi.Rol.IMAM)
            adet = havuz_yeniden_dagit(liste)
            messages.success(
                request,
                f"İmam listesi temizlendi.{f' {adet} günlük atama güncellendi.' if adet else ''}",
            )
        elif action == "temizle_muezzin":
            havuz_temizle(liste, ImamMuezzinHavuzKaydi.Rol.MUEZZIN)
            adet = havuz_yeniden_dagit(liste)
            messages.success(
                request,
                f"Müezzin listesi temizlendi.{f' {adet} günlük atama güncellendi.' if adet else ''}",
            )
        elif action == "havuz_ekle":
            rol = request.POST.get("rol", "")
            talebe_id = request.POST.get("talebe_id", "")
            if rol in {"imam", "muezzin"} and talebe_id.isdigit() and havuz_ekle(liste, rol, int(talebe_id)):
                adet = havuz_yeniden_dagit(liste)
                msg = "Talebe listeye eklendi."
                if adet:
                    msg += f" {adet} günlük atama güncellendi."
                messages.success(request, msg)
            else:
                messages.error(request, "Talebe eklenemedi.")
        elif action == "havuz_sil":
            kayit_id = request.POST.get("kayit_id", "")
            if kayit_id.isdigit():
                havuz_sil(int(kayit_id), liste)
                adet = havuz_yeniden_dagit(liste)
                msg = "Talebe listeden çıkarıldı."
                if adet:
                    msg += f" {adet} günlük atama güncellendi."
                messages.success(request, msg)

        url = reverse("yonetim:imam_gorev_panel", kwargs={"pk": liste.pk})
        if yil and ay:
            return redirect(f"{url}?yil={yil}&ay={ay}")
        return redirect(url)

    panel = gorev_paneli(liste, yil=yil, ay=ay)
    return render(
        request,
        "yonetim/imam_gorev_panel.html",
        panel,
    )


@yonetici_gerekli
def imam_onizleme(request, pk):
    liste = get_object_or_404(
        ImamMuezzinListesi.objects.prefetch_related("atamalar__imam", "atamalar__muezzin"),
        pk=pk,
    )
    return render(request, "imam_muezzin_pdf.html", pdf_baglami(liste))


@yonetici_gerekli
def imam_duzenle(request, pk):
    liste = get_object_or_404(ImamMuezzinListesi, pk=pk)
    form = ImamMuezzinListesiForm(request.POST or None, instance=liste)
    formset = ImamMuezzinAtamaFormSet(
        request.POST or None,
        instance=liste,
        prefix="atamalar",
    )

    if request.method == "POST" and request.POST.get("action") == "redistribute":
        if form.is_valid():
            liste = form.save()
            adet = otomatik_dagit(liste)
            messages.success(request, f"Liste yeniden dağıtıldı. {adet} gün atandı.")
        else:
            messages.error(request, "Önce form hatalarını düzeltin.")
        return redirect("yonetim:imam_duzenle", pk=liste.pk)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()

        messages.success(request, f"“{liste.ad}” güncellendi.")
        return redirect("yonetim:imam_duzenle", pk=liste.pk)

    return render(
        request,
        "yonetim/imam_form.html",
        {
            "form": form,
            "formset": formset,
            "liste": liste,
        },
    )


@yonetici_gerekli
def imam_pdf(request, pk):
    liste = get_object_or_404(
        ImamMuezzinListesi.objects.prefetch_related(
            "atamalar__imam",
            "atamalar__muezzin",
        ),
        pk=pk,
    )
    return _imam_pdf_yanit(request, liste)


@yonetici_gerekli
def temizlik_alan_listesi(request):
    alanlar = TemizlikAlani.objects.order_by("sira", "ad")

    return render(
        request,
        "yonetim/temizlik_alan_listesi.html",
        {"alanlar": alanlar},
    )


@yonetici_gerekli
def temizlik_alan_ekle(request):
    form = TemizlikAlaniForm(request.POST or None)

    if form.is_valid():
        alan = form.save()
        messages.success(request, f"“{alan.ad}” alanı eklendi.")
        return redirect("yonetim:temizlik_alan_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Temizlik Alanı Ekle",
            "sayfa_aciklama": "Koridor, yemekhane gibi temizlik bölgelerini tanımlayın.",
            "geri_url": "yonetim:temizlik_alan_listesi",
        },
    )


@yonetici_gerekli
def temizlik_alan_duzenle(request, pk):
    alan = get_object_or_404(TemizlikAlani, pk=pk)
    form = TemizlikAlaniForm(request.POST or None, instance=alan)

    if form.is_valid():
        form.save()
        messages.success(request, f"“{alan.ad}” güncellendi.")
        return redirect("yonetim:temizlik_alan_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": f"{alan.ad} · Düzenle",
            "sayfa_aciklama": "Alan bilgisini güncelleyin.",
            "geri_url": "yonetim:temizlik_alan_listesi",
        },
    )


@yonetici_gerekli
def temizlik_listesi(request):
    listeler = (
        TemizlikListesi.objects.prefetch_related("atamalar")
        .annotate(gun_sayisi=Count("atamalar", distinct=True))
        .order_by("-baslangic_tarihi", "ad")
    )

    return render(
        request,
        "yonetim/temizlik_listesi.html",
        {
            "listeler": listeler,
            "bugun_atamalar": bugunun_atamalari(),
        },
    )


@yonetici_gerekli
def temizlik_ekle(request):
    form = TemizlikListesiForm(request.POST or None)

    if form.is_valid():
        liste = form.save(commit=False)
        liste.olusturan = request.user
        liste.save()
        form.save_m2m()
        adet = temizlik_dagit(liste)
        messages.success(
            request,
            f"“{liste.ad}” oluşturuldu. {adet} alan-gün ataması yapıldı.",
        )
        return redirect("yonetim:temizlik_gorev_panel", pk=liste.pk)

    return render(
        request,
        "yonetim/temizlik_liste_form.html",
        {
            "form": form,
            "sayfa_basligi": "Temizlik Listesi Ekle",
            "sayfa_aciklama": "Tarih aralığı ve talebe havuzunu belirleyin. Kat ve mahalleri kayıttan sonra görev panelinden yönetin.",
            "geri_url": "yonetim:temizlik_listesi",
        },
    )


@yonetici_gerekli
def temizlik_gorev_panel(request, pk):
    liste = get_object_or_404(TemizlikListesi, pk=pk)

    if request.GET.get("ajax") == "talebe_ara":
        return JsonResponse(
            {
                "talebeler": talebe_ara(
                    liste,
                    request.GET.get("q", ""),
                )
            }
        )

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "sorumlu_ekle":
            kat = get_object_or_404(TemizlikKati, pk=request.POST.get("kat_id"), liste=liste)
            personel_id = request.POST.get("personel_id", "")
            if personel_id.isdigit() and sorumlu_ekle(kat, int(personel_id)):
                messages.success(request, "Sorumlu personel eklendi.")
            else:
                messages.error(request, "Personel eklenemedi.")
        elif action == "sorumlu_sil":
            kat = get_object_or_404(TemizlikKati, pk=request.POST.get("kat_id"), liste=liste)
            personel_id = request.POST.get("personel_id", "")
            if personel_id.isdigit():
                sorumlu_sil(kat, int(personel_id))
                messages.success(request, "Sorumlu kaldırıldı.")
        elif action == "gorevli_ekle":
            alan = get_object_or_404(TemizlikAlani, pk=request.POST.get("alan_id"))
            talebe_id = request.POST.get("talebe_id", "")
            if talebe_id.isdigit() and gorevli_ekle(liste, alan, int(talebe_id)):
                messages.success(request, "Görevli talebe eklendi.")
            else:
                messages.error(request, "Görevli eklenemedi.")
        elif action == "gorevli_sil":
            gorevli_id = request.POST.get("gorevli_id", "")
            if gorevli_id.isdigit():
                gorevli_sil(int(gorevli_id), liste)
                messages.success(request, "Görevli kaldırıldı.")
        elif action == "gorevli_tasi":
            gorevli_id = request.POST.get("gorevli_id", "")
            hedef_alan_id = request.POST.get("hedef_alan_id", "")
            if (
                gorevli_id.isdigit()
                and hedef_alan_id.isdigit()
                and gorevli_tasi(int(gorevli_id), liste, int(hedef_alan_id))
            ):
                messages.success(request, "Görevli taşındı.")
            else:
                messages.error(request, "Taşıma yapılamadı.")
        elif action == "kat_ekle":
            ad = request.POST.get("kat_ad", "").strip()
            if kat_ekle(liste, ad):
                messages.success(request, f"“{ad}” katı eklendi.")
            else:
                messages.error(request, "Kat adı gerekli.")
        elif action == "mahal_ekle":
            kat = get_object_or_404(TemizlikKati, pk=request.POST.get("kat_id"), liste=liste)
            ad = request.POST.get("mahal_ad", "").strip()
            aciklama = request.POST.get("mahal_aciklama", "").strip()
            if mahal_ekle(kat, ad, aciklama):
                messages.success(request, f"“{ad}” mahali eklendi.")
            else:
                messages.error(request, "Mahal adı gerekli.")
        elif action == "mahal_sil":
            alan = get_object_or_404(TemizlikAlani, pk=request.POST.get("alan_id"))
            if alan.kat and alan.kat.liste_id == liste.pk:
                mahal_sil(alan, liste)
                messages.success(request, "Mahal silindi.")
        elif action == "kat_sil":
            kat = get_object_or_404(TemizlikKati, pk=request.POST.get("kat_id"), liste=liste)
            silinen = kat.ad
            kat_sil(kat)
            messages.success(request, f"“{silinen}” katı silindi.")
        elif action == "kontrol_guncelle":
            alan_id = request.POST.get("alan_id", "")
            durum = request.POST.get("durum", "")
            if alan_id.isdigit() and kontrol_guncelle(
                liste, int(alan_id), durum, request.user
            ):
                messages.success(request, "Kontrol durumu güncellendi.")
        elif action == "gorevleri_dengele":
            adet = gorevleri_dengele(liste)
            messages.success(request, f"Görevler dengelendi ({adet} atama).")
        elif action == "otomatik_rotasyon":
            adet = otomatik_gorev_rotasyonu(liste)
            messages.success(request, f"Görev rotasyonu uygulandı ({adet} kayıt).")

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True})
        return redirect("yonetim:temizlik_gorev_panel", pk=liste.pk)

    context = yonetim_merkezi(liste)
    return render(
        request,
        "yonetim/temizlik_gorev_panel.html",
        context,
    )


@yonetici_gerekli
def temizlik_duzenle(request, pk):
    liste = get_object_or_404(TemizlikListesi, pk=pk)
    form = TemizlikListesiForm(request.POST or None, instance=liste)
    formset = TemizlikAtamaFormSet(
        request.POST or None,
        instance=liste,
        prefix="atamalar",
    )

    if request.method == "POST" and request.POST.get("action") == "redistribute":
        if form.is_valid():
            liste = form.save()
            adet = temizlik_dagit(liste)
            messages.success(
                request,
                f"Liste yeniden dağıtıldı. {adet} alan-gün atandı.",
            )
        else:
            messages.error(request, "Önce form hatalarını düzeltin.")
        return redirect("yonetim:temizlik_duzenle", pk=liste.pk)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()

        messages.success(request, f"“{liste.ad}” güncellendi.")
        return redirect("yonetim:temizlik_duzenle", pk=liste.pk)

    return render(
        request,
        "yonetim/temizlik_form.html",
        {
            "form": form,
            "formset": formset,
            "liste": liste,
        },
    )


def _temizlik_pdf_yanit(request, liste):
    from .views import temizlik_pdf_yanit

    return temizlik_pdf_yanit(request, liste)


@yonetici_gerekli
def temizlik_pdf(request, pk):
    liste = get_object_or_404(TemizlikListesi, pk=pk)
    return _temizlik_pdf_yanit(request, liste)


@yonetici_gerekli
def temizlik_rapor(request, pk):
    import csv
    from io import StringIO

    liste = get_object_or_404(TemizlikListesi, pk=pk)
    merkez = yonetim_merkezi(liste)
    filtre = {
        "kat_id": request.GET.get("kat", ""),
        "mahal_id": request.GET.get("mahal", ""),
        "talebe_id": request.GET.get("talebe", ""),
        "personel_id": request.GET.get("personel", ""),
        "tarih": request.GET.get("tarih", ""),
    }
    satirlar = rapor_satirlari(liste, **filtre)

    if request.GET.get("format") == "excel":
        buffer = StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(["Kat", "Mahal", "Talebe", "Sorumlu Personel", "Durum", "Tarih"])
        for row in satirlar:
            writer.writerow(
                [
                    row["kat"],
                    row["mahal"],
                    row["talebe"],
                    row["sorumlular"],
                    row["durum"],
                    row["tarih"].strftime("%d.%m.%Y"),
                ]
            )
        response = HttpResponse(
            "\ufeff" + buffer.getvalue(),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="temizlik-rapor-{liste.pk}.csv"'
        )
        return response

    if request.GET.get("format") == "pdf":
        q = request.GET.copy()
        q.pop("format", None)
        url = reverse("yonetim:temizlik_pdf", args=[liste.pk])
        if q:
            url = f"{url}?{q.urlencode()}"
        return redirect(url)

    kat_secenekleri = [(k["kat"].pk, k["kat"].ad) for k in merkez["kat_kartlari"]]
    mahal_secenekleri = []
    for k in merkez["kat_kartlari"]:
        for row in k["mahaller"]:
            mahal_secenekleri.append((row["alan"].pk, f"{k['kat'].ad} · {row['alan'].ad}"))

    return render(
        request,
        "yonetim/temizlik_rapor.html",
        {
            "liste": liste,
            "satirlar": satirlar,
            "filtre": filtre,
            "kat_secenekleri": kat_secenekleri,
            "mahal_secenekleri": mahal_secenekleri,
            "talebeler": merkez["talebeler"],
            "personeller": merkez["personeller"],
        },
    )


@yonetici_gerekli
def yemek_ogun_listesi(request):
    ogunler = YemekOgun.objects.order_by("sira", "ad")

    return render(
        request,
        "yonetim/yemek_ogun_listesi.html",
        {"ogunler": ogunler},
    )


@yonetici_gerekli
def yemek_ogun_ekle(request):
    form = YemekOgunForm(request.POST or None)

    if form.is_valid():
        ogun = form.save()
        messages.success(request, f"“{ogun.ad}” öğünü eklendi.")
        return redirect("yonetim:yemek_ogun_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Öğün Ekle",
            "sayfa_aciklama": "Kahvaltı, öğle ve akşam öğünlerini tanımlayın.",
            "geri_url": "yonetim:yemek_ogun_listesi",
        },
    )


@yonetici_gerekli
def yemek_ogun_duzenle(request, pk):
    ogun = get_object_or_404(YemekOgun, pk=pk)
    form = YemekOgunForm(request.POST or None, instance=ogun)

    if form.is_valid():
        form.save()
        messages.success(request, f"“{ogun.ad}” güncellendi.")
        return redirect("yonetim:yemek_ogun_listesi")

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": f"{ogun.ad} · Düzenle",
            "sayfa_aciklama": "Öğün bilgisini güncelleyin.",
            "geri_url": "yonetim:yemek_ogun_listesi",
        },
    )


@yonetici_gerekli
def yemekci_listesi(request):
    listeler = (
        YemekciListesi.objects.prefetch_related("atamalar")
        .annotate(gun_sayisi=Count("atamalar"))
        .order_by("-baslangic_tarihi", "ad")
    )

    return render(
        request,
        "yonetim/yemekci_listesi.html",
        {
            "listeler": listeler,
            "bugun_atamalar": bugunun_yemek_atamalari(),
        },
    )


@yonetici_gerekli
def yemekci_ekle(request):
    form = YemekciListesiForm(request.POST or None)

    if form.is_valid():
        liste = form.save(commit=False)
        liste.olusturan = request.user
        liste.save()
        form.save_m2m()
        adet = yemekci_dagit(liste)
        messages.success(
            request,
            f"“{liste.ad}” oluşturuldu. {adet} öğün-gün ataması yapıldı.",
        )
        return redirect("yonetim:yemekci_duzenle", pk=liste.pk)

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Yemekçilik Listesi Ekle",
            "sayfa_aciklama": "Tarih aralığı, öğünler ve talebe havuzunu belirleyin.",
            "geri_url": "yonetim:yemekci_listesi",
        },
    )


@yonetici_gerekli
def yemekci_duzenle(request, pk):
    liste = get_object_or_404(YemekciListesi, pk=pk)
    form = YemekciListesiForm(request.POST or None, instance=liste)
    formset = YemekciAtamaFormSet(
        request.POST or None,
        instance=liste,
        prefix="atamalar",
    )

    if request.method == "POST" and request.POST.get("action") == "redistribute":
        if form.is_valid():
            liste = form.save()
            adet = yemekci_dagit(liste)
            messages.success(
                request,
                f"Liste yeniden dağıtıldı. {adet} öğün-gün atandı.",
            )
        else:
            messages.error(request, "Önce form hatalarını düzeltin.")
        return redirect("yonetim:yemekci_duzenle", pk=liste.pk)

    if request.method == "POST" and form.is_valid() and formset.is_valid():
        with transaction.atomic():
            form.save()
            formset.save()

        messages.success(request, f"“{liste.ad}” güncellendi.")
        return redirect("yonetim:yemekci_duzenle", pk=liste.pk)

    return render(
        request,
        "yonetim/yemekci_form.html",
        {
            "form": form,
            "formset": formset,
            "liste": liste,
        },
    )


def _yemekci_pdf_yanit(request, liste):
    from .views import yemekcilik_pdf_yanit

    return yemekcilik_pdf_yanit(request, liste)


@yonetici_gerekli
def yemekci_pdf(request, pk):
    liste = get_object_or_404(
        YemekciListesi.objects.prefetch_related(
            "atamalar__ogun",
            "atamalar__talebe",
            "atamalar__yardimci",
        ),
        pk=pk,
    )
    return _yemekci_pdf_yanit(request, liste)
