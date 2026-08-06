from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import EtutHocasi, SinifSube, Talebe, Zimmet
from .yonetim_forms import (
    EtutHocasiForm,
    SinifSubeForm,
    TalebeForm,
)


def yonetici_mi(user):
    return user.is_authenticated and user.is_staff


def yonetici_gerekli(view_func):
    return login_required(
        user_passes_test(yonetici_mi)(view_func)
    )


@yonetici_gerekli
def dashboard(request):
    son_talebeler = (
        Talebe.objects
        .select_related("sinif_sube", "etut_hocasi")
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
        "toplam_personel": EtutHocasi.objects.count(),
        "aktif_personel": EtutHocasi.objects.filter(aktif=True).count(),
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
        EtutHocasi.objects
        .select_related("user")
        .prefetch_related("sorumlu_sinif_subeler")
        .annotate(talebe_sayisi=Count("talebeler"))
        .order_by("ad_soyad")
    )

    return render(
        request,
        "yonetim/personel_listesi.html",
        {"personeller": personeller},
    )


@yonetici_gerekli
def personel_ekle(request):
    form = EtutHocasiForm(request.POST or None)

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
            "sayfa_basligi": "Etüt Hocası Ekle",
            "sayfa_aciklama": (
                "Giriş bilgilerini ve sorumlu olduğu sınıfları belirleyin."
            ),
            "geri_url": "yonetim:personel_listesi",
        },
    )


@yonetici_gerekli
def personel_duzenle(request, pk):
    personel = get_object_or_404(EtutHocasi, pk=pk)
    form = EtutHocasiForm(
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
            "sayfa_basligi": "Etüt Hocası Düzenle",
            "sayfa_aciklama": (
                "Personel bilgilerini ve sınıf yetkilerini güncelleyin."
            ),
            "geri_url": "yonetim:personel_listesi",
        },
    )


@yonetici_gerekli
def talebe_listesi(request):
    talebeler = (
        Talebe.objects
        .select_related("sinif_sube", "etut_hocasi")
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
            | Q(sinif_sube__sinif__icontains=arama)
            | Q(sinif_sube__sube__icontains=arama)
        )

    aktif_zimmetler = {z.talebe_id: z for z in Zimmet.objects.filter(talebe__in=talebeler, durum="okunuyor").select_related("kitap").order_by("talebe_id", "-id")}
    for talebe in talebeler:
        talebe.aktif_zimmet = aktif_zimmetler.get(talebe.id)

    return render(
        request,
        "yonetim/talebe_listesi.html",
        {
            "talebeler": talebeler,
            "arama": arama,
            "sinif_id": sinif_id,
        },
    )


@yonetici_gerekli
def talebe_ekle(request):
    form = TalebeForm(request.POST or None)

    if form.is_valid():
        talebe = form.save()
        messages.success(
            request,
            f"{talebe.ad_soyad} başarıyla eklendi.",
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
