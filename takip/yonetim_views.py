from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import (
    CumaDurumMetni,
    Duyuru,
    EtutHocasi,
    HaftalikSohbetMevzuu,
    ImamMuezzinHavuzKaydi,
    ImamMuezzinListesi,
    PanelKisayol,
    PanelKisayolGorsel,
    PanelMetrik,
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
from .dashboard_service import dashboard_kisayollari, dashboard_metrikleri
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
from .panel_permissions import yonetim_erisimi_var
from .personel_giris_service import (
    personel_giris_kaydi_yenile,
    personel_giris_kayitlari_yenile,
    personel_giris_pdf_olustur,
    personel_giris_zip_olustur,
)
from .program_service import bugunun_programi
from .talebe_excel import (
    mevcut_talebeler_xlsx_olustur,
    sablon_xlsx_olustur,
    talebe_excel_ice_aktar,
)
from .yonetim_forms import (
    CumaDurumMetniForm,
    DuyuruForm,
    HaftalikSohbetMevzuuForm,
    ImamMuezzinAtamaFormSet,
    ImamMuezzinListesiForm,
    PersonelProfiliForm,
    ProgramFaaliyetTuruForm,
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
        "kisayollar": dashboard_kisayollari(request.user, hedef="yonetim"),
        "metrikler": dashboard_metrikleri(
            request.user,
            hedef="yonetim",
            baglam={
                "talebe_sayisi": Talebe.objects.filter(aktif=True).count(),
            },
        ),
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
def brans_listesi(request):
    from takip.models import Brans

    branslar = (
        Brans.objects.annotate(ders_sayisi=Count("dersler", distinct=True))
        .order_by("sira", "ad")
    )
    return render(
        request,
        "yonetim/brans_listesi.html",
        {"branslar": branslar},
    )


@yonetici_gerekli
def brans_ekle(request):
    from takip.yonetim_forms import BransForm

    form = BransForm(request.POST or None)
    if form.is_valid():
        brans = form.save()
        messages.success(request, f"«{brans.ad}» branşı eklendi.")
        return redirect("yonetim:brans_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Branş Ekle",
            "sayfa_aciklama": "Öğretmen branşlarını buradan tanımlayın.",
            "geri_url": "yonetim:brans_listesi",
        },
    )


@yonetici_gerekli
def brans_duzenle(request, pk):
    from takip.models import Brans
    from takip.yonetim_forms import BransForm

    brans = get_object_or_404(Brans, pk=pk)
    form = BransForm(request.POST or None, instance=brans)
    if form.is_valid():
        brans = form.save()
        messages.success(request, f"«{brans.ad}» branşı güncellendi.")
        return redirect("yonetim:brans_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Branş Düzenle",
            "sayfa_aciklama": "Branş adını, sırasını veya durumunu güncelleyin.",
            "geri_url": "yonetim:brans_listesi",
        },
    )


@yonetici_gerekli
def ders_listesi(request):
    from takip.models import Ders

    dersler = Ders.objects.select_related("brans").order_by("sira", "ad")
    return render(
        request,
        "yonetim/ders_listesi.html",
        {"dersler": dersler},
    )


@yonetici_gerekli
def ders_ekle(request):
    from takip.yonetim_forms import DersForm

    form = DersForm(request.POST or None)
    if form.is_valid():
        ders = form.save()
        messages.success(request, f"«{ders.ad}» dersi eklendi.")
        return redirect("yonetim:ders_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Ders Ekle",
            "sayfa_aciklama": "Öğretmen not girişinde görünen dersleri tanımlayın.",
            "geri_url": "yonetim:ders_listesi",
        },
    )


@yonetici_gerekli
def ders_duzenle(request, pk):
    from takip.models import Ders
    from takip.yonetim_forms import DersForm

    ders = get_object_or_404(Ders, pk=pk)
    form = DersForm(request.POST or None, instance=ders)
    if form.is_valid():
        ders = form.save()
        messages.success(request, f"«{ders.ad}» dersi güncellendi.")
        return redirect("yonetim:ders_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Ders Düzenle",
            "sayfa_aciklama": "Ders adı, branş ve sırayı güncelleyin.",
            "geri_url": "yonetim:ders_listesi",
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
    aktif_personel_sayisi = PersonelProfili.objects.filter(
        aktif=True,
        user__isnull=False,
        user__is_active=True,
    ).count()

    return render(
        request,
        "yonetim/personel_listesi.html",
        {
            "personeller": personeller,
            "aktif_personel_sayisi": aktif_personel_sayisi,
        },
    )


@yonetici_gerekli
@require_POST
def personel_giris_pdf_toplu(request):
    from takip.pdf_utils import pdf_error_response

    personeller = (
        PersonelProfili.objects
        .select_related("user")
        .filter(aktif=True, user__isnull=False, user__is_active=True)
        .order_by("ad_soyad")
    )
    kayitlar = personel_giris_kayitlari_yenile(personeller)
    if not kayitlar:
        messages.error(request, "PDF oluşturulacak aktif personel bulunamadı.")
        return redirect("yonetim:personel_listesi")

    zip_dosya = personel_giris_zip_olustur(kayitlar, request=request)
    if not zip_dosya:
        return pdf_error_response("Giriş PDF arşivi oluşturulamadı.")

    response = HttpResponse(zip_dosya, content_type="application/zip")
    response["Content-Disposition"] = (
        'attachment; filename="personel-giris-bilgileri.zip"'
    )
    return response


@yonetici_gerekli
@require_POST
def personel_giris_pdf_tek(request, pk):
    from takip.pdf_utils import pdf_error_response

    personel = get_object_or_404(
        PersonelProfili.objects.select_related("user"),
        pk=pk,
        aktif=True,
    )
    kayit = personel_giris_kaydi_yenile(personel)
    if not kayit:
        messages.error(request, "Bu personel için giriş bilgisi oluşturulamadı.")
        return redirect("yonetim:personel_listesi")

    from takip.pdf_utils import make_pdf_response

    pdf = personel_giris_pdf_olustur(kayit, request=request)
    if not pdf:
        return pdf_error_response("Giriş PDF'i oluşturulamadı.")

    dosya = personel.ad_soyad.lower().replace(" ", "-")
    return make_pdf_response(pdf, f"giris-{dosya}.pdf")


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
    durum = (request.GET.get("durum") or "aktif").strip().lower()
    if durum not in {"aktif", "pasif", "hepsi"}:
        durum = "aktif"

    if durum == "aktif":
        talebeler = talebeler.filter(aktif=True)
    elif durum == "pasif":
        talebeler = talebeler.filter(aktif=False)

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
            "durum": durum,
            "rapor_siniflar": erisilebilir_siniflar(rapor_kaynak),
            "rapor_pdf_url": reverse("yonetim:talebe_liste_raporu_pdf"),
            "rapor_excel_url": reverse("yonetim:talebe_liste_excel"),
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
def talebe_liste_excel(request):
    from .talebe_liste_raporu_service import talebe_liste_excel_yanit

    qs = Talebe.objects.all()
    sinif_id = request.GET.get("sinif", "").strip()
    if sinif_id.isdigit():
        qs = qs.filter(sinif_sube_id=int(sinif_id))
    arama = request.GET.get("q", "").strip()
    if arama:
        qs = qs.filter(
            Q(ad_soyad__icontains=arama)
            | Q(talebe_no__icontains=arama)
            | Q(etut_hocasi__ad_soyad__icontains=arama)
        )

    return talebe_liste_excel_yanit(
        talebe_qs=qs,
        baslik="Talebe Listesi — Kurum",
        dosya_adi="talebe-listesi-kurum.xlsx",
    )


@yonetici_gerekli
def _talebe_form_context(form, *, sayfa_basligi, sayfa_aciklama):
    from takip.turkiye_il_ilce import il_ilce_haritasi

    return {
        "form": form,
        "sayfa_basligi": sayfa_basligi,
        "sayfa_aciklama": sayfa_aciklama,
        "geri_url": "yonetim:talebe_listesi",
        "il_ilce_json": il_ilce_haritasi(),
    }


@yonetici_gerekli
def talebe_ekle(request):
    form = TalebeForm(request.POST or None, request.FILES or None)

    if form.is_valid():
        talebe = form.save()
        form.veli_kaydet(talebe)
        messages.success(
            request,
            f"{talebe.ad_soyad} başarıyla eklendi. "
            f"Talebe no: {talebe.talebe_no}.",
        )
        return redirect("yonetim:talebe_listesi")

    return render(
        request,
        "yonetim/talebe_kayit_form.html",
        _talebe_form_context(
            form,
            sayfa_basligi="Talebe Ekle",
            sayfa_aciklama="Kimlik, eğitim ve veli bilgilerini eksiksiz doldurun.",
        ),
    )


@yonetici_gerekli
def talebe_duzenle(request, pk):
    talebe = get_object_or_404(Talebe, pk=pk)
    form = TalebeForm(
        request.POST or None,
        request.FILES or None,
        instance=talebe,
    )

    if form.is_valid():
        talebe = form.save()
        form.veli_kaydet(talebe)
        messages.success(
            request,
            f"{talebe.ad_soyad} güncellendi.",
        )
        return redirect("yonetim:talebe_listesi")

    return render(
        request,
        "yonetim/talebe_kayit_form.html",
        _talebe_form_context(
            form,
            sayfa_basligi="Talebe Düzenle",
            sayfa_aciklama="Talebenin kayıt bilgilerini güncelleyin.",
        ),
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


@yonetici_gerekli
def sohbet_mevzuu_listesi(request):
    mevzular = HaftalikSohbetMevzuu.objects.select_related("olusturan").order_by(
        "-hafta_baslangic",
        "-id",
    )
    return render(
        request,
        "yonetim/sohbet_mevzuu_listesi.html",
        {"mevzular": mevzular},
    )


@yonetici_gerekli
def sohbet_mevzuu_ekle(request):
    form = HaftalikSohbetMevzuuForm(request.POST or None)
    if form.is_valid():
        mevzu = form.save(commit=False)
        mevzu.olusturan = request.user
        mevzu.save()
        messages.success(request, f"“{mevzu.baslik}” yayınlandı.")
        return redirect("yonetim:sohbet_mevzuu_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Sohbet Mevzuu Ekle",
            "sayfa_aciklama": "Veli panelinde görünecek haftalık sohbet başlığı ve içeriğini girin.",
            "geri_url": "yonetim:sohbet_mevzuu_listesi",
        },
    )


@yonetici_gerekli
def sohbet_mevzuu_duzenle(request, pk):
    mevzu = get_object_or_404(HaftalikSohbetMevzuu, pk=pk)
    form = HaftalikSohbetMevzuuForm(request.POST or None, instance=mevzu)
    if form.is_valid():
        mevzu = form.save()
        messages.success(request, f"“{mevzu.baslik}” güncellendi.")
        return redirect("yonetim:sohbet_mevzuu_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Sohbet Mevzuu Düzenle",
            "sayfa_aciklama": "Başlık, içerik ve hafta bilgisini güncelleyin.",
            "geri_url": "yonetim:sohbet_mevzuu_listesi",
        },
    )


@yonetici_gerekli
@require_POST
def sohbet_mevzuu_sil(request, pk):
    mevzu = get_object_or_404(HaftalikSohbetMevzuu, pk=pk)
    baslik = mevzu.baslik
    mevzu.delete()
    messages.success(request, f"“{baslik}” silindi.")
    return redirect("yonetim:sohbet_mevzuu_listesi")


@yonetici_gerekli
def cuma_durum_listesi(request):
    metinler = CumaDurumMetni.objects.select_related("olusturan").order_by(
        "sira", "-id"
    )
    return render(
        request,
        "yonetim/cuma_durum_listesi.html",
        {"metinler": metinler},
    )


@yonetici_gerekli
def cuma_durum_ekle(request):
    form = CumaDurumMetniForm(request.POST or None)
    if form.is_valid():
        kayit = form.save(commit=False)
        kayit.olusturan = request.user
        kayit.save()
        messages.success(request, "Cuma durum metni eklendi.")
        return redirect("yonetim:cuma_durum_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "baslik": "Cuma Durum Metni Ekle",
            "aciklama": "Personelin WhatsApp durumunda kullanacağı hadis veya söz.",
            "geri_url": "yonetim:cuma_durum_listesi",
        },
    )


@yonetici_gerekli
def cuma_durum_duzenle(request, pk):
    kayit = get_object_or_404(CumaDurumMetni, pk=pk)
    form = CumaDurumMetniForm(request.POST or None, instance=kayit)
    if form.is_valid():
        form.save()
        messages.success(request, "Metin güncellendi.")
        return redirect("yonetim:cuma_durum_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "baslik": "Cuma Durum Metni Düzenle",
            "aciklama": "Hadis metni, kaynak, tema veya belirli Cuma ataması.",
            "geri_url": "yonetim:cuma_durum_listesi",
        },
    )


@yonetici_gerekli
@require_POST
def cuma_durum_sil(request, pk):
    kayit = get_object_or_404(CumaDurumMetni, pk=pk)
    ozet = str(kayit)[:40]
    kayit.delete()
    messages.success(request, f"“{ozet}” silindi.")
    return redirect("yonetim:cuma_durum_listesi")


@yonetici_gerekli
def kisayol_gorsel_listesi(request):
    from takip.dashboard_service import ICON_SECENEKLERI

    kayitlar = list(PanelKisayol.objects.order_by("sira", "id"))
    return render(
        request,
        "yonetim/kisayol_gorsel_listesi.html",
        {
            "kayitlar": kayitlar,
            "ikonlar": ICON_SECENEKLERI,
        },
    )


@yonetici_gerekli
@require_POST
def kisayol_gorsel_kaydet(request):
    from django.utils.text import slugify

    pk = request.POST.get("pk")
    anahtar = (request.POST.get("anahtar") or "").strip()
    baslik = (request.POST.get("baslik") or "").strip()
    if not baslik:
        messages.error(request, "Başlık gerekli.")
        return redirect("yonetim:kisayol_gorsel_listesi")

    if pk:
        kayit = get_object_or_404(PanelKisayol, pk=pk)
    else:
        if not anahtar:
            anahtar = slugify(baslik)[:40] or "kisayol"
        base = anahtar
        n = 2
        while PanelKisayol.objects.filter(anahtar=anahtar).exists():
            anahtar = f"{base}-{n}"[:40]
            n += 1
        kayit = PanelKisayol(anahtar=anahtar)

    kayit.baslik = baslik
    kayit.alt_baslik = (request.POST.get("alt_baslik") or "").strip()
    kayit.icon = (request.POST.get("icon") or "book").strip()[:20]
    kayit.mark = (request.POST.get("mark") or "").strip()[:8]
    kayit.url_name = (request.POST.get("url_name") or "").strip()
    kayit.url_ozel = (request.POST.get("url_ozel") or "").strip()
    kayit.goster_personel = request.POST.get("goster_personel") == "1"
    kayit.goster_yonetim = request.POST.get("goster_yonetim") == "1"
    kayit.goster_veli = request.POST.get("goster_veli") == "1"
    kayit.goster_ogretmen = request.POST.get("goster_ogretmen") == "1"
    kayit.aktif = request.POST.get("aktif") == "1"
    try:
        kayit.sira = int(request.POST.get("sira") or 0)
    except (TypeError, ValueError):
        kayit.sira = 0
    if request.FILES.get("gorsel"):
        if kayit.gorsel:
            kayit.gorsel.delete(save=False)
        kayit.gorsel = request.FILES["gorsel"]
    kayit.save()
    messages.success(request, f"“{kayit.baslik}” kaydedildi.")
    return redirect("yonetim:kisayol_gorsel_listesi")


@yonetici_gerekli
@require_POST
def kisayol_gorsel_sil(request, pk):
    kayit = get_object_or_404(PanelKisayol, pk=pk)
    ad = kayit.baslik
    if kayit.gorsel:
        kayit.gorsel.delete(save=False)
    kayit.delete()
    messages.success(request, f"“{ad}” silindi.")
    return redirect("yonetim:kisayol_gorsel_listesi")


@yonetici_gerekli
def metrik_listesi(request):
    from takip.dashboard_service import ICON_SECENEKLERI, PANEL_METRIK_KATALOG

    return render(
        request,
        "yonetim/metrik_listesi.html",
        {
            "kayitlar": list(PanelMetrik.objects.order_by("sira", "id")),
            "katalog": PANEL_METRIK_KATALOG,
            "ikonlar": ICON_SECENEKLERI,
            "tonlar": PanelMetrik.Ton.choices,
        },
    )


@yonetici_gerekli
@require_POST
def metrik_kaydet(request):
    from django.utils.text import slugify

    pk = request.POST.get("pk")
    baslik = (request.POST.get("baslik") or "").strip()
    anahtar = (request.POST.get("anahtar") or "").strip()
    if not baslik:
        messages.error(request, "Başlık gerekli.")
        return redirect("yonetim:metrik_listesi")

    if pk:
        kayit = get_object_or_404(PanelMetrik, pk=pk)
    else:
        if not anahtar:
            anahtar = slugify(baslik)[:40] or "metrik"
        # Katalogdan ekleme
        if PanelMetrik.objects.filter(anahtar=anahtar).exists() and not pk:
            kayit = PanelMetrik.objects.get(anahtar=anahtar)
        else:
            base = anahtar
            n = 2
            while PanelMetrik.objects.filter(anahtar=anahtar).exists():
                anahtar = f"{base}-{n}"[:40]
                n += 1
            kayit = PanelMetrik(anahtar=anahtar)

    kayit.baslik = baslik
    kayit.not_metni = (request.POST.get("not_metni") or "").strip()
    kayit.ton = (request.POST.get("ton") or "blue").strip()
    if kayit.ton not in PanelMetrik.Ton.values:
        kayit.ton = PanelMetrik.Ton.BLUE
    kayit.icon = (request.POST.get("icon") or "users").strip()[:20]
    kayit.goster_personel = request.POST.get("goster_personel") == "1"
    kayit.goster_yonetim = request.POST.get("goster_yonetim") == "1"
    kayit.goster_veli = request.POST.get("goster_veli") == "1"
    kayit.goster_ogretmen = request.POST.get("goster_ogretmen") == "1"
    kayit.aktif = request.POST.get("aktif") == "1"
    try:
        kayit.sira = int(request.POST.get("sira") or 0)
    except (TypeError, ValueError):
        kayit.sira = 0
    kayit.save()
    messages.success(request, f"“{kayit.baslik}” kaydedildi.")
    return redirect("yonetim:metrik_listesi")


@yonetici_gerekli
@require_POST
def metrik_sil(request, pk):
    kayit = get_object_or_404(PanelMetrik, pk=pk)
    ad = kayit.baslik
    kayit.delete()
    messages.success(request, f"“{ad}” kaldırıldı.")
    return redirect("yonetim:metrik_listesi")


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
    from takip.program_service import program_tum_donem_ozetleri

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
            kalan = list(
                program.satirlar.order_by("baslangic_saati", "id")
            )
            for index, satir in enumerate(kalan, start=1):
                if satir.sira != index:
                    satir.sira = index
                    satir.save(update_fields=["sira"])

        messages.success(request, f"“{program.ad}” güncellendi.")
        return redirect("yonetim:program_duzenle", pk=program.pk)

    import json

    from takip.models import ProgramFaaliyetTuru

    tur_renk = {
        t.kod: t.renk
        for t in ProgramFaaliyetTuru.objects.filter(aktif=True)
    }

    return render(
        request,
        "yonetim/program_form.html",
        {
            "form": form,
            "formset": formset,
            "program": program,
            "sure_donemler": program_tum_donem_ozetleri(program),
            "tur_renk_json": json.dumps(tur_renk, ensure_ascii=False),
        },
    )


@yonetici_gerekli
def program_tur_listesi(request):
    from takip.models import ProgramFaaliyetTuru

    turler = ProgramFaaliyetTuru.objects.order_by("sira", "ad")
    return render(
        request,
        "yonetim/program_tur_listesi.html",
        {"turler": turler},
    )


@yonetici_gerekli
def program_tur_ekle(request):
    form = ProgramFaaliyetTuruForm(request.POST or None)
    if form.is_valid():
        form.save()
        messages.success(request, "Faaliyet türü eklendi.")
        return redirect("yonetim:program_tur_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Faaliyet Türü Ekle",
            "sayfa_aciklama": "Günlük program satırlarında kullanılacak türü tanımlayın.",
            "geri_url": "yonetim:program_tur_listesi",
        },
    )


@yonetici_gerekli
def program_tur_duzenle(request, pk):
    from takip.models import ProgramFaaliyetTuru

    tur = get_object_or_404(ProgramFaaliyetTuru, pk=pk)
    form = ProgramFaaliyetTuruForm(request.POST or None, instance=tur)
    if form.is_valid():
        form.save()
        messages.success(request, "Faaliyet türü güncellendi.")
        return redirect("yonetim:program_tur_listesi")
    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": f"Tür · {tur.ad}",
            "sayfa_aciklama": "Tür adını, rengini ve sırasını güncelleyin.",
            "geri_url": "yonetim:program_tur_listesi",
        },
    )


@yonetici_gerekli
def program_pdf(request, pk):
    program = get_object_or_404(
        ProgramPlan.objects.prefetch_related("satirlar"),
        pk=pk,
    )
    return _program_pdf_yanit(request, program)


@yonetici_gerekli
def program_excel(request, pk):
    from takip.excel_rapor import excel_http_yanit
    from takip.program_service import program_excel_icerik

    program = get_object_or_404(
        ProgramPlan.objects.prefetch_related("satirlar"),
        pk=pk,
    )
    dosya, icerik = program_excel_icerik(program)
    return excel_http_yanit(icerik, dosya)


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
    """Liste arşivi yok — doğrudan aktif görev paneline git."""
    from .temizlik_service import temizlik_listesi_olustur_veya_al

    liste = temizlik_listesi_olustur_veya_al(request.user)
    return redirect("yonetim:temizlik_gorev_panel", pk=liste.pk)


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
        from takip.excel_rapor import basit_rapor_xlsx, excel_http_yanit
        from django.utils.timezone import localdate

        rows = [
            [
                row["kat"],
                row["mahal"],
                (row["talebe"] or "").upper(),
                row["sorumlular"],
                row["durum"],
                row["tarih"].strftime("%d.%m.%Y") if row.get("tarih") else "",
            ]
            for row in satirlar
        ]
        icerik = basit_rapor_xlsx(
            baslik=f"Temizlik Raporu — {liste}",
            alt_baslik=localdate().strftime("%d.%m.%Y"),
            kolon_basliklari=["Kat", "Mahal", "Ad-Soyad", "Sorumlu Personel", "Durum", "Tarih"],
            satirlar=rows,
            sayfa_adi="Temizlik",
            durum_kolonlari=[4],
            ortala_kolonlari=[0, 5],
            genislikler=[12, 18, 24, 22, 14, 12],
        )
        return excel_http_yanit(icerik, f"temizlik-rapor-{liste.pk}.xlsx")

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
    """Eski öğün listesi → sınıf döngüsü paneli."""
    return redirect("yemekcilik_panel")


@yonetici_gerekli
def yemekci_ekle(request):
    return redirect("yemekcilik_panel")


@yonetici_gerekli
def yemekci_duzenle(request, pk):
    return redirect("yemekcilik_panel")


def _yemekci_pdf_yanit(request, liste):
    return redirect("yemekcilik_panel")


@yonetici_gerekli
def yemekci_pdf(request, pk):
    return redirect("yemekcilik_panel")


@yonetici_gerekli
def ogretmen_degerlendirme_rapor(request):
    from datetime import datetime

    from django.utils.timezone import localdate
    from django.template.loader import render_to_string

    from config.branding import panel_branding_context
    from takip.ogretmen_not_service import (
        admin_degerlendirme_qs,
        ogretmen_haftalik_takip_ozeti,
    )
    from takip.ogretmen_service import _hafta_araligi
    from takip.pdf_utils import (
        html_to_pdf,
        make_pdf_response,
        pdf_engine_status,
        pdf_error_response,
    )

    def _int_or_none(raw):
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    sinif_id = _int_or_none(request.GET.get("sinif"))
    talebe_id = _int_or_none(request.GET.get("talebe"))
    hoca_id = _int_or_none(request.GET.get("hoca"))

    hafta_raw = (request.GET.get("hafta") or "").strip()
    hafta_baslangic = None
    if hafta_raw:
        try:
            gun = datetime.strptime(hafta_raw, "%Y-%m-%d").date()
            _, hafta_baslangic, _ = _hafta_araligi(gun)
        except ValueError:
            hafta_baslangic = None
    if hafta_baslangic is None:
        _, hafta_baslangic, _ = _hafta_araligi(localdate())

    notlar = list(
        admin_degerlendirme_qs(
            sinif_id=sinif_id,
            talebe_id=talebe_id,
            hoca_id=hoca_id,
            hafta_baslangic=hafta_baslangic,
        )[:500]
    )
    takip = ogretmen_haftalik_takip_ozeti(hafta_baslangic)
    _, _, hafta_bitis = _hafta_araligi(hafta_baslangic)

    from takip.ogretmen_odeme_service import aktif_ogretmenler

    siniflar = SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")
    hocalar = list(aktif_ogretmenler())
    talebe_qs = Talebe.objects.filter(aktif=True).order_by("ad_soyad")
    if sinif_id:
        talebe_qs = talebe_qs.filter(sinif_sube_id=sinif_id)
    talebeler = list(talebe_qs[:300])

    filtre_parcalari = [
        f"Hafta: {hafta_baslangic.strftime('%d.%m.%Y')} – {hafta_bitis.strftime('%d.%m.%Y')}"
    ]
    if sinif_id:
        s = next((x for x in siniflar if x.id == sinif_id), None)
        filtre_parcalari.append(f"Sınıf: {s}" if s else "Sınıf filtreli")
    if talebe_id:
        t = next((x for x in talebeler if x.id == talebe_id), None)
        filtre_parcalari.append(f"Talebe: {t.ad_soyad}" if t else "Talebe filtreli")
    if hoca_id:
        h = next((x for x in hocalar if x.id == hoca_id), None)
        filtre_parcalari.append(f"Öğretmen: {h.ad_soyad}" if h else "Öğretmen filtreli")
    filtre_ozet = " · ".join(filtre_parcalari)

    if request.GET.get("format") == "pdf":
        html_metni = render_to_string(
            "ogretmen_degerlendirme_rapor_pdf.html",
            {
                **panel_branding_context(),
                "notlar": notlar,
                "filtre_ozet": filtre_ozet,
                "bugun": localdate(),
            },
            request=request,
        )
        pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
        if not pdf_verisi:
            return pdf_error_response(
                f"Rapor PDF oluşturulamadı. (Motor: {pdf_engine_status()})"
            )
        return make_pdf_response(pdf_verisi, "ogretmen-degerlendirme-raporu.pdf")

    return render(
        request,
        "yonetim/ogretmen_degerlendirme_rapor.html",
        {
            "notlar": notlar,
            "siniflar": siniflar,
            "talebeler": talebeler,
            "hocalar": hocalar,
            "secili_sinif_id": sinif_id,
            "secili_talebe_id": talebe_id,
            "secili_hoca_id": hoca_id,
            "secili_hafta": hafta_baslangic.isoformat(),
            "hafta_baslangic": hafta_baslangic,
            "hafta_bitis": hafta_bitis,
            "takip": takip,
            "filtre_ozet": filtre_ozet,
        },
    )


@yonetici_gerekli
def ogretmen_degerlendirme_karne_pdf(request, talebe_id: int):
    from datetime import date

    from django.utils.timezone import localdate

    from config.branding import panel_branding_context
    from takip.ogretmen_not_service import (
        talebe_haftalik_karne_verisi,
        talebe_karne_verisi,
    )
    from takip.ogretmen_service import aktif_hafta_baslangic
    from takip.pdf_utils import html_to_pdf, make_pdf_response, pdf_engine_status, pdf_error_response
    from django.template.loader import render_to_string

    talebe = get_object_or_404(Talebe, pk=talebe_id)
    if request.GET.get("tum") == "1":
        ctx = talebe_karne_verisi(talebe, sadece_veliye_acik=False)
        sablon = "ogretmen_degerlendirme_karne_pdf.html"
        dosya_ek = "degerlendirme-karnesi"
    else:
        raw = (request.GET.get("hafta") or "").strip()
        try:
            hafta = date.fromisoformat(raw) if raw else aktif_hafta_baslangic()
        except ValueError:
            hafta = aktif_hafta_baslangic()
        ctx = talebe_haftalik_karne_verisi(
            talebe, hafta, sadece_veliye_acik=False
        )
        sablon = "ogretmen_haftalik_egitim_karne_pdf.html"
        dosya_ek = "haftalik-egitim-karnesi"

    ctx.update(panel_branding_context())
    ctx["bugun"] = localdate()
    html_metni = render_to_string(sablon, ctx, request=request)
    pdf_verisi = html_to_pdf(html_metni, base_url=request.build_absolute_uri("/"))
    if not pdf_verisi:
        return pdf_error_response(
            f"Karne PDF oluşturulamadı. (Motor: {pdf_engine_status()})"
        )
    ad = talebe.ad_soyad.replace(" ", "-")
    return make_pdf_response(pdf_verisi, f"{ad}-{dosya_ek}.pdf")
