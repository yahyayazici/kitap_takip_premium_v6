"""Yönetim — hızlı kayıt formları (personel, talebe+veli, öğretmen)."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.db import transaction

from takip.models import (
    DiniDersSeviyesi,
    EtutHocasi,
    PersonelProfili,
    SinifSube,
    Talebe,
    VeliKisi,
)
from takip.ogretmen_odeme_models import OgretmenOdemeProfili
from takip.panel_permissions import ROL_ETUT_MESUL, ROL_SINIF_MESUL
from takip.talebe_foto_util import dogrula_biyometrik_foto
from takip.tc_util import pasif_talebe_tc_temizle, tc_dogrula, talebe_tc_cakisma_var_mi
from takip.veli_hesap_util import veli_panel_ensure
from takip.wave0_models import Brans, VeliHesap
from takip.personel_giris_service import (
    OgretmenGirisKaydi,
    PersonelGirisKaydi,
    ogretmen_olustur,
    personel_giris_pdf_olustur,
    personel_giris_zip_olustur,
    sifre_uret,
    kullanici_adi_uret,
    rol_secenekleri,
    toplu_ogretmen_olustur,
)
from takip.yonetim_forms import PersonelProfiliForm


def _cs(attrs=None):
    base = {"class": "cs-input"}
    if attrs:
        base.update(attrs)
    return base


class HizliPersonelForm(PersonelProfiliForm):
    """İdari personel — kullanıcı adı ve şifre otomatik."""

    SINIF_GEREKLI_ROLLER = {ROL_SINIF_MESUL, ROL_ETUT_MESUL}

    dini_ders_seviyeleri = forms.ModelMultipleChoiceField(
        label="Sorumlu dini ders seviyeleri",
        queryset=DiniDersSeviyesi.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-chip-grid"}),
        help_text="Etüt mesulü için en az bir seviye seçin.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("kullanici_adi", None)
        self.fields.pop("sifre", None)
        rol_alan = self.fields["ana_rol"]
        rol_alan.widget.attrs.update({"class": "cs-input", "data-yk-rol-sec": "1"})
        self.fields["ad_soyad"].widget.attrs["placeholder"] = "Ad ve soyad"
        self.fields["aktif"].initial = True
        self.fields["dini_ders_seviyeleri"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        if self.instance.pk and self.instance.etut_hocasi_id:
            self.fields["dini_ders_seviyeleri"].initial = (
                self.instance.etut_hocasi.sorumlu_dini_ders_seviyeleri.all()
            )

    def clean(self):
        cleaned = super().clean()
        if not self.instance.pk:
            ad = (cleaned.get("ad_soyad") or "").strip()
            if ad:
                cleaned["kullanici_adi"] = kullanici_adi_uret(ad)
                cleaned["sifre"] = sifre_uret()

        if cleaned.get("ana_rol") == ROL_ETUT_MESUL and not cleaned.get(
            "dini_ders_seviyeleri"
        ):
            self.add_error(
                "dini_ders_seviyeleri",
                "Etüt mesulü için en az bir dini ders seviyesi seçin.",
            )
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        personel = super().save(commit=commit)
        if personel.ana_rol == ROL_ETUT_MESUL and personel.etut_hocasi_id:
            seviyeler = self.cleaned_data.get("dini_ders_seviyeleri") or []
            hoca = personel.etut_hocasi
            for seviye in seviyeler:
                seviye.hocalar.add(hoca)
        return personel


class TopluPersonelForm(forms.Form):
    isim_listesi = forms.CharField(
        label="Personel isimleri",
        widget=forms.Textarea(
            attrs=_cs(
                {
                    "rows": 10,
                    "placeholder": "Her satıra bir ad soyad yazın\nÖrn:\nAhmet Yılmaz\nAyşe Demir",
                }
            )
        ),
        help_text="Kullanıcı adı ve şifre her personel için otomatik oluşturulur.",
    )
    ana_rol = forms.ChoiceField(
        label="Rol",
        choices=[],
        widget=forms.Select(attrs={"class": "cs-input", "data-yk-rol-sec": "1"}),
    )
    sorumlu_sinif_subeler = forms.ModelMultipleChoiceField(
        label="Sorumlu olduğu sınıf ve şubeler",
        queryset=SinifSube.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-chip-grid"}),
    )
    dini_ders_seviyeleri = forms.ModelMultipleChoiceField(
        label="Sorumlu dini ders seviyeleri",
        queryset=DiniDersSeviyesi.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-chip-grid"}),
    )
    aktif = forms.BooleanField(
        label="Aktif hesap",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ana_rol"].choices = rol_secenekleri()
        self.fields["sorumlu_sinif_subeler"].queryset = SinifSube.objects.filter(
            aktif=True
        ).order_by("sinif", "sube")
        self.fields["dini_ders_seviyeleri"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")

    def clean(self):
        cleaned = super().clean()
        rol = cleaned.get("ana_rol")
        if rol == ROL_SINIF_MESUL and not cleaned.get("sorumlu_sinif_subeler"):
            self.add_error(
                "sorumlu_sinif_subeler",
                "Sınıf mesulü için en az bir sınıf seçin.",
            )
        if rol == ROL_ETUT_MESUL:
            if not cleaned.get("sorumlu_sinif_subeler"):
                self.add_error(
                    "sorumlu_sinif_subeler",
                    "Etüt mesulü için en az bir sınıf seçin.",
                )
            if not cleaned.get("dini_ders_seviyeleri"):
                self.add_error(
                    "dini_ders_seviyeleri",
                    "Etüt mesulü için en az bir dini ders seviyesi seçin.",
                )
        return cleaned

    def clean_isim_listesi(self):
        ham = self.cleaned_data.get("isim_listesi") or ""
        isimler = [satir.strip() for satir in ham.splitlines() if satir.strip()]
        if not isimler:
            raise forms.ValidationError("En az bir personel adı girin.")
        return isimler


class HizliTalebeForm(forms.ModelForm):
    """İlk kayıt: ad soyad, TC, sınıf, etüt hocası, dini ders hocası."""

    class Meta:
        model = Talebe
        fields = [
            "ad_soyad",
            "tc_kimlik",
            "sinif_sube",
            "etut_hocasi",
            "dini_ders_hocasi",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs=_cs({"placeholder": "Talebe adı soyadı"})
            ),
            "tc_kimlik": forms.TextInput(
                attrs=_cs(
                    {
                        "placeholder": "11 haneli TC kimlik no",
                        "inputmode": "numeric",
                        "maxlength": "11",
                        "autocomplete": "off",
                    }
                )
            ),
            "sinif_sube": forms.Select(
                attrs={"class": "cs-input", "data-yk-sinif-sec": "1"}
            ),
            "etut_hocasi": forms.Select(
                attrs={"class": "cs-input", "data-yk-etut-sec": "1"}
            ),
            "dini_ders_hocasi": forms.Select(
                attrs={"class": "cs-input", "data-yk-dini-hoca-sec": "1"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoca_qs = EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")
        self.fields["sinif_sube"].queryset = SinifSube.objects.filter(aktif=True).order_by(
            "sinif", "sube"
        )
        self.fields["sinif_sube"].empty_label = "Sınıf seçin"
        self.fields["sinif_sube"].required = True
        self.fields["sinif_sube"].help_text = (
            "Sınıf seçilince o sınıfa zimmetli etüt hocası otomatik gelir."
        )
        self.fields["etut_hocasi"].queryset = hoca_qs
        self.fields["etut_hocasi"].empty_label = "Etüt hocası seçin"
        self.fields["etut_hocasi"].required = True
        self.fields["dini_ders_hocasi"].queryset = hoca_qs
        self.fields["dini_ders_hocasi"].empty_label = "Dini ders hocası seçin"
        self.fields["dini_ders_hocasi"].required = True
        self.fields["dini_ders_hocasi"].help_text = (
            "Etüt hocasından farklı olabilir; seçilen hocanın dini ders seviye "
            "grubuna otomatik yazılır."
        )
        self.fields["tc_kimlik"].required = True
        self.fields["tc_kimlik"].help_text = (
            "Veli paneli için: kullanıcı adı TC, şifre TC'nin son 4 hanesi "
            "(veli bilgisi sonra doldurulur)."
        )
        self.fields["ad_soyad"].required = True

    def clean(self):
        cleaned = super().clean()
        sinif_sube = cleaned.get("sinif_sube")
        etut = cleaned.get("etut_hocasi")
        dini_hoca = cleaned.get("dini_ders_hocasi")

        if sinif_sube and not etut:
            etut = (
                sinif_sube.etut_hocalari.filter(aktif=True)
                .order_by("ad_soyad")
                .first()
            )
            if etut:
                cleaned["etut_hocasi"] = etut
            else:
                self.add_error(
                    "sinif_sube",
                    f"«{sinif_sube}» için zimmetli etüt hocası tanımlı değil. "
                    "Önce personel/etüt mesulüne sınıf zimmeti verin.",
                )

        if sinif_sube and etut:
            if not etut.sorumlu_sinif_subeler.filter(pk=sinif_sube.pk).exists():
                self.add_error(
                    "etut_hocasi",
                    "Seçilen etüt hocası bu sınıftan sorumlu değil.",
                )

        if etut and not dini_hoca:
            cleaned["dini_ders_hocasi"] = etut
            dini_hoca = etut

        if dini_hoca and not cleaned.get("dini_ders_seviyesi"):
            seviye = (
                dini_hoca.sorumlu_dini_ders_seviyeleri.filter(aktif=True)
                .order_by("sira", "ad")
                .first()
            )
            if seviye:
                cleaned["dini_ders_seviyesi"] = seviye

        return cleaned

    def clean_tc_kimlik(self):
        tc = tc_dogrula(self.cleaned_data.get("tc_kimlik"))
        if talebe_tc_cakisma_var_mi(tc, haric_pk=self.instance.pk):
            raise forms.ValidationError(
                "Bu TC kimlik no aktif bir talebede kayıtlı."
            )
        return tc

    @transaction.atomic
    def save_with_veli(self) -> tuple[Talebe, VeliHesap | None]:
        tc = self.cleaned_data.get("tc_kimlik")
        if tc:
            pasif_talebe_tc_temizle(tc)
        talebe = super().save(commit=False)
        sinif = self.cleaned_data.get("sinif_sube")
        if sinif:
            talebe.sinif_sube = sinif
        seviye = self.cleaned_data.get("dini_ders_seviyesi")
        if seviye:
            talebe.dini_ders_seviyesi = seviye
        if not talebe.dini_ders_hocasi_id and talebe.etut_hocasi_id:
            talebe.dini_ders_hocasi = talebe.etut_hocasi
        talebe.save()
        return talebe, None


class HizliOgretmenForm(forms.Form):
    ad_soyad = forms.CharField(
        label="Ad soyad",
        max_length=120,
        widget=forms.TextInput(attrs=_cs({"placeholder": "Öğretmen adı soyadı"})),
    )
    brans = forms.ModelChoiceField(
        label="Branş",
        queryset=Brans.objects.none(),
        required=True,
        empty_label="Branş seçin",
        widget=forms.Select(attrs={"class": "cs-input"}),
        help_text="Beş ana dersten birini seçin (Türkçe, Matematik, Fen, Sosyal, Din).",
    )
    saatlik_ucret = forms.DecimalField(
        label="Saatlik ücret (₺)",
        required=False,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "cs-input", "step": "0.01", "min": "0"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brans"].queryset = Brans.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )

    def clean(self):
        cleaned = super().clean()
        ad = (cleaned.get("ad_soyad") or "").strip()
        if ad:
            cleaned["kullanici_adi"] = kullanici_adi_uret(ad)
            cleaned["sifre"] = sifre_uret()
        return cleaned

    @transaction.atomic
    def save(self) -> OgretmenGirisKaydi:
        return ogretmen_olustur(
            ad_soyad=self.cleaned_data["ad_soyad"],
            brans=self.cleaned_data.get("brans"),
            saatlik_ucret=self.cleaned_data.get("saatlik_ucret") or Decimal("0"),
        )


class TopluOgretmenForm(forms.Form):
    isim_listesi = forms.CharField(
        label="Öğretmen isimleri",
        widget=forms.Textarea(
            attrs=_cs(
                {
                    "rows": 10,
                    "placeholder": "Her satıra bir ad soyad yazın\nÖrn:\nKemal Demirci\nRecep Bebek",
                }
            )
        ),
        help_text="Kullanıcı adı ve şifre her öğretmen için otomatik oluşturulur.",
    )
    brans = forms.ModelChoiceField(
        label="Branş",
        queryset=Brans.objects.none(),
        required=True,
        empty_label="Branş seçin",
        widget=forms.Select(attrs={"class": "cs-input"}),
    )
    saatlik_ucret = forms.DecimalField(
        label="Saatlik ücret (₺)",
        required=False,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        widget=forms.NumberInput(attrs={"class": "cs-input", "step": "0.01", "min": "0"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brans"].queryset = Brans.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )

    def clean_isim_listesi(self):
        ham = self.cleaned_data.get("isim_listesi") or ""
        isimler = [satir.strip() for satir in ham.splitlines() if satir.strip()]
        if not isimler:
            raise forms.ValidationError("En az bir öğretmen adı girin.")
        return isimler
