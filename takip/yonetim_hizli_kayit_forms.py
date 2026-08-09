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
from takip.wave0_models import Brans, VeliHesap, VeliTalebeBaglantisi
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
    veli_ad_soyad = forms.CharField(
        label="Veli ad soyad",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs=_cs({"placeholder": "Veli adı soyadı"})),
    )
    veli_telefon = forms.CharField(
        label="Veli telefon",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs=_cs({"placeholder": "05xx xxx xx xx"})),
    )
    veli_yakinlik = forms.ChoiceField(
        label="Yakınlık",
        choices=VeliKisi.Yakinlik.choices,
        initial=VeliKisi.Yakinlik.VELI,
        required=False,
        widget=forms.Select(attrs={"class": "cs-input"}),
    )
    veli_hesap_olustur = forms.BooleanField(
        label="Veli panel hesabı oluştur",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
    )
    veli_kullanici_adi = forms.CharField(
        label="Veli kullanıcı adı",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs=_cs({"placeholder": "Boş bırakılırsa otomatik önerilir", "autocomplete": "off"})
        ),
    )
    veli_sifre = forms.CharField(
        label="Veli şifre",
        required=False,
        widget=forms.PasswordInput(
            attrs=_cs({"placeholder": "Veli paneli için", "autocomplete": "new-password"}),
            render_value=False,
        ),
    )

    class Meta:
        model = Talebe
        fields = [
            "ad_soyad",
            "biyometrik_foto",
            "sinif_sube",
            "etut_hocasi",
            "telefon",
            "dogum_tarihi",
            "dini_ders_seviyesi",
            "dini_ders_hocasi",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs=_cs({"placeholder": "Talebe adı soyadı"})
            ),
            "biyometrik_foto": forms.ClearableFileInput(
                attrs=_cs({"accept": "image/jpeg,image/png,image/webp"})
            ),
            "sinif_sube": forms.Select(
                attrs={"class": "cs-input", "data-yk-sinif-sec": "1"}
            ),
            "etut_hocasi": forms.Select(
                attrs={"class": "cs-input", "data-yk-etut-sec": "1"}
            ),
            "telefon": forms.TextInput(
                attrs=_cs({"placeholder": "Opsiyonel"})
            ),
            "dogum_tarihi": forms.DateInput(
                attrs=_cs({"type": "date"}),
                format="%Y-%m-%d",
            ),
            "dini_ders_seviyesi": forms.Select(
                attrs={"class": "cs-input", "data-yk-dini-seviye-sec": "1"}
            ),
            "dini_ders_hocasi": forms.Select(
                attrs={"class": "cs-input", "data-yk-dini-hoca-sec": "1"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sinif_sube"].queryset = SinifSube.objects.filter(
            aktif=True
        ).order_by("sinif", "sube")
        self.fields["sinif_sube"].empty_label = "Sınıf seçin"
        hoca_qs = EtutHocasi.objects.filter(aktif=True).order_by("ad_soyad")
        self.fields["etut_hocasi"].queryset = hoca_qs
        self.fields["etut_hocasi"].empty_label = "Etüt hocası seçin"
        self.fields["etut_hocasi"].help_text = (
            "Sınıf seçince zimmetli etüt hocası otomatik gelir."
        )
        self.fields["dini_ders_seviyesi"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["dini_ders_seviyesi"].required = False
        self.fields["dini_ders_seviyesi"].empty_label = "Seviye seçin"
        self.fields["dini_ders_hocasi"].queryset = hoca_qs
        self.fields["dini_ders_hocasi"].required = False
        self.fields["dini_ders_hocasi"].empty_label = "Dini ders hocası seçin"
        self.fields["dini_ders_hocasi"].help_text = (
            "Önce dini ders seviyesini seçin; o seviyedeki hocalar listelenir."
        )
        self.fields["telefon"].required = False
        self.fields["dogum_tarihi"].required = False

    def clean(self):
        cleaned = super().clean()
        sinif_sube = cleaned.get("sinif_sube")
        etut = cleaned.get("etut_hocasi")
        seviye = cleaned.get("dini_ders_seviyesi")
        dini_hoca = cleaned.get("dini_ders_hocasi")

        if sinif_sube and etut:
            if not etut.sorumlu_sinif_subeler.filter(pk=sinif_sube.pk).exists():
                self.add_error(
                    "etut_hocasi",
                    "Seçilen etüt hocası bu sınıftan sorumlu değil.",
                )

        if seviye and not dini_hoca:
            self.add_error(
                "dini_ders_hocasi",
                "Dini ders seviyesi seçildiğinde dini ders hocası zorunludur.",
            )
        elif seviye and dini_hoca:
            if not seviye.hocalar.filter(pk=dini_hoca.pk).exists():
                self.add_error(
                    "dini_ders_hocasi",
                    f"Seçilen hoca «{seviye.ad}» seviyesinden sorumlu değil.",
                )
        elif not seviye and dini_hoca:
            self.add_error(
                "dini_ders_seviyesi",
                "Dini ders hocası seçmeden önce seviye seçin.",
            )

        if etut and not dini_hoca and not seviye:
            cleaned["dini_ders_hocasi"] = etut

        veli_ad = (cleaned.get("veli_ad_soyad") or "").strip()
        hesap = cleaned.get("veli_hesap_olustur")
        veli_user = (cleaned.get("veli_kullanici_adi") or "").strip().lower()
        veli_sifre = cleaned.get("veli_sifre") or ""

        if hesap:
            if not veli_ad:
                self.add_error(
                    "veli_ad_soyad",
                    "Veli panel hesabı için veli adı girin.",
                )
            if not veli_sifre or len(veli_sifre) < 8:
                self.add_error(
                    "veli_sifre",
                    "Veli hesabı için en az 8 karakterlik şifre girin.",
                )
            if not veli_user:
                ad = cleaned.get("ad_soyad", "")
                oneri = _veli_kullanici_oneri(ad, veli_ad)
                cleaned["veli_kullanici_adi"] = oneri
                veli_user = oneri
            if User.objects.filter(username__iexact=veli_user).exists():
                self.add_error(
                    "veli_kullanici_adi",
                    "Bu veli kullanıcı adı zaten kullanılıyor.",
                )
        elif veli_ad and veli_user:
            if User.objects.filter(username__iexact=veli_user).exists():
                self.add_error(
                    "veli_kullanici_adi",
                    "Bu kullanıcı adı kullanılıyor.",
                )

        return cleaned

    def clean_biyometrik_foto(self):
        foto = self.cleaned_data.get("biyometrik_foto")
        dogrula_biyometrik_foto(foto)
        return foto

    @transaction.atomic
    def save_with_veli(self) -> tuple[Talebe, VeliHesap | None]:
        talebe = self.save()
        veli_ad = (self.cleaned_data.get("veli_ad_soyad") or "").strip()
        veli_hesap = None

        if veli_ad:
            VeliKisi.objects.create(
                talebe=talebe,
                ad_soyad=veli_ad,
                telefon=self.cleaned_data.get("veli_telefon", ""),
                yakinlik=self.cleaned_data.get("veli_yakinlik") or VeliKisi.Yakinlik.VELI,
                birincil=True,
            )

        if self.cleaned_data.get("veli_hesap_olustur") and veli_ad:
            username = self.cleaned_data["veli_kullanici_adi"].strip().lower()
            user = User.objects.create_user(
                username=username,
                password=self.cleaned_data["veli_sifre"],
                first_name=veli_ad,
            )
            veli_hesap = VeliHesap.objects.create(
                user=user,
                ad_soyad=veli_ad,
                telefon=self.cleaned_data.get("veli_telefon", ""),
                aktif=True,
            )
            VeliTalebeBaglantisi.objects.create(
                veli=veli_hesap,
                talebe=talebe,
                yakinlik=self.cleaned_data.get("veli_yakinlik") or "veli",
            )

        return talebe, veli_hesap


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


def _veli_kullanici_oneri(talebe_ad: str, veli_ad: str) -> str:
    kaynak = veli_ad or talebe_ad
    parcalar = [
        p.lower()
        for p in kaynak.replace("'", "").split()
        if p.strip()
    ]
    taban = ".".join(parcalar[:2]) if parcalar else "veli"
    aday = taban
    sayac = 1
    while User.objects.filter(username__iexact=aday).exists():
        sayac += 1
        aday = f"{taban}{sayac}"
    return aday[:150]
