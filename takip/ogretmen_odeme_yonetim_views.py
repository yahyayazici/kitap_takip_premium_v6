"""Yönetim — öğretmen ödeme profili + sınıf zimmeti."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from takip.hizli_kayit_service import ogretmen_pasif_et
from takip.models import EtutHocasi, SinifSube
from takip.ogretmen_odeme_models import OgretmenOdemeProfili
from takip.ogretmen_odeme_service import aktif_ogretmenler, ogretmen_profili
from takip.ogretmen_service import (
    OGRETMEN_EKSTRA_ROL_SLUGLERI,
    ogretmen_ekstra_rol_slugleri,
)
from takip.permissions.service import can, clear_permission_cache
from takip.ogretmen_bilgilendirme_service import ogretmen_bilgilendirme_pdf_olustur
from takip.personel_giris_service import (
    ogretmen_giris_kaydi_yenile,
    personel_giris_pdf_olustur,
)
from takip.pdf_utils import make_pdf_response, pdf_error_response
from takip.wave0_models import Brans, KullaniciRol, Rol
from takip.yonetim_views import yonetici_gerekli


class OgretmenOdemeProfilForm(forms.ModelForm):
    sorumlu_sinif_subeler = forms.ModelMultipleChoiceField(
        label="Gireceği sınıflar",
        queryset=SinifSube.objects.none(),
        required=True,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-chip-grid"}),
        help_text="Öğretmen panelinde yalnızca bu sınıflar görünür.",
    )

    class Meta:
        model = OgretmenOdemeProfili
        fields = ["brans", "saatlik_ucret", "aktif"]
        widgets = {
            "brans": forms.Select(attrs={"class": "cs-input"}),
            "saatlik_ucret": forms.NumberInput(
                attrs={"class": "cs-input", "step": "0.01", "min": "0"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }

    def __init__(self, *args, hoca: EtutHocasi | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hoca = hoca or getattr(self.instance, "etut_hocasi", None)
        self.fields["sorumlu_sinif_subeler"].queryset = SinifSube.objects.filter(
            aktif=True
        ).order_by("sinif", "sube")
        if self.hoca and self.hoca.pk:
            self.fields["sorumlu_sinif_subeler"].initial = (
                self.hoca.sorumlu_sinif_subeler.all()
            )

    def clean_sorumlu_sinif_subeler(self):
        siniflar = self.cleaned_data.get("sorumlu_sinif_subeler")
        if not siniflar:
            raise forms.ValidationError("En az bir sınıf seçin.")
        return siniflar

    def save(self, commit=True):
        profil = super().save(commit=commit)
        hoca = self.hoca or profil.etut_hocasi
        if hoca is not None:
            hoca.sorumlu_sinif_subeler.set(
                self.cleaned_data.get("sorumlu_sinif_subeler") or []
            )
        return profil


@yonetici_gerekli
def ogretmen_odeme_profil_listesi(request):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hocalar = list(
        aktif_ogretmenler().prefetch_related("sorumlu_sinif_subeler")
    )
    for hoca in hocalar:
        try:
            hoca.odeme_profili_kayit = hoca.odeme_profili
        except OgretmenOdemeProfili.DoesNotExist:
            hoca.odeme_profili_kayit = None
        hoca.sinif_etiketleri = [
            f"{s.sinif}-{s.sube}" for s in hoca.sorumlu_sinif_subeler.all()
        ]
        if hoca.user_id:
            slugler = ogretmen_ekstra_rol_slugleri(hoca.user)
            hoca.ekstra_rol_etiketleri = list(
                Rol.objects.filter(slug__in=slugler, aktif=True)
                .order_by("sira", "ad")
                .values_list("ad", flat=True)
            )
        else:
            hoca.ekstra_rol_etiketleri = []

    return render(
        request,
        "yonetim/ogretmen_odeme_profil_listesi.html",
        {"hocalar": hocalar},
    )


@yonetici_gerekli
def ogretmen_odeme_profil_duzenle(request, pk: int):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hoca = get_object_or_404(
        EtutHocasi.objects.prefetch_related("sorumlu_sinif_subeler"),
        pk=pk,
        aktif=True,
        personel_kaydi__isnull=True,
    )
    profil = ogretmen_profili(hoca)
    form = OgretmenOdemeProfilForm(
        request.POST or None,
        instance=profil,
        hoca=hoca,
    )

    if form.is_valid():
        form.save()
        messages.success(
            request,
            f"{hoca.ad_soyad} branş, ücret ve sınıf zimmeti güncellendi.",
        )
        return redirect(
            reverse("yonetim:ogretmen_odeme_profil_listesi") + f"#hoca-{hoca.pk}"
        )

    return render(
        request,
        "yonetim/ogretmen_odeme_profil_form.html",
        {
            "form": form,
            "hoca": hoca,
            "branslar": Brans.objects.filter(aktif=True).order_by("sira", "ad"),
        },
    )


@yonetici_gerekli
def ogretmen_rol_ver(request, pk: int):
    """Branş öğretmene ekstra RBAC rol ata (PersonelProfili açılmaz)."""
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hoca = get_object_or_404(
        EtutHocasi.objects.select_related("user"),
        pk=pk,
        aktif=True,
        personel_kaydi__isnull=True,
    )
    if not hoca.user_id:
        messages.error(request, "Bu öğretmenin kullanıcı hesabı yok; önce giriş PDF oluşturun.")
        return redirect("yonetim:ogretmen_odeme_profil_listesi")

    atanabilir = list(
        Rol.objects.filter(slug__in=OGRETMEN_EKSTRA_ROL_SLUGLERI, aktif=True).order_by(
            "sira", "ad"
        )
    )
    secili = set(ogretmen_ekstra_rol_slugleri(hoca.user))

    if request.method == "POST":
        istenen = set(request.POST.getlist("roller")) & set(OGRETMEN_EKSTRA_ROL_SLUGLERI)
        mevcut = {
            kr.rol.slug: kr
            for kr in KullaniciRol.objects.filter(
                user=hoca.user, rol__slug__in=OGRETMEN_EKSTRA_ROL_SLUGLERI
            ).select_related("rol")
        }

        for slug in istenen - set(mevcut):
            rol = next((r for r in atanabilir if r.slug == slug), None)
            if rol is None:
                rol = Rol.objects.filter(slug=slug, aktif=True).first()
            if rol is None:
                continue
            KullaniciRol.objects.get_or_create(
                user=hoca.user,
                rol=rol,
                defaults={"birincil": False},
            )

        for slug, kayit in mevcut.items():
            if slug not in istenen:
                kayit.delete()

        clear_permission_cache()
        if istenen:
            adlar = ", ".join(
                r.ad for r in atanabilir if r.slug in istenen
            ) or ", ".join(sorted(istenen))
            messages.success(
                request,
                f"{hoca.ad_soyad} için ekstra roller kaydedildi: {adlar}.",
            )
        else:
            messages.success(
                request,
                f"{hoca.ad_soyad} için ekstra rol kaldırıldı. Girişte doğrudan Not Girişi açılır.",
            )
        return redirect(
            reverse("yonetim:ogretmen_odeme_profil_listesi") + f"#hoca-{hoca.pk}"
        )

    return render(
        request,
        "yonetim/ogretmen_rol_ver.html",
        {
            "hoca": hoca,
            "atanabilir_roller": atanabilir,
            "secili_slugler": secili,
        },
    )


@yonetici_gerekli
@require_POST
def ogretmen_odeme_profil_sil(request, pk: int):
    if not can(request.user, "ogretmen_odeme", "view_financial"):
        return redirect("yonetim:dashboard")

    hoca = get_object_or_404(
        EtutHocasi, pk=pk, aktif=True, personel_kaydi__isnull=True
    )
    ogretmen_pasif_et(hoca)
    messages.success(request, f"{hoca.ad_soyad} pasif edildi ve listeden kaldırıldı.")
    return redirect("yonetim:ogretmen_odeme_profil_listesi")


@yonetici_gerekli
@require_POST
def ogretmen_giris_pdf_tek(request, pk: int):
    """Öğretmen için yeni şifre üretip giriş bilgileri PDF indir."""
    hoca = get_object_or_404(
        EtutHocasi.objects.select_related("user"),
        pk=pk,
        aktif=True,
        personel_kaydi__isnull=True,
    )
    kayit = ogretmen_giris_kaydi_yenile(hoca)
    if not kayit:
        messages.error(request, "Bu öğretmen için giriş bilgisi oluşturulamadı.")
        return redirect("yonetim:ogretmen_odeme_profil_listesi")

    pdf = personel_giris_pdf_olustur(kayit, request=request)
    if not pdf:
        return pdf_error_response("Giriş PDF'i oluşturulamadı.")

    dosya = hoca.ad_soyad.lower().replace(" ", "-")
    return make_pdf_response(pdf, f"giris-{dosya}.pdf")


@yonetici_gerekli
@require_GET
def etut_hocasi_rehber_pdf(request):
    """Etüt hocaları için ortak kullanım rehberi PDF."""
    pdf = ogretmen_bilgilendirme_pdf_olustur(request)
    if not pdf:
        return pdf_error_response("Etüt hocası rehber PDF'i oluşturulamadı.")
    return make_pdf_response(pdf, "cinili-saray-etut-hocasi-rehberi.pdf")
