from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.forms import inlineformset_factory

from .models import (
    Brans,
    CumaDurumMetni,
    Ders,
    DiniDersSeviyesi,
    Duyuru,
    EtutHocasi,
    HaftalikSohbetMevzuu,
    ImamMuezzinAtama,
    ImamMuezzinListesi,
    PersonelProfili,
    ProgramFaaliyetTuru,
    ProgramPlan,
    ProgramSatir,
    SinifSube,
    Talebe,
    TemizlikAlani,
    TemizlikAtama,
    TemizlikListesi,
    YemekciAtama,
    YemekciListesi,
    YemekOgun,
)
from .imam_muezzin_service import parse_haric_tarih_metni
from .panel_permissions import PERSONEL_ROLLER, ROL_ETUT_MESUL, ROL_SINIF_MESUL
from .talebe_foto_util import dogrula_biyometrik_foto
from .tc_util import pasif_talebe_tc_temizle, tc_dogrula, talebe_tc_cakisma_var_mi


class SinifSubeForm(forms.ModelForm):
    class Meta:
        model = SinifSube
        fields = ["sinif", "sube", "aktif"]
        widgets = {
            "sinif": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Örn. 3, 4, 5, Hazırlık",
                }
            ),
            "sube": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Örn. A, B, C",
                }
            ),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }


class BransForm(forms.ModelForm):
    class Meta:
        model = Brans
        fields = ["ad", "sira", "aktif"]
        widgets = {
            "ad": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Örn. Matematik, Türkçe"}
            ),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }


class DersForm(forms.ModelForm):
    class Meta:
        model = Ders
        fields = ["ad", "brans", "sira", "aktif"]
        widgets = {
            "ad": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Örn. Matematik"}
            ),
            "brans": forms.Select(attrs={"class": "cs-input"}),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["brans"].queryset = Brans.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )
        self.fields["brans"].required = False
        self.fields["brans"].empty_label = "Branş seçin (opsiyonel)"


class PersonelProfiliForm(forms.ModelForm):
    kullanici_adi = forms.CharField(
        label="Kullanıcı adı",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "cs-input",
                "placeholder": "Örn. yahya.yazici",
                "autocomplete": "off",
            }
        ),
    )

    sifre = forms.CharField(
        label="Şifre",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "cs-input",
                "placeholder": "Yeni personelde zorunludur",
                "autocomplete": "new-password",
            },
            render_value=False,
        ),
        help_text=(
            "Yeni personelde en az 8 karakter girin. "
            "Düzenlemede boş bırakırsanız şifre değişmez."
        ),
    )

    sorumlu_sinif_subeler = forms.ModelMultipleChoiceField(
        label="Sorumlu olduğu sınıf ve şubeler",
        queryset=SinifSube.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-chip-grid"}),
    )

    class Meta:
        model = PersonelProfili
        fields = [
            "ad_soyad",
            "ana_rol",
            "aktif",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Ad ve soyad",
                }
            ),
            "ana_rol": forms.Select(
                attrs={"class": "cs-input"}
            ),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sorumlu_sinif_subeler"].queryset = (
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif", "sube")
        )

        if self.instance and self.instance.pk:
            self.fields["kullanici_adi"].initial = (
                self.instance.user.username
            )
            if self.instance.etut_hocasi_id:
                self.fields["sorumlu_sinif_subeler"].initial = (
                    self.instance.etut_hocasi.sorumlu_sinif_subeler.all()
                )

    def clean_kullanici_adi(self):
        kullanici_adi = (
            self.cleaned_data["kullanici_adi"]
            .strip()
            .lower()
        )

        sorgu = User.objects.filter(
            username__iexact=kullanici_adi
        )

        if self.instance and self.instance.pk:
            sorgu = sorgu.exclude(
                pk=self.instance.user_id
            )

        if sorgu.exists():
            raise forms.ValidationError(
                "Bu kullanıcı adı zaten kullanılıyor."
            )

        return kullanici_adi

    def clean_sifre(self):
        sifre = self.cleaned_data.get("sifre", "")

        if not self.instance.pk and not sifre:
            raise forms.ValidationError(
                "Yeni personel için şifre zorunludur."
            )

        if sifre and len(sifre) < 8:
            raise forms.ValidationError(
                "Şifre en az 8 karakter olmalıdır."
            )

        return sifre

    def clean(self):
        cleaned = super().clean()
        ana_rol = cleaned.get("ana_rol")
        siniflar = cleaned.get("sorumlu_sinif_subeler")

        if ana_rol in {ROL_ETUT_MESUL, ROL_SINIF_MESUL} and not siniflar:
            rol_etiket = "Etüt mesulü" if ana_rol == ROL_ETUT_MESUL else "Sınıf mesulü"
            self.add_error(
                "sorumlu_sinif_subeler",
                f"{rol_etiket} için en az bir sınıf seçin.",
            )

        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        personel = super().save(commit=False)

        kullanici_adi = self.cleaned_data["kullanici_adi"]
        sifre = self.cleaned_data.get("sifre")
        ana_rol = self.cleaned_data["ana_rol"]
        siniflar = self.cleaned_data.get("sorumlu_sinif_subeler")

        if personel.pk:
            user = personel.user
        else:
            user = User()

        user.username = kullanici_adi
        user.first_name = personel.ad_soyad
        user.is_active = personel.aktif
        user.is_staff = True

        if sifre:
            user.set_password(sifre)

        user.save()

        etut_hocasi = personel.etut_hocasi

        if ana_rol in {ROL_ETUT_MESUL, ROL_SINIF_MESUL}:
            if etut_hocasi is None:
                etut_hocasi = EtutHocasi(user=user, ad_soyad=personel.ad_soyad)
            else:
                etut_hocasi.ad_soyad = personel.ad_soyad
                etut_hocasi.aktif = personel.aktif

            etut_hocasi.save()
            etut_hocasi.sorumlu_sinif_subeler.set(siniflar or [])
            personel.etut_hocasi = etut_hocasi
        elif etut_hocasi is not None:
            etut_hocasi.ad_soyad = personel.ad_soyad
            etut_hocasi.aktif = personel.aktif
            etut_hocasi.save()

        personel.user = user

        if commit:
            personel.save()

        return personel


# Geriye dönük uyumluluk
EtutHocasiForm = PersonelProfiliForm


class TalebeForm(forms.ModelForm):
    anne_ad_soyad = forms.CharField(
        required=False,
        label="Anne ad soyad",
        widget=forms.TextInput(attrs={"class": "cs-input", "placeholder": "Veli / anne adı soyadı"}),
    )
    anne_telefon = forms.CharField(
        required=False,
        label="Anne telefon",
        widget=forms.TextInput(
            attrs={
                "class": "cs-input",
                "placeholder": "05XX XXX XX XX",
                "inputmode": "tel",
            }
        ),
    )
    baba_ad_soyad = forms.CharField(
        required=False,
        label="Baba ad soyad",
        widget=forms.TextInput(attrs={"class": "cs-input", "placeholder": "Veli / baba adı soyadı"}),
    )
    baba_telefon = forms.CharField(
        required=False,
        label="Baba telefon",
        widget=forms.TextInput(
            attrs={
                "class": "cs-input",
                "placeholder": "05XX XXX XX XX",
                "inputmode": "tel",
            }
        ),
    )

    bolumler = (
        (
            "Kimlik bilgileri",
            (
                "biyometrik_foto",
                "kimlik_adi",
                "kimlik_soyadi",
                "tc_kimlik",
                "cinsiyet",
                "dogum_tarihi",
            ),
        ),
        (
            "Diğer bilgiler",
            (
                "baba_adi",
                "anne_adi",
                "dogum_yeri",
                "memleket",
                "memleket_ilce",
                "telefon",
                "eposta",
            ),
        ),
        (
            "Eğitim bilgileri",
            (
                "okul_seviyesi",
                "sinif_sube",
                "etut_hocasi",
                "dini_ders_seviyesi",
                "dini_ders_hocasi",
            ),
        ),
        (
            "Aile ve veli",
            (
                "aile_durumu",
                "anne_ad_soyad",
                "anne_telefon",
                "baba_ad_soyad",
                "baba_telefon",
                "ev_adresi",
            ),
        ),
        (
            "Kayıt durumu",
            ("talebe_no", "durum", "aktif"),
        ),
    )

    class Meta:
        model = Talebe
        fields = [
            "biyometrik_foto",
            "kimlik_adi",
            "kimlik_soyadi",
            "ad_soyad",
            "tc_kimlik",
            "cinsiyet",
            "dogum_tarihi",
            "baba_adi",
            "anne_adi",
            "dogum_yeri",
            "memleket",
            "memleket_ilce",
            "telefon",
            "eposta",
            "okul_seviyesi",
            "etut_hocasi",
            "sinif_sube",
            "dini_ders_hocasi",
            "dini_ders_seviyesi",
            "aile_durumu",
            "ev_adresi",
            "talebe_no",
            "durum",
            "aktif",
        ]
        widgets = {
            "biyometrik_foto": forms.ClearableFileInput(
                attrs={"class": "cs-input", "accept": "image/jpeg,image/png,image/webp"}
            ),
            "kimlik_adi": forms.TextInput(attrs={"class": "cs-input"}),
            "kimlik_soyadi": forms.TextInput(attrs={"class": "cs-input"}),
            "ad_soyad": forms.HiddenInput(),
            "tc_kimlik": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "11 haneli TC kimlik no"}
            ),
            "cinsiyet": forms.Select(attrs={"class": "cs-input"}),
            "dogum_tarihi": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "cs-input", "type": "date"},
            ),
            "baba_adi": forms.TextInput(attrs={"class": "cs-input"}),
            "anne_adi": forms.TextInput(attrs={"class": "cs-input"}),
            "dogum_yeri": forms.TextInput(attrs={"class": "cs-input"}),
            "memleket": forms.Select(attrs={"class": "cs-input", "id": "id_memleket"}),
            "memleket_ilce": forms.Select(
                attrs={"class": "cs-input", "id": "id_memleket_ilce"}
            ),
            "telefon": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "05XX XXX XX XX",
                    "inputmode": "tel",
                }
            ),
            "eposta": forms.EmailInput(attrs={"class": "cs-input"}),
            "okul_seviyesi": forms.TextInput(attrs={"class": "cs-input"}),
            "sinif_sube": forms.RadioSelect(attrs={"class": "choice-chip-radio"}),
            "etut_hocasi": forms.Select(attrs={"class": "cs-input"}),
            "dini_ders_hocasi": forms.Select(attrs={"class": "cs-input"}),
            "dini_ders_seviyesi": forms.Select(attrs={"class": "cs-input"}),
            "aile_durumu": forms.Select(attrs={"class": "cs-input"}),
            "ev_adresi": forms.Textarea(
                attrs={
                    "class": "cs-input",
                    "rows": 3,
                    "placeholder": "Mahalle, cadde, bina no, ilçe / il",
                }
            ),
            "talebe_no": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Boş bırakılırsa otomatik atanır",
                }
            ),
            "durum": forms.Select(attrs={"class": "cs-input"}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }
        labels = {
            "sinif_sube": "Okul sınıf / şube",
            "etut_hocasi": "Etüt mesulü",
            "memleket": "Memleket ili",
            "memleket_ilce": "Memleket ilçesi",
            "ev_adresi": "Veli ev adresi",
        }

    def __init__(self, *args, **kwargs):
        from takip.telefon_util import telefon_formatla
        from takip.turkiye_il_ilce import il_secenekleri, ilce_secenekleri

        super().__init__(*args, **kwargs)

        self.fields["dogum_tarihi"].input_formats = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]
        self.fields["sinif_sube"].queryset = (
            SinifSube.objects.filter(aktif=True).order_by("sinif", "sube")
        )
        self.fields["sinif_sube"].empty_label = "Atanmadı"

        hoca_qs = (
            EtutHocasi.objects.filter(aktif=True)
            .prefetch_related("sorumlu_sinif_subeler")
            .order_by("ad_soyad")
        )
        self.fields["etut_hocasi"].queryset = hoca_qs
        self.fields["etut_hocasi"].empty_label = "Etüt mesulü seçin"
        self.fields["dini_ders_hocasi"].queryset = hoca_qs
        self.fields["dini_ders_hocasi"].required = False
        self.fields["dini_ders_hocasi"].empty_label = "Dini ders hocası seçin"
        self.fields["dini_ders_hocasi"].help_text = (
            "Önce dini ders seviyesini seçin. Boş bırakılırsa etüt mesulü atanır."
        )
        self.fields["dini_ders_seviyesi"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["dini_ders_seviyesi"].required = False
        self.fields["dini_ders_seviyesi"].empty_label = "Dini ders seviyesi seçin"
        self.fields["talebe_no"].required = False
        self.fields["talebe_no"].help_text = (
            "Boş bırakırsanız sistem otomatik numara atar (ör. 1, 2, 3)."
        )
        self.fields["tc_kimlik"].required = True
        self.fields["tc_kimlik"].help_text = (
            "Veli panel girişi: kullanıcı adı talebe TC, şifre TC'nin son 4 hanesi."
        )
        self.fields["cinsiyet"].required = False
        self.fields["aile_durumu"].required = False
        self.fields["ad_soyad"].required = False

        self.fields["memleket"].choices = il_secenekleri()
        self.fields["memleket"].required = False
        secili_il = ""
        if self.data.get("memleket"):
            secili_il = self.data.get("memleket")
        elif self.instance.pk:
            secili_il = self.instance.memleket or ""
        elif self.initial.get("memleket"):
            secili_il = self.initial.get("memleket")
        self.fields["memleket_ilce"].choices = ilce_secenekleri(secili_il)
        self.fields["memleket_ilce"].required = False

        if self.instance.pk and self.instance.telefon:
            self.initial["telefon"] = telefon_formatla(self.instance.telefon)

        if self.instance.pk:
            from takip.wave0_models import VeliKisi

            for veli in self.instance.veli_kisileri.all():
                if veli.yakinlik == VeliKisi.Yakinlik.ANNE:
                    self.fields["anne_ad_soyad"].initial = veli.ad_soyad
                    self.fields["anne_telefon"].initial = telefon_formatla(veli.telefon)
                elif veli.yakinlik == VeliKisi.Yakinlik.BABA:
                    self.fields["baba_ad_soyad"].initial = veli.ad_soyad
                    self.fields["baba_telefon"].initial = telefon_formatla(veli.telefon)

    def clean(self):
        from takip.turkiye_il_ilce import memleket_gecerli

        cleaned = super().clean()
        etut = cleaned.get("etut_hocasi")
        dini = cleaned.get("dini_ders_hocasi")
        seviye = cleaned.get("dini_ders_seviyesi")

        if seviye and not dini:
            self.add_error(
                "dini_ders_hocasi",
                "Dini ders seviyesi seçildiğinde dini ders hocası zorunludur.",
            )
        elif seviye and dini:
            if not seviye.hocalar.filter(pk=dini.pk).exists():
                self.add_error(
                    "dini_ders_hocasi",
                    f"Seçilen hoca «{seviye.ad}» seviyesinden sorumlu değil.",
                )
        elif not seviye and dini:
            self.add_error(
                "dini_ders_seviyesi",
                "Dini ders hocası seçmeden önce seviye seçin.",
            )

        if etut and not dini and not seviye:
            cleaned["dini_ders_hocasi"] = etut

        kimlik_ad = (cleaned.get("kimlik_adi") or "").strip()
        kimlik_soyad = (cleaned.get("kimlik_soyadi") or "").strip()
        birlesik = f"{kimlik_ad} {kimlik_soyad}".strip()
        if birlesik:
            cleaned["ad_soyad"] = birlesik
        elif not (cleaned.get("ad_soyad") or "").strip():
            self.add_error("kimlik_adi", "Kimlik adı ve soyadı gerekli.")

        il = (cleaned.get("memleket") or "").strip()
        ilce = (cleaned.get("memleket_ilce") or "").strip()
        if ilce and not memleket_gecerli(il, ilce):
            self.add_error("memleket_ilce", "Seçilen ilçe bu ile ait değil.")

        return cleaned

    def _telefon_temizle(self, alan: str) -> str:
        from takip.telefon_util import telefon_temizle_veya_hata

        deger = self.cleaned_data.get(alan) or ""
        try:
            return telefon_temizle_veya_hata(deger)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_telefon(self):
        return self._telefon_temizle("telefon")

    def clean_anne_telefon(self):
        return self._telefon_temizle("anne_telefon")

    def clean_baba_telefon(self):
        return self._telefon_temizle("baba_telefon")

    def clean_biyometrik_foto(self):
        foto = self.cleaned_data.get("biyometrik_foto")
        dogrula_biyometrik_foto(foto)
        return foto

    def clean_tc_kimlik(self):
        tc = tc_dogrula(self.cleaned_data.get("tc_kimlik"))
        if talebe_tc_cakisma_var_mi(tc, haric_pk=self.instance.pk):
            raise forms.ValidationError(
                "Bu TC kimlik no aktif bir talebede kayıtlı."
            )
        return tc

    def save(self, commit=True):
        talebe = super().save(commit=False)
        if talebe.tc_kimlik:
            pasif_talebe_tc_temizle(talebe.tc_kimlik, haric_pk=talebe.pk)
        if commit:
            talebe.save()
        return talebe

    def veli_kaydet(self, talebe: Talebe) -> None:
        from takip.talebe_excel import _veli_kisi_guncelle
        from takip.wave0_models import VeliKisi

        _veli_kisi_guncelle(
            talebe,
            VeliKisi.Yakinlik.ANNE,
            self.cleaned_data.get("anne_ad_soyad", ""),
            self.cleaned_data.get("anne_telefon", ""),
        )
        _veli_kisi_guncelle(
            talebe,
            VeliKisi.Yakinlik.BABA,
            self.cleaned_data.get("baba_ad_soyad", ""),
            self.cleaned_data.get("baba_telefon", ""),
        )


class TalebeProfilTamamlaForm(forms.ModelForm):
    """Etüt / personel — hızlı kayıttan sonra kalan tüm alanlar (foto dahil)."""

    anne_ad_soyad = forms.CharField(
        required=False,
        label="Anne ad soyad",
        widget=forms.TextInput(attrs={"class": "cs-input", "placeholder": "Anne adı soyadı"}),
    )
    anne_telefon = forms.CharField(
        required=False,
        label="Anne telefon",
        widget=forms.TextInput(
            attrs={"class": "cs-input", "placeholder": "05XX XXX XX XX", "inputmode": "tel"}
        ),
    )
    baba_ad_soyad = forms.CharField(
        required=False,
        label="Baba ad soyad",
        widget=forms.TextInput(attrs={"class": "cs-input", "placeholder": "Baba adı soyadı"}),
    )
    baba_telefon = forms.CharField(
        required=False,
        label="Baba telefon",
        widget=forms.TextInput(
            attrs={"class": "cs-input", "placeholder": "05XX XXX XX XX", "inputmode": "tel"}
        ),
    )

    class Meta:
        model = Talebe
        fields = [
            "biyometrik_foto",
            "ad_soyad",
            "kimlik_adi",
            "kimlik_soyadi",
            "tc_kimlik",
            "cinsiyet",
            "dogum_tarihi",
            "sinif_sube",
            "dini_ders_seviyesi",
            "baba_adi",
            "anne_adi",
            "dogum_yeri",
            "memleket",
            "memleket_ilce",
            "telefon",
            "eposta",
            "aile_durumu",
            "ev_adresi",
        ]
        widgets = {
            "biyometrik_foto": forms.ClearableFileInput(
                attrs={"class": "cs-input", "accept": "image/jpeg,image/png,image/webp"}
            ),
            "ad_soyad": forms.TextInput(attrs={"class": "cs-input"}),
            "kimlik_adi": forms.TextInput(attrs={"class": "cs-input"}),
            "kimlik_soyadi": forms.TextInput(attrs={"class": "cs-input"}),
            "tc_kimlik": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "11 haneli TC",
                    "inputmode": "numeric",
                    "maxlength": "11",
                }
            ),
            "cinsiyet": forms.Select(attrs={"class": "cs-input"}),
            "dogum_tarihi": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "cs-input", "type": "date"},
            ),
            "sinif_sube": forms.Select(attrs={"class": "cs-input"}),
            "dini_ders_seviyesi": forms.Select(attrs={"class": "cs-input"}),
            "baba_adi": forms.TextInput(attrs={"class": "cs-input"}),
            "anne_adi": forms.TextInput(attrs={"class": "cs-input"}),
            "dogum_yeri": forms.TextInput(attrs={"class": "cs-input"}),
            "memleket": forms.Select(attrs={"class": "cs-input", "id": "id_memleket"}),
            "memleket_ilce": forms.Select(
                attrs={"class": "cs-input", "id": "id_memleket_ilce"}
            ),
            "telefon": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "05XX XXX XX XX", "inputmode": "tel"}
            ),
            "eposta": forms.EmailInput(attrs={"class": "cs-input"}),
            "aile_durumu": forms.Select(attrs={"class": "cs-input"}),
            "ev_adresi": forms.Textarea(
                attrs={
                    "class": "cs-input",
                    "rows": 3,
                    "placeholder": "Mahalle, cadde, bina no, ilçe / il",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        from takip.telefon_util import telefon_formatla
        from takip.turkiye_il_ilce import il_secenekleri, ilce_secenekleri

        super().__init__(*args, **kwargs)

        self.fields["dogum_tarihi"].input_formats = ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"]
        self.fields["dogum_tarihi"].required = False
        self.fields["tc_kimlik"].required = False
        self.fields["cinsiyet"].required = False
        self.fields["aile_durumu"].required = False
        self.fields["ad_soyad"].required = True
        self.fields["sinif_sube"].queryset = SinifSube.objects.filter(aktif=True).order_by(
            "sinif", "sube"
        )
        self.fields["sinif_sube"].required = False
        self.fields["sinif_sube"].empty_label = "Sınıf seçin"
        self.fields["dini_ders_seviyesi"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["dini_ders_seviyesi"].required = False
        self.fields["dini_ders_seviyesi"].empty_label = "Seviye seçin"
        for ad in (
            "kimlik_adi",
            "kimlik_soyadi",
            "baba_adi",
            "anne_adi",
            "dogum_yeri",
            "telefon",
            "eposta",
            "ev_adresi",
            "biyometrik_foto",
        ):
            self.fields[ad].required = False

        self.fields["memleket"] = forms.ChoiceField(
            label="Memleket ili",
            required=False,
            choices=il_secenekleri(),
            widget=forms.Select(
                attrs={
                    "class": "cs-input",
                    "id": "id_memleket",
                    "autocomplete": "address-level1",
                }
            ),
        )
        secili_il = ""
        if self.data.get("memleket"):
            secili_il = self.data.get("memleket")
        elif self.instance.pk:
            secili_il = self.instance.memleket or ""
        self.fields["memleket_ilce"] = forms.ChoiceField(
            label="Memleket ilçesi",
            required=False,
            choices=ilce_secenekleri(secili_il),
            widget=forms.Select(
                attrs={
                    "class": "cs-input",
                    "id": "id_memleket_ilce",
                    "autocomplete": "address-level2",
                }
            ),
        )
        if secili_il:
            self.fields["memleket"].initial = secili_il
        if self.instance.pk and self.instance.memleket_ilce:
            self.fields["memleket_ilce"].initial = self.instance.memleket_ilce

        if self.instance.pk and self.instance.telefon:
            self.initial["telefon"] = telefon_formatla(self.instance.telefon)

        if self.instance.pk:
            from takip.wave0_models import VeliKisi

            for veli in self.instance.veli_kisileri.all():
                if veli.yakinlik == VeliKisi.Yakinlik.ANNE:
                    self.fields["anne_ad_soyad"].initial = veli.ad_soyad
                    self.fields["anne_telefon"].initial = telefon_formatla(veli.telefon)
                elif veli.yakinlik == VeliKisi.Yakinlik.BABA:
                    self.fields["baba_ad_soyad"].initial = veli.ad_soyad
                    self.fields["baba_telefon"].initial = telefon_formatla(veli.telefon)

    def clean(self):
        from takip.turkiye_il_ilce import memleket_gecerli

        cleaned = super().clean()
        kimlik_ad = (cleaned.get("kimlik_adi") or "").strip()
        kimlik_soyad = (cleaned.get("kimlik_soyadi") or "").strip()
        if kimlik_ad and kimlik_soyad:
            cleaned["ad_soyad"] = f"{kimlik_ad} {kimlik_soyad}".strip()

        il = (cleaned.get("memleket") or "").strip()
        ilce = (cleaned.get("memleket_ilce") or "").strip()
        if ilce and not memleket_gecerli(il, ilce):
            self.add_error("memleket_ilce", "Seçilen ilçe bu ile ait değil.")
        return cleaned

    def _telefon_temizle(self, alan: str) -> str:
        from takip.telefon_util import telefon_temizle_veya_hata

        deger = self.cleaned_data.get(alan) or ""
        try:
            return telefon_temizle_veya_hata(deger)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_telefon(self):
        return self._telefon_temizle("telefon")

    def clean_anne_telefon(self):
        return self._telefon_temizle("anne_telefon")

    def clean_baba_telefon(self):
        return self._telefon_temizle("baba_telefon")

    def clean_biyometrik_foto(self):
        foto = self.cleaned_data.get("biyometrik_foto")
        dogrula_biyometrik_foto(foto)
        return foto

    def clean_tc_kimlik(self):
        tc = tc_dogrula(self.cleaned_data.get("tc_kimlik"), zorunlu=False)
        if not tc:
            return ""
        if talebe_tc_cakisma_var_mi(tc, haric_pk=self.instance.pk):
            raise forms.ValidationError(
                "Bu TC kimlik no aktif bir talebede kayıtlı."
            )
        return tc

    def save(self, commit=True):
        talebe = super().save(commit=False)
        ad_soyad = self.cleaned_data.get("ad_soyad")
        if ad_soyad:
            talebe.ad_soyad = ad_soyad
        if talebe.tc_kimlik:
            pasif_talebe_tc_temizle(talebe.tc_kimlik, haric_pk=talebe.pk)
        if commit:
            talebe.save()
            self.veli_kaydet(talebe)
        return talebe

    def veli_kaydet(self, talebe: Talebe) -> None:
        from takip.talebe_excel import _veli_kisi_guncelle
        from takip.wave0_models import VeliKisi

        _veli_kisi_guncelle(
            talebe,
            VeliKisi.Yakinlik.ANNE,
            self.cleaned_data.get("anne_ad_soyad", ""),
            self.cleaned_data.get("anne_telefon", ""),
        )
        _veli_kisi_guncelle(
            talebe,
            VeliKisi.Yakinlik.BABA,
            self.cleaned_data.get("baba_ad_soyad", ""),
            self.cleaned_data.get("baba_telefon", ""),
        )


class DuyuruForm(forms.ModelForm):
    class Meta:
        model = Duyuru
        fields = [
            "baslik",
            "ozet",
            "kategori",
            "hedef_kitle",
            "dis_link",
            "gorsel",
            "video_url",
            "video_dosya",
            "ton",
            "baslangic",
            "bitis",
            "sira",
            "aktif",
        ]
        widgets = {
            "baslik": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Duyuru başlığı",
                }
            ),
            "ozet": forms.Textarea(
                attrs={
                    "class": "cs-input",
                    "rows": 8,
                    "placeholder": "Duyuru metni",
                }
            ),
            "kategori": forms.Select(attrs={"class": "cs-input"}),
            "hedef_kitle": forms.Select(attrs={"class": "cs-input"}),
            "dis_link": forms.URLInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "https://",
                }
            ),
            "gorsel": forms.ClearableFileInput(
                attrs={"class": "cs-input", "accept": "image/*"}
            ),
            "video_url": forms.URLInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "YouTube / Vimeo / mp4 bağlantısı",
                }
            ),
            "video_dosya": forms.ClearableFileInput(
                attrs={"class": "cs-input", "accept": "video/*"}
            ),
            "ton": forms.Select(attrs={"class": "cs-input"}),
            "baslangic": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "bitis": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "sira": forms.NumberInput(
                attrs={"class": "cs-input", "min": 0}
            ),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic")
        bitis = cleaned.get("bitis")

        if baslangic and bitis and bitis < baslangic:
            self.add_error(
                "bitis",
                "Bitiş tarihi başlangıçtan önce olamaz.",
            )

        return cleaned


class HaftalikSohbetMevzuuForm(forms.ModelForm):
    class Meta:
        model = HaftalikSohbetMevzuu
        fields = ["baslik", "icerik", "hafta_baslangic", "aktif"]
        widgets = {
            "baslik": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Sohbet başlığı"}
            ),
            "icerik": forms.Textarea(
                attrs={
                    "class": "cs-input",
                    "rows": 8,
                    "placeholder": "Sohbet içeriği",
                }
            ),
            "hafta_baslangic": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }


class CumaDurumMetniForm(forms.ModelForm):
    class Meta:
        model = CumaDurumMetni
        fields = [
            "metin",
            "kaynak",
            "sablon",
            "cuma_tarihi",
            "sira",
            "aktif",
        ]
        widgets = {
            "metin": forms.Textarea(
                attrs={
                    "class": "cs-input",
                    "rows": 5,
                    "placeholder": "Hadis, ayet veya söz metni",
                }
            ),
            "kaynak": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Kaynak (isteğe bağlı)"}
            ),
            "sablon": forms.Select(attrs={"class": "cs-input"}),
            "cuma_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"},
            ),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }


class ProgramPlanForm(forms.ModelForm):
    class Meta:
        model = ProgramPlan
        fields = [
            "ad",
            "aciklama",
            "baslangic_tarihi",
            "bitis_tarihi",
            "aktif",
        ]
        widgets = {
            "ad": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Örn. Bahar Dönemi Programı"}
            ),
            "aciklama": forms.Textarea(
                attrs={"class": "cs-input", "rows": 2}
            ),
            "baslangic_tarihi": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "cs-input", "type": "date"},
            ),
            "bitis_tarihi": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"class": "cs-input", "type": "date"},
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("baslangic_tarihi", "bitis_tarihi"):
            self.fields[name].input_formats = [
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%d.%m.%Y",
            ]

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic_tarihi")
        bitis = cleaned.get("bitis_tarihi")

        if baslangic and bitis and bitis < baslangic:
            self.add_error(
                "bitis_tarihi",
                "Bitiş tarihi başlangıçtan önce olamaz.",
            )

        return cleaned


class ProgramSatirForm(forms.ModelForm):
    class Meta:
        model = ProgramSatir
        fields = [
            "baslangic_saati",
            "bitis_saati",
            "faaliyet_turu",
            "faaliyet_adi",
        ]
        widgets = {
            "baslangic_saati": forms.TimeInput(
                format="%H:%M",
                attrs={"class": "cs-input pg-flow-time", "type": "time"},
            ),
            "bitis_saati": forms.TimeInput(
                format="%H:%M",
                attrs={"class": "cs-input pg-flow-time", "type": "time"},
            ),
            "faaliyet_turu": forms.Select(
                attrs={"class": "cs-input pg-flow-tur", "data-pg-tur": "1"}
            ),
            "faaliyet_adi": forms.TextInput(
                attrs={
                    "class": "cs-input pg-flow-title",
                    "placeholder": "Faaliyet adı",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import ProgramFaaliyetTuru

        for name in ("baslangic_saati", "bitis_saati"):
            self.fields[name].input_formats = ["%H:%M", "%H:%M:%S"]

        turler = ProgramFaaliyetTuru.objects.filter(aktif=True).order_by("sira", "ad")
        choices = [(t.kod, t.ad) for t in turler]
        if not choices:
            choices = list(ProgramSatir.FaaliyetTuru.choices)
        self.fields["faaliyet_turu"] = forms.ChoiceField(
            label="Tür",
            choices=choices,
            widget=forms.Select(
                attrs={"class": "cs-input pg-flow-tur", "data-pg-tur": "1"}
            ),
        )
        if self.instance and self.instance.pk and self.instance.faaliyet_turu:
            mevcut = self.instance.faaliyet_turu
            if mevcut not in dict(choices):
                self.fields["faaliyet_turu"].choices = [
                    (mevcut, mevcut),
                    *choices,
                ]

    def has_changed(self):
        # Tür seçili kalsa bile boş ekstra satırı kayda alma
        if not super().has_changed():
            return False
        bas = self.data.get(self.add_prefix("baslangic_saati")) if self.data else None
        bit = self.data.get(self.add_prefix("bitis_saati")) if self.data else None
        ad = self.data.get(self.add_prefix("faaliyet_adi")) if self.data else None
        if self.is_bound and not (bas or bit or (ad or "").strip()):
            return False
        return True


class ProgramFaaliyetTuruForm(forms.ModelForm):
    class Meta:
        model = ProgramFaaliyetTuru
        fields = ["kod", "ad", "renk", "sira", "aktif"]
        widgets = {
            "kod": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "orn. mola"}
            ),
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "renk": forms.Select(
                choices=[
                    ("green", "Yeşil"),
                    ("blue", "Mavi"),
                    ("amber", "Turuncu"),
                    ("sky", "Açık mavi"),
                    ("slate", "Gri"),
                ],
                attrs={"class": "cs-input"},
            ),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-check"}),
        }


ProgramSatirFormSet = inlineformset_factory(
    ProgramPlan,
    ProgramSatir,
    form=ProgramSatirForm,
    extra=3,
    can_delete=True,
)


class ImamMuezzinListesiForm(forms.ModelForm):
    haric_tarihler_metin = forms.CharField(
        label="Hariç tutulan günler",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "cs-input",
                "rows": 4,
                "placeholder": "Her satıra bir tarih: 15.08.2026",
            }
        ),
        help_text="Tatil ve istisna günleri. Satır satır veya virgülle yazın.",
    )

    class Meta:
        model = ImamMuezzinListesi
        fields = [
            "ad",
            "baslangic_tarihi",
            "bitis_tarihi",
            "cumartesi_dahil",
            "pazar_dahil",
            "talebe_havuzu",
            "aktif",
        ]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "baslangic_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "bitis_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "cumartesi_dahil": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "pazar_dahil": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "talebe_havuzu": forms.CheckboxSelectMultiple(
                attrs={"class": "choice-chip-grid choice-chip-grid--wide"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["talebe_havuzu"].queryset = (
            Talebe.objects.filter(aktif=True)
            .select_related("sinif_sube")
            .order_by("sinif", "sube", "ad_soyad")
        )

        if self.instance and self.instance.pk:
            gosterim = []
            for iso in self.instance.haric_tarihler or []:
                try:
                    y, m, d = iso.split("-")
                    gosterim.append(f"{d}.{m}.{y}")
                except ValueError:
                    gosterim.append(iso)
            self.fields["haric_tarihler_metin"].initial = "\n".join(gosterim)

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic_tarihi")
        bitis = cleaned.get("bitis_tarihi")

        if baslangic and bitis and bitis < baslangic:
            self.add_error(
                "bitis_tarihi",
                "Bitiş tarihi başlangıçtan önce olamaz.",
            )

        return cleaned

    def save(self, commit=True):
        liste = super().save(commit=False)
        liste.haric_tarihler = parse_haric_tarih_metni(
            self.cleaned_data.get("haric_tarihler_metin", "")
        )

        if commit:
            liste.save()
            self.save_m2m()

        return liste


class ImamMuezzinAtamaForm(forms.ModelForm):
    class Meta:
        model = ImamMuezzinAtama
        fields = ["tarih", "imam", "muezzin"]
        widgets = {
            "tarih": forms.DateInput(
                attrs={"class": "cs-input", "type": "date", "readonly": "readonly"}
            ),
            "imam": forms.Select(attrs={"class": "cs-input"}),
            "muezzin": forms.Select(attrs={"class": "cs-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Talebe.objects.filter(aktif=True).order_by("ad_soyad")
        self.fields["imam"].queryset = qs
        self.fields["muezzin"].queryset = qs

    def save(self, commit=True):
        atama = super().save(commit=False)
        atama.manuel_duzenlendi = True

        if commit:
            atama.save()

        return atama


ImamMuezzinAtamaFormSet = inlineformset_factory(
    ImamMuezzinListesi,
    ImamMuezzinAtama,
    form=ImamMuezzinAtamaForm,
    extra=0,
    can_delete=False,
)


class TemizlikAlaniForm(forms.ModelForm):
    class Meta:
        model = TemizlikAlani
        fields = ["ad", "aciklama", "sira", "aktif"]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "aciklama": forms.TextInput(attrs={"class": "cs-input"}),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }


class TemizlikListesiForm(forms.ModelForm):
    haric_tarihler_metin = forms.CharField(
        label="Hariç tutulan günler",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "cs-input",
                "rows": 4,
                "placeholder": "Her satıra bir tarih: 15.08.2026",
            }
        ),
        help_text="Tatil ve istisna günleri. Satır satır veya virgülle yazın.",
    )

    class Meta:
        model = TemizlikListesi
        fields = [
            "ad",
            "baslangic_tarihi",
            "bitis_tarihi",
            "cumartesi_dahil",
            "pazar_dahil",
            "talebe_havuzu",
            "aktif",
        ]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "baslangic_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "bitis_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "cumartesi_dahil": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "pazar_dahil": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "talebe_havuzu": forms.CheckboxSelectMultiple(
                attrs={"class": "choice-chip-grid choice-chip-grid--wide"}
            ),
        }
        help_texts = {
            "talebe_havuzu": "Boş bırakılırsa tüm aktif talebeler kullanılır. Mahaller görev panelinden yönetilir.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["talebe_havuzu"].queryset = (
            Talebe.objects.filter(aktif=True)
            .select_related("sinif_sube")
            .order_by("sinif", "sube", "ad_soyad")
        )

        if self.instance and self.instance.pk:
            gosterim = []
            for iso in self.instance.haric_tarihler or []:
                try:
                    y, m, d = iso.split("-")
                    gosterim.append(f"{d}.{m}.{y}")
                except ValueError:
                    gosterim.append(iso)
            self.fields["haric_tarihler_metin"].initial = "\n".join(gosterim)

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic_tarihi")
        bitis = cleaned.get("bitis_tarihi")

        if baslangic and bitis and bitis < baslangic:
            self.add_error(
                "bitis_tarihi",
                "Bitiş tarihi başlangıçtan önce olamaz.",
            )

        return cleaned

    def save(self, commit=True):
        liste = super().save(commit=False)
        liste.haric_tarihler = parse_haric_tarih_metni(
            self.cleaned_data.get("haric_tarihler_metin", "")
        )

        if commit:
            liste.save()
            self.save_m2m()

        return liste


class TemizlikAtamaForm(forms.ModelForm):
    class Meta:
        model = TemizlikAtama
        fields = ["tarih", "alan", "talebe"]
        widgets = {
            "tarih": forms.DateInput(
                attrs={"class": "cs-input", "type": "date", "readonly": "readonly"}
            ),
            "alan": forms.HiddenInput(),
            "talebe": forms.Select(attrs={"class": "cs-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["talebe"].queryset = Talebe.objects.filter(aktif=True).order_by(
            "ad_soyad"
        )

    def save(self, commit=True):
        atama = super().save(commit=False)
        atama.manuel_duzenlendi = True

        if commit:
            atama.save()

        return atama


TemizlikAtamaFormSet = inlineformset_factory(
    TemizlikListesi,
    TemizlikAtama,
    form=TemizlikAtamaForm,
    extra=0,
    can_delete=False,
)


class YemekOgunForm(forms.ModelForm):
    class Meta:
        model = YemekOgun
        fields = ["ad", "aciklama", "sira", "aktif"]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "aciklama": forms.TextInput(attrs={"class": "cs-input"}),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }


class YemekciListesiForm(forms.ModelForm):
    haric_tarihler_metin = forms.CharField(
        label="Hariç tutulan günler",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "cs-input",
                "rows": 4,
                "placeholder": "Her satıra bir tarih: 15.08.2026",
            }
        ),
        help_text="Tatil ve istisna günleri. Satır satır veya virgülle yazın.",
    )

    class Meta:
        model = YemekciListesi
        fields = [
            "ad",
            "baslangic_tarihi",
            "bitis_tarihi",
            "cumartesi_dahil",
            "pazar_dahil",
            "ogunler",
            "talebe_havuzu",
            "aktif",
        ]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "baslangic_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "bitis_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "cumartesi_dahil": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "pazar_dahil": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
            "ogunler": forms.CheckboxSelectMultiple(
                attrs={"class": "choice-chip-grid"}
            ),
            "talebe_havuzu": forms.CheckboxSelectMultiple(
                attrs={"class": "choice-chip-grid choice-chip-grid--wide"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["ogunler"].queryset = YemekOgun.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["talebe_havuzu"].queryset = (
            Talebe.objects.filter(aktif=True)
            .select_related("sinif_sube")
            .order_by("sinif", "sube", "ad_soyad")
        )

        if self.instance and self.instance.pk:
            gosterim = []
            for iso in self.instance.haric_tarihler or []:
                try:
                    y, m, d = iso.split("-")
                    gosterim.append(f"{d}.{m}.{y}")
                except ValueError:
                    gosterim.append(iso)
            self.fields["haric_tarihler_metin"].initial = "\n".join(gosterim)

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic_tarihi")
        bitis = cleaned.get("bitis_tarihi")

        if baslangic and bitis and bitis < baslangic:
            self.add_error(
                "bitis_tarihi",
                "Bitiş tarihi başlangıçtan önce olamaz.",
            )

        return cleaned

    def save(self, commit=True):
        liste = super().save(commit=False)
        liste.haric_tarihler = parse_haric_tarih_metni(
            self.cleaned_data.get("haric_tarihler_metin", "")
        )

        if commit:
            liste.save()
            self.save_m2m()

        return liste


class YemekciAtamaForm(forms.ModelForm):
    class Meta:
        model = YemekciAtama
        fields = ["tarih", "ogun", "talebe", "yardimci"]
        widgets = {
            "tarih": forms.DateInput(
                attrs={"class": "cs-input", "type": "date", "readonly": "readonly"}
            ),
            "ogun": forms.HiddenInput(),
            "talebe": forms.Select(attrs={"class": "cs-input"}),
            "yardimci": forms.Select(attrs={"class": "cs-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Talebe.objects.filter(aktif=True).order_by("ad_soyad")
        self.fields["talebe"].queryset = qs
        self.fields["yardimci"].queryset = qs

    def save(self, commit=True):
        atama = super().save(commit=False)
        atama.manuel_duzenlendi = True

        if commit:
            atama.save()

        return atama


YemekciAtamaFormSet = inlineformset_factory(
    YemekciListesi,
    YemekciAtama,
    form=YemekciAtamaForm,
    extra=0,
    can_delete=False,
)


class TalebeExcelForm(forms.Form):
    excel_dosyasi = forms.FileField(
        label="Excel dosyası",
        help_text="Yalnızca .xlsx dosyaları desteklenir.",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "cs-input",
                "accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        ),
    )

    def clean_excel_dosyasi(self):
        dosya = self.cleaned_data["excel_dosyasi"]
        if not dosya.name.lower().endswith(".xlsx"):
            raise forms.ValidationError("Lütfen .xlsx uzantılı bir Excel dosyası yükleyin.")
        if dosya.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Dosya boyutu 5 MB'dan küçük olmalıdır.")
        return dosya
