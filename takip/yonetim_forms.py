from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.forms import inlineformset_factory

from .models import (
    Duyuru,
    EtutHocasi,
    ImamMuezzinAtama,
    ImamMuezzinListesi,
    PersonelProfili,
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
        widget=forms.CheckboxSelectMultiple(),
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
    class Meta:
        model = Talebe
        fields = [
            "ad_soyad",
            "talebe_no",
            "sinif_sube",
            "etut_hocasi",
            "dini_ders_hocasi",
            "durum",
            "dini_ders_seviyesi",
            "dogum_tarihi",
            "telefon",
            "eposta",
            "aktif",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Talebenin adını ve soyadını yazın",
                }
            ),
            "talebe_no": forms.TextInput(
                attrs={
                    "class": "cs-input",
                    "placeholder": "Boş bırakılırsa otomatik atanır",
                }
            ),
            "sinif_sube": forms.RadioSelect(),
            "etut_hocasi": forms.Select(
                attrs={"class": "cs-input"}
            ),
            "dini_ders_hocasi": forms.Select(
                attrs={"class": "cs-input"}
            ),
            "aktif": forms.CheckboxInput(
                attrs={"class": "cs-checkbox"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sinif_sube"].queryset = (
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif", "sube")
        )

        hoca_qs = (
            EtutHocasi.objects.filter(aktif=True)
            .prefetch_related("sorumlu_sinif_subeler")
            .order_by("ad_soyad")
        )
        self.fields["etut_hocasi"].queryset = hoca_qs
        self.fields["dini_ders_hocasi"].queryset = hoca_qs
        self.fields["dini_ders_hocasi"].required = False
        self.fields["dini_ders_hocasi"].help_text = (
            "Etüt hocasından farklı olabilir. Boş bırakılırsa etüt hocası atanır."
        )
        self.fields["talebe_no"].required = False
        self.fields["talebe_no"].help_text = (
            "Boş bırakırsanız sistem otomatik numara atar (ör. 1, 2, 3)."
        )

    def clean(self):
        cleaned = super().clean()
        etut = cleaned.get("etut_hocasi")
        dini = cleaned.get("dini_ders_hocasi")

        if etut and not dini:
            cleaned["dini_ders_hocasi"] = etut

        return cleaned


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
                    "rows": 3,
                    "placeholder": "Ana sayfada görünecek kısa metin",
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
                attrs={"class": "cs-input", "type": "date"}
            ),
            "bitis_tarihi": forms.DateInput(
                attrs={"class": "cs-input", "type": "date"}
            ),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }

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
            "sira",
            "baslangic_saati",
            "bitis_saati",
            "faaliyet_turu",
            "faaliyet_adi",
            "program_adi",
            "faaliyet_durumu",
        ]
        widgets = {
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "baslangic_saati": forms.TimeInput(
                attrs={"class": "cs-input", "type": "time"}
            ),
            "bitis_saati": forms.TimeInput(
                attrs={"class": "cs-input", "type": "time"}
            ),
            "faaliyet_turu": forms.Select(attrs={"class": "cs-input"}),
            "faaliyet_adi": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Faaliyet adı"}
            ),
            "program_adi": forms.TextInput(
                attrs={"class": "cs-input", "placeholder": "Opsiyonel"}
            ),
            "faaliyet_durumu": forms.Select(attrs={"class": "cs-input"}),
        }


ProgramSatirFormSet = inlineformset_factory(
    ProgramPlan,
    ProgramSatir,
    form=ProgramSatirForm,
    extra=2,
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
            "talebe_havuzu": forms.CheckboxSelectMultiple(),
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
            "talebe_havuzu": forms.CheckboxSelectMultiple(),
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
            "ogunler": forms.CheckboxSelectMultiple(),
            "talebe_havuzu": forms.CheckboxSelectMultiple(),
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
