from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .models import (
    Kitap,
    KitapSinavi,
    OkumaKaydi,
    Talebe,
    TalebeDosyasi,
    TalebeHesap,
    TalebePersonelNotu,
    VeliKisi,
)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "checkbox"
            else:
                field.widget.attrs["class"] = "input"


class KitapForm(StyledModelForm):
    class Meta:
        model = Kitap
        fields = [
            "ad", "yazar", "yayinevi", "toplam_sayfa",
            "sinif_seviyesi", "aciklama"
        ]
        widgets = {"aciklama": forms.Textarea(attrs={"rows": 4})}


class TopluZimmetForm(forms.Form):
    kitap = forms.ModelChoiceField(
        queryset=Kitap.objects.filter(aktif=True),
        widget=forms.Select(attrs={"class": "input"}),
        label="Kitap",
    )
    talebeler = forms.ModelMultipleChoiceField(
        queryset=Talebe.objects.none(),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "choice-chip-grid choice-chip-grid--wide"}
        ),
        label="Talebeler",
    )
    zimmet_tarihi = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
        label="Zimmet tarihi",
    )
    hedef_bitis_tarihi = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
        label="Hedef bitiş tarihi",
    )
    baslangic_sayfasi = forms.IntegerField(
        initial=0,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "input"}),
        label="Başlangıç sayfası",
    )
    aktif_kitabi_olanlari_atla = forms.BooleanField(
        required=False,
        initial=True,
        label="Aktif kitabı olan talebeleri atla",
    )

    def __init__(self, *args, etut_hocasi=None, admin=False, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Talebe.objects.filter(aktif=True).select_related("etut_hocasi")
        if etut_hocasi and not admin:
            qs = qs.filter(etut_hocasi=etut_hocasi)
        self.fields["talebeler"].queryset = qs.order_by(
            "sinif", "sube", "ad_soyad"
        )


class OkumaKaydiForm(StyledModelForm):
    class Meta:
        model = OkumaKaydi
        fields = ["tarih", "son_sayfa", "not_metni"]
        widgets = {
            "tarih": forms.DateInput(attrs={"type": "date"}),
            "not_metni": forms.TextInput(
                attrs={"placeholder": "Kısa not (isteğe bağlı)"}
            ),
        }


class KitapSinaviForm(StyledModelForm):
    class Meta:
        model = KitapSinavi
        fields = [
            "tarih", "toplam_soru", "dogru",
            "yanlis", "bos", "puan", "degerlendirme"
        ]
        widgets = {
            "tarih": forms.DateInput(attrs={"type": "date"}),
            "degerlendirme": forms.Textarea(attrs={"rows": 4}),
        }
from django import forms

from .models import Sinav


class SinavOlusturmaForm(forms.ModelForm):
    class Meta:
        model = Sinav
        fields = [
            "ad",
            "soru_sayisi",
            "sinav_tarihi",
        ]

        labels = {
            "ad": "Sınav Adı",
            "soru_sayisi": "Soru Sayısı",
            "sinav_tarihi": "Sınav Tarihi",
        }

        widgets = {
            "ad": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "Örnek: Gizli Çekmece Kitap Sınavı",
                }
            ),

            "soru_sayisi": forms.NumberInput(
                attrs={
                    "class": "input",
                    "min": 1,
                    "placeholder": "20",
                }
            ),

            "sinav_tarihi": forms.DateInput(
                attrs={
                    "class": "input",
                    "type": "date",
                }
            ),
        }


class TalebePersonelNotuForm(StyledModelForm):
    class Meta:
        model = TalebePersonelNotu
        fields = ["baslik", "icerik", "staff_only", "veliye_goster"]
        widgets = {"icerik": forms.Textarea(attrs={"rows": 4})}


class TalebeDosyasiForm(StyledModelForm):
    class Meta:
        model = TalebeDosyasi
        fields = ["dosya", "aciklama"]


class TalebeGenelDurumForm(forms.Form):
    durum_kodu = forms.ChoiceField(
        choices=[],
        label="Genel durum",
        widget=forms.Select(attrs={"class": "input"}),
    )
    ozet = forms.CharField(
        widget=forms.Textarea(attrs={"class": "input", "rows": 5}),
        label="Genel durum özeti",
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import TalebeGenelDurum

        self.fields["durum_kodu"].choices = TalebeGenelDurum.DurumKodu.choices


class VeliKisiForm(StyledModelForm):
    class Meta:
        model = VeliKisi
        fields = ["yakinlik", "ad_soyad", "telefon", "eposta", "birincil"]


class KttSinavForm(StyledModelForm):
    class Meta:
        from takip.models import KttSinav

        model = KttSinav
        fields = [
            "ad",
            "ders",
            "sinif_seviyesi",
            "sinav_tarihi",
            "soru_sayisi",
            "aciklama",
            "veliye_goster",
            "etut_hocasi",
        ]
        widgets = {
            "sinav_tarihi": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, admin_modu=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not admin_modu:
            self.fields.pop("etut_hocasi", None)


class AkademikMudahaleForm(StyledModelForm):
    class Meta:
        from takip.models import AkademikMudahale

        model = AkademikMudahale
        fields = [
            "talebe",
            "ders",
            "konu",
            "mudahale_turu",
            "tarih",
            "sure_dakika",
            "degerlendirme_notu",
            "veliye_goster",
        ]
        widgets = {
            "tarih": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "degerlendirme_notu": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Ders, MudahaleTuru
        from takip.permissions.scope import yetkili_talebeler

        self.fields["talebe"].queryset = yetkili_talebeler(user).order_by("ad_soyad")
        self.fields["ders"].queryset = Ders.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )
        self.fields["mudahale_turu"].queryset = MudahaleTuru.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["ders"].required = False


class AkademikMudahaleTopluForm(StyledModelForm):
    """Sınıftaki tüm öğrencilere aynı müdahale kaydı."""

    sinif_sube = forms.ModelChoiceField(
        queryset=None,
        label="Sınıf",
        required=True,
        widget=forms.Select(attrs={"class": "input", "id": "id_sinif_sube_toplu"}),
    )

    class Meta:
        from takip.models import AkademikMudahale

        model = AkademikMudahale
        fields = [
            "ders",
            "konu",
            "mudahale_turu",
            "sure_dakika",
            "degerlendirme_notu",
        ]
        widgets = {
            "degerlendirme_notu": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Ders, MudahaleTuru, SinifSube
        from takip.permissions.scope import yetkili_talebeler

        sinif_ids = (
            yetkili_talebeler(user, aktif_only=True)
            .exclude(sinif_sube__isnull=True)
            .values_list("sinif_sube_id", flat=True)
            .distinct()
        )
        self.fields["sinif_sube"].queryset = SinifSube.objects.filter(
            pk__in=sinif_ids, aktif=True
        ).order_by("sinif", "sube")
        self.fields["ders"].queryset = Ders.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )
        self.fields["mudahale_turu"].queryset = MudahaleTuru.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["ders"].required = False
        self.fields["mudahale_turu"].widget.attrs["id"] = "id_mudahale_turu_toplu"
        self.fields["ders"].widget.attrs["id"] = "id_ders_toplu"
        self.fields["konu"].widget.attrs["id"] = "id_konu_toplu"
        self.fields["sure_dakika"].widget.attrs["id"] = "id_sure_dakika_toplu"
        self.fields["degerlendirme_notu"].widget.attrs["id"] = "id_degerlendirme_notu_toplu"


class MudahaleTuruForm(StyledModelForm):
    class Meta:
        from takip.models import MudahaleTuru

        model = MudahaleTuru
        fields = ["ad", "ikon", "renk", "sira", "aktif", "form_semasi"]
        widgets = {
            "form_semasi": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": '[{"key":"kaynak","label":"Kaynak","type":"text"}]',
                }
            ),
        }

    def clean_form_semasi(self):
        val = self.cleaned_data.get("form_semasi")
        if isinstance(val, str):
            if not val.strip():
                return []
            import json

            try:
                return json.loads(val)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError("Geçerli JSON girin.") from exc
        return val or []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.form_semasi:
            import json

            self.initial["form_semasi"] = json.dumps(
                self.instance.form_semasi,
                ensure_ascii=False,
                indent=2,
            )


        widgets = {
            "sinav_tarihi": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }


class DenemeSinaviForm(StyledModelForm):
    class Meta:
        from takip.models import DenemeSinavi

        model = DenemeSinavi
        fields = ["ad", "sinav_tarihi", "sinif_seviyesi", "aciklama"]
        widgets = {
            "sinav_tarihi": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }


class YaziliKampForm(StyledModelForm):
    class Meta:
        from takip.models import YaziliKamp

        model = YaziliKamp
        fields = [
            "ad",
            "baslangic",
            "bitis",
            "sinif_seviyesi",
            "aktif",
            "veli_goster",
        ]
        widgets = {
            "baslangic": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "bitis": forms.DateInput(attrs={"class": "input", "type": "date"}),
        }


class YaziliSinavForm(StyledModelForm):
    class Meta:
        from takip.models import YaziliSinav

        model = YaziliSinav
        fields = [
            "ad",
            "sinav_tarihi",
            "ders",
            "ders_ad",
            "brans",
            "yazili_no",
            "tur",
            "soru_sayisi",
            "durum",
        ]
        widgets = {
            "sinav_tarihi": forms.DateInput(attrs={"class": "input", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Ders

        self.fields["ders"].queryset = Ders.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )
        self.fields["ders"].required = False
        self.fields["soru_sayisi"].required = False


class YaziliSinavPanelForm(StyledModelForm):
    """Etüt hocası paneli — KTT benzeri yazılı oluşturma."""

    DONEM_SECENEKLERI = [(1, "1. Dönem"), (2, "2. Dönem")]
    YAZILI_SECENEKLERI = [(1, "1. Yazılı"), (2, "2. Yazılı")]

    class Meta:
        from takip.models import YaziliSinav

        model = YaziliSinav
        fields = [
            "ad",
            "sinav_tarihi",
            "ders",
            "donem",
            "yazili_no",
            "tur",
        ]
        widgets = {
            "sinav_tarihi": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
        }

    def __init__(self, *args, aktif_tur=None, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Ders, YaziliSinav

        self._aktif_tur = aktif_tur
        self.fields["ders"].queryset = Ders.objects.filter(aktif=True).order_by(
            "sira", "ad"
        )
        self.fields["ders"].required = True
        self.fields["tur"].widget = forms.HiddenInput()

        if aktif_tur == YaziliSinav.Tur.GERCEK:
            self.fields.pop("ad", None)
            self.fields["donem"].widget = forms.Select(
                choices=self.DONEM_SECENEKLERI,
                attrs={"class": "input"},
            )
            self.fields["donem"].required = True
            self.fields["yazili_no"].widget = forms.Select(
                choices=self.YAZILI_SECENEKLERI,
                attrs={"class": "input"},
            )
            if not self.is_bound:
                self.initial.setdefault("donem", 1)
                self.initial.setdefault("yazili_no", 1)
        else:
            self.fields.pop("donem", None)
            self.fields["ad"].required = False
            self.fields["ad"].help_text = (
                "Boş bırakılırsa ders + yazılı no ile doldurulur."
            )

        if aktif_tur in {YaziliSinav.Tur.ORNEK, YaziliSinav.Tur.GERCEK}:
            if not self.is_bound:
                self.initial.setdefault("tur", aktif_tur)


class EtutPlanFaaliyetForm(StyledModelForm):
    class Meta:
        from takip.models import EtutPlanFaaliyet

        model = EtutPlanFaaliyet
        fields = [
            "gun",
            "faaliyet_turu",
            "baslik",
            "aciklama",
            "hedef",
        ]
        widgets = {
            "aciklama": forms.Textarea(attrs={"rows": 2}),
        }


class DiniDersSeviyesiYonetimForm(StyledModelForm):
    class Meta:
        from takip.models import DiniDersSeviyesi

        model = DiniDersSeviyesi
        fields = ["ad", "sira", "aktif", "hocalar"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import EtutHocasi

        self.fields["hocalar"].queryset = EtutHocasi.objects.filter(
            aktif=True
        ).order_by("ad_soyad")


class DiniDersTakipAlaniForm(StyledModelForm):
    class Meta:
        from takip.models import DiniDersTakipAlani

        model = DiniDersTakipAlani
        fields = ["ad", "sira", "aktif"]


class DiniDersKonuForm(StyledModelForm):
    hedef_tarih = forms.DateField(
        required=False,
        label="Hedef tarih",
        help_text="İsteğe bağlı: bu konunun tamamlanması beklenen tarih.",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    class Meta:
        from takip.models import DiniDersKonu

        model = DiniDersKonu
        fields = ["alan", "seviye", "ad", "sira", "aktif"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import DiniDersSeviyesi, DiniDersTakipAlani

        self.fields["alan"].queryset = DiniDersTakipAlani.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["seviye"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        if self.instance and self.instance.pk:
            kayit = getattr(self.instance, "hedef_tarihi_kaydi", None)
            if kayit:
                self.fields["hedef_tarih"].initial = kayit.hedef_tarih


class DiniAlanPlaniForm(StyledModelForm):
    class Meta:
        from takip.models import DiniAlanPlani

        model = DiniAlanPlani
        fields = [
            "egitim_yili",
            "seviye",
            "alan",
            "birinci_donem_hedef",
            "yil_sonu_hedef",
            "aktif",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import DiniDersSeviyesi, DiniDersTakipAlani, EgitimYili

        self.fields["egitim_yili"].queryset = EgitimYili.objects.order_by("-baslangic")
        self.fields["seviye"].queryset = DiniDersSeviyesi.objects.filter(
            aktif=True
        ).order_by("sira", "ad")
        self.fields["alan"].queryset = DiniDersTakipAlani.objects.filter(
            aktif=True
        ).order_by("sira", "ad")


class DiniIlerlemeEsikForm(StyledModelForm):
    class Meta:
        from takip.models import DiniIlerlemeEsik

        model = DiniIlerlemeEsik
        fields = [
            "egitim_yili",
            "plan_onunde_puan",
            "geride_puan",
            "grupla_uyumlu_puan",
            "hiz_artis_esik_puan",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import EgitimYili

        self.fields["egitim_yili"].queryset = EgitimYili.objects.order_by("-baslangic")


class VeliHesapForm(forms.Form):
    username = forms.CharField(max_length=150, label="Kullanıcı adı")
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Şifre",
        required=True,
    )
    ad_soyad = forms.CharField(max_length=120, label="Ad soyad")
    telefon = forms.CharField(max_length=20, required=False, label="Telefon")
    yakinlik = forms.ChoiceField(
        choices=[
            ("anne", "Anne"),
            ("baba", "Baba"),
            ("veli", "Veli"),
            ("diger", "Diğer"),
        ],
        initial="veli",
        label="Yakınlık",
    )
    talebeler = forms.ModelMultipleChoiceField(
        queryset=Talebe.objects.filter(durum=Talebe.Durum.AKTIF).order_by("ad_soyad"),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "choice-chip-grid choice-chip-grid--wide"}
        ),
        label="Bağlı öğrenciler",
    )
    aktif = forms.BooleanField(required=False, initial=True, label="Aktif")

    def __init__(self, *args, instance=None, duzenleme=False, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Talebe

        self.instance = instance
        self.duzenleme = duzenleme
        self.fields["talebeler"].queryset = Talebe.objects.filter(
            durum=Talebe.Durum.AKTIF
        ).order_by("ad_soyad")

        if duzenleme and instance:
            self.fields["username"].initial = instance.user.username
            self.fields["username"].disabled = True
            self.fields["password"].required = False
            self.fields["password"].help_text = "Boş bırakırsanız şifre değişmez."
            self.fields["ad_soyad"].initial = instance.ad_soyad
            self.fields["telefon"].initial = instance.telefon
            self.fields["aktif"].initial = instance.aktif
            self.fields["talebeler"].initial = instance.talebe_baglantilari.values_list(
                "talebe_id", flat=True
            )

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if self.duzenleme:
            return username
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı kullanılıyor.")
        return username

    def clean(self):
        cleaned = super().clean()
        if not self.duzenleme and not cleaned.get("password"):
            self.add_error("password", "Şifre gerekli.")
        if not cleaned.get("talebeler"):
            self.add_error("talebeler", "En az bir öğrenci seçin.")
        return cleaned


class TalebeHesapForm(forms.Form):
    username = forms.CharField(max_length=150, label="Kullanıcı adı")
    password = forms.CharField(
        widget=forms.PasswordInput,
        label="Şifre",
        required=True,
    )
    talebe = forms.ModelChoiceField(
        queryset=Talebe.objects.filter(durum=Talebe.Durum.AKTIF).order_by("ad_soyad"),
        label="Öğrenci",
    )
    aktif = forms.BooleanField(required=False, initial=True, label="Aktif")

    def __init__(self, *args, instance=None, duzenleme=False, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Talebe

        self.instance = instance
        self.duzenleme = duzenleme
        self.fields["talebe"].queryset = Talebe.objects.filter(
            durum=Talebe.Durum.AKTIF
        ).order_by("ad_soyad")

        if duzenleme and instance:
            self.fields["username"].initial = instance.user.username
            self.fields["username"].disabled = True
            self.fields["password"].required = False
            self.fields["password"].help_text = "Boş bırakırsanız şifre değişmez."
            self.fields["talebe"].initial = instance.talebe_id
            self.fields["aktif"].initial = instance.aktif

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if self.duzenleme:
            return username
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı kullanılıyor.")
        return username

    def clean_talebe(self):
        talebe = self.cleaned_data.get("talebe")
        if not talebe:
            return talebe
        qs = TalebeHesap.objects.filter(talebe=talebe)
        if self.duzenleme and self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Bu öğrenci için zaten bir hesap var.")
        return talebe

    def clean(self):
        cleaned = super().clean()
        if not self.duzenleme and not cleaned.get("password"):
            self.add_error("password", "Şifre gerekli.")
        return cleaned


class OgretmenOdemeDonemForm(forms.Form):
    etut_hocasi = forms.ModelChoiceField(
        queryset=None,
        label="Öğretmen",
        widget=forms.Select(attrs={"class": "input"}),
    )
    baslangic = forms.DateField(
        label="Başlangıç",
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
    )
    bitis = forms.DateField(
        label="Bitiş",
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
    )
    notlar = forms.CharField(
        required=False,
        label="Notlar",
        widget=forms.Textarea(attrs={"class": "input", "rows": 2}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.ogretmen_odeme_service import yetkili_odeme_ogretmenleri

        self.user = user
        if user is not None:
            self.fields["etut_hocasi"].queryset = yetkili_odeme_ogretmenleri(
                user,
                olusturma_icin=True,
            )
        else:
            from takip.ogretmen_odeme_service import aktif_ogretmenler

            self.fields["etut_hocasi"].queryset = aktif_ogretmenler()

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic")
        bitis = cleaned.get("bitis")
        if baslangic and bitis and bitis < baslangic:
            self.add_error("bitis", "Bitiş tarihi başlangıçtan önce olamaz.")
        hoca = cleaned.get("etut_hocasi")
        if self.user is not None and hoca is not None:
            from takip.ogretmen_odeme_service import yetkili_odeme_ogretmenleri

            if not yetkili_odeme_ogretmenleri(
                self.user,
                olusturma_icin=True,
            ).filter(pk=hoca.pk).exists():
                self.add_error("etut_hocasi", "Bu öğretmen için kayıt oluşturamazsınız.")
        return cleaned


class MezuniyetIslemForm(StyledModelForm):
    talebe = forms.ModelChoiceField(
        queryset=Talebe.objects.none(),
        label="Talebe",
    )

    class Meta:
        from takip.models import MezunProfil

        model = MezunProfil
        fields = [
            "mezuniyet_yili",
            "mezuniyet_tarihi",
            "donem",
            "lgs_puani",
            "lgs_sira",
            "lgs_yuzdelik",
            "yerlestigi_lise",
            "lise_yerlesme_yili",
            "universite",
            "bolum",
            "yks_puani",
            "yks_sira",
            "iletisim_telefon",
            "iletisim_eposta",
            "iletisim_adres",
            "notlar",
        ]
        widgets = {
            "mezuniyet_tarihi": forms.DateInput(
                attrs={"class": "input", "type": "date"}
            ),
            "iletisim_adres": forms.Textarea(attrs={"rows": 3}),
            "notlar": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, user, *args, duzenleme=False, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import Donem
        from takip.permissions.scope import yetkili_talebeler

        self.duzenleme = duzenleme
        if duzenleme:
            self.fields.pop("talebe", None)
        else:
            self.fields["talebe"].queryset = (
                yetkili_talebeler(user, aktif_only=True)
                .exclude(durum=Talebe.Durum.MEZUN)
                .order_by("ad_soyad")
            )
        self.fields["donem"].queryset = Donem.objects.select_related(
            "egitim_yili"
        ).order_by("-egitim_yili__baslangic", "ad")
        self.fields["donem"].required = False


class AidatTanimForm(StyledModelForm):
    class Meta:
        from takip.models import AidatTanim

        model = AidatTanim
        fields = ["egitim_yili", "ad", "tutar", "vade", "aktif"]
        widgets = {
            "vade": forms.DateInput(attrs={"class": "input", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.wave0_models import EgitimYili

        self.fields["egitim_yili"].queryset = EgitimYili.objects.filter(
            aktif=True
        ).order_by("-baslangic")


class AidatTahsilatForm(forms.Form):
    tutar = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Tutar",
        widget=forms.NumberInput(attrs={"class": "input", "step": "0.01"}),
    )
    tarih = forms.DateField(
        label="Tarih",
        widget=forms.DateInput(attrs={"class": "input", "type": "date"}),
    )
    aciklama = forms.CharField(
        required=False,
        label="Açıklama",
        widget=forms.Textarea(attrs={"class": "input", "rows": 2}),
    )


class OgrenciGorusmesiForm(StyledModelForm):
    yapilacaklar_metin = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"rows": 4, "placeholder": "Her satır bir yapılacak görev"}
        ),
        label="Yapılacaklar",
    )
    etiketler_metin = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={"placeholder": "Etiketleri virgülle ayırın"}
        ),
        label="Etiketler",
    )

    class Meta:
        from takip.models import OgrenciGorusmesi

        model = OgrenciGorusmesi
        fields = [
            "talebe",
            "tur",
            "tarih",
            "saat",
            "ozet",
            "detay",
            "kararlar",
            "veli_goster",
            "takip_gerekiyor",
            "genel_durum",
            "sonraki_gorusme",
            "sonraki_gorusme_saat",
        ]
        widgets = {
            "tarih": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "saat": forms.TimeInput(attrs={"class": "input", "type": "time"}),
            "sonraki_gorusme": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "sonraki_gorusme_saat": forms.TimeInput(attrs={"class": "input", "type": "time"}),
            "detay": forms.Textarea(attrs={"rows": 5}),
            "kararlar": forms.Textarea(attrs={"rows": 4, "placeholder": "Her satır bir karar"}),
            "genel_durum": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, user, *args, alan=None, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import GorusmeTuru
        from takip.permissions.scope import yetkili_talebeler

        self.user = user
        self.alan = alan
        self.fields["talebe"].queryset = yetkili_talebeler(
            user, aktif_only=False
        ).order_by("ad_soyad")
        tur_qs = GorusmeTuru.objects.filter(aktif=True)
        if alan:
            tur_qs = tur_qs.filter(alan=alan)
        self.fields["tur"].queryset = tur_qs.order_by("sira", "ad")

        if self.instance.pk:
            if self.instance.yapilacaklar:
                self.fields["yapilacaklar_metin"].initial = "\n".join(
                    item.get("metin", "") if isinstance(item, dict) else str(item)
                    for item in self.instance.yapilacaklar
                )
            if self.instance.etiketler:
                self.fields["etiketler_metin"].initial = ", ".join(self.instance.etiketler)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.kaydeden = self.user

        etiketler = [
            e.strip()
            for e in self.cleaned_data.get("etiketler_metin", "").split(",")
            if e.strip()
        ]
        instance.etiketler = etiketler

        yapilacaklar = []
        for satir in self.cleaned_data.get("yapilacaklar_metin", "").splitlines():
            metin = satir.strip()
            if metin:
                yapilacaklar.append({"metin": metin, "tamamlandi": False})
        instance.yapilacaklar = yapilacaklar

        if commit:
            instance.save()
            from takip.rehberlik_service import gorevleri_kaydet

            gorevleri_kaydet(instance, yapilacaklar)
        return instance


class DisiplinKaydiForm(StyledModelForm):
    class Meta:
        from takip.models import DisiplinKaydi

        model = DisiplinKaydi
        fields = ["talebe", "tur", "tarih", "aciklama", "sonuc"]
        widgets = {
            "tarih": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "aciklama": forms.Textarea(attrs={"rows": 4}),
            "sonuc": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import DisiplinOlayTuru
        from takip.permissions.scope import yetkili_talebeler

        self.fields["talebe"].queryset = yetkili_talebeler(
            user, aktif_only=True
        ).order_by("ad_soyad")
        self.fields["tur"].queryset = DisiplinOlayTuru.objects.filter(
            aktif=True
        ).order_by("sira", "ad")


class GunlukTakipKaydiForm(StyledModelForm):
    class Meta:
        from takip.models import GunlukTakipKaydi

        model = GunlukTakipKaydi
        fields = ["talebe", "tarih", "devam", "etut_katilim", "not_alani"]
        widgets = {
            "tarih": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "not_alani": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.permissions.scope import yetkili_talebeler

        self.fields["talebe"].queryset = yetkili_talebeler(
            user, aktif_only=True
        ).order_by("ad_soyad")

class PersonelVazifeForm(StyledModelForm):
    class Meta:
        from takip.vazife_models import PersonelVazife

        model = PersonelVazife
        fields = [
            "baslik",
            "aciklama",
            "atanan",
            "sinif_sube",
            "baslangic",
            "bitis",
            "durum",
            "oncelik",
        ]
        labels = {
            "bitis": "Şu güne kadar",
            "baslangic": "Başlangıç",
            "atanan": "Personel",
        }
        help_texts = {
            "bitis": "Bu tarihe kadar personele ana sayfada ve Vazifelerim’de bildirim gider.",
        }
        widgets = {
            "baslangic": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "bitis": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import PersonelProfili, SinifSube

        self.fields["atanan"].queryset = PersonelProfili.objects.filter(
            aktif=True
        ).order_by("ad_soyad")
        self.fields["sinif_sube"].queryset = SinifSube.objects.filter(
            aktif=True
        ).order_by("sinif", "sube")
        self.fields["sinif_sube"].required = False
        self.fields["bitis"].required = True

    def clean(self):
        cleaned = super().clean()
        baslangic = cleaned.get("baslangic")
        bitis = cleaned.get("bitis")
        if baslangic and bitis and bitis < baslangic:
            self.add_error("bitis", "Şu güne kadar tarihi başlangıçtan önce olamaz.")
        return cleaned


class PersonelToplantisiForm(StyledModelForm):
    class Meta:
        from takip.personel_toplanti_models import PersonelToplantisi

        model = PersonelToplantisi
        fields = [
            "baslik",
            "tarih",
            "katilimci_personeller",
            "durum",
        ]
        widgets = {
            "baslik": forms.TextInput(
                attrs={"class": "input", "placeholder": "Alt başlık (isteğe bağlı)"}
            ),
            "tarih": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "katilimci_personeller": forms.SelectMultiple(
                attrs={
                    "class": "input ms-filter",
                    "data-placeholder": "Katılımcı seçin (isteğe bağlı)",
                }
            ),
        }

    def __init__(self, *args, olusturma=False, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import PersonelProfili

        profil_qs = PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad")
        self.fields["katilimci_personeller"].queryset = profil_qs
        self.fields["katilimci_personeller"].required = False
        self.fields["katilimci_personeller"].label = "Katılımcılar"
        self.fields["baslik"].required = False
        self.fields["baslik"].label = "Alt başlık"
        if olusturma:
            self.fields.pop("durum", None)


class PersonelToplantiGundemForm(StyledModelForm):
    class Meta:
        from takip.personel_toplanti_models import PersonelToplantiGundemMadde

        model = PersonelToplantiGundemMadde
        fields = ["madde", "gorusulen", "sira"]
        widgets = {
            "madde": forms.TextInput(attrs={"placeholder": "Gündem maddesi"}),
            "gorusulen": forms.Textarea(
                attrs={"rows": 2, "placeholder": "Toplantıda konuşulanlar"}
            ),
            "sira": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["sira"].required = False
        self.fields["madde"].required = False
        self.fields["gorusulen"].required = False

    def clean(self):
        cleaned = super().clean()
        madde = (cleaned.get("madde") or "").strip()
        gorusulen = (cleaned.get("gorusulen") or "").strip()
        if madde or gorusulen:
            cleaned["madde"] = madde
            cleaned["gorusulen"] = gorusulen
        return cleaned


class PersonelToplantiYapilacakForm(StyledModelForm):
    """Yapılacak / takip maddesi — personele vazife olarak yansır."""

    class Meta:
        from takip.personel_toplanti_models import PersonelToplantiKarar

        model = PersonelToplantiKarar
        fields = ["metin", "sorumlu", "kontrol_tarihi", "durum", "sira"]
        widgets = {
            "metin": forms.Textarea(attrs={"rows": 2, "placeholder": "Yapılacak iş"}),
            "kontrol_tarihi": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "sira": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import PersonelProfili

        self.fields["sorumlu"].queryset = PersonelProfili.objects.filter(
            aktif=True
        ).order_by("ad_soyad")
        self.fields["sorumlu"].required = False
        self.fields["kontrol_tarihi"].required = False
        self.fields["sira"].required = False
        self.fields["metin"].required = False

    def clean_metin(self):
        return (self.cleaned_data.get("metin") or "").strip()


class PersonelToplantiKararForm(StyledModelForm):
    class Meta:
        from takip.personel_toplanti_models import PersonelToplantiKarar

        model = PersonelToplantiKarar
        fields = ["tur", "metin", "sorumlu", "kontrol_tarihi", "durum", "sira"]
        widgets = {
            "metin": forms.Textarea(attrs={"rows": 2, "placeholder": "Karar / yapılacak metni"}),
            "kontrol_tarihi": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "sira": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from takip.models import PersonelProfili

        self.fields["sorumlu"].queryset = PersonelProfili.objects.filter(
            aktif=True
        ).order_by("ad_soyad")
        self.fields["sorumlu"].required = False
        self.fields["kontrol_tarihi"].required = False
        self.fields["sira"].required = False
        self.fields["metin"].required = False

    def clean_metin(self):
        return (self.cleaned_data.get("metin") or "").strip()


class YctOlayForm(StyledModelForm):
    class Meta:
        from takip.yct_models import YctOlay

        model = YctOlay
        fields = [
            "baslik",
            "aciklama",
            "baslangic",
            "bitis",
            "kategori",
            "tum_personel",
        ]
        widgets = {
            "baslik": forms.TextInput(
                attrs={"class": "input", "placeholder": "Örn: LGS deneme haftası"}
            ),
            "aciklama": forms.Textarea(
                attrs={"class": "input", "rows": 3, "placeholder": "Plan detayı"}
            ),
            "baslangic": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "bitis": forms.DateInput(attrs={"class": "input", "type": "date"}),
            "kategori": forms.Select(attrs={"class": "input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bitis"].required = False
        self.fields["aciklama"].required = False


class SinavBasvuruForm(StyledModelForm):
    bilgilendirme_onay = forms.BooleanField(
        required=True,
        label="Bilgilendirme ve değerlendirme metinlerini okudum, anladım.",
        error_messages={
            "required": "Devam etmek için bilgilendirme metnini onaylayın.",
        },
    )

    class Meta:
        from takip.models import SinavBasvuru

        model = SinavBasvuru
        fields = [
            "ad_soyad",
            "baba_adi",
            "baba_telefon",
            "anne_adi",
            "anne_telefon",
            "il",
            "ilce",
            "dogum_tarihi",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={"placeholder": "Öğrencinin adı ve soyadı", "autocomplete": "name"}
            ),
            "baba_adi": forms.TextInput(attrs={"placeholder": "Baba adı"}),
            "baba_telefon": forms.TextInput(
                attrs={
                    "placeholder": "05xx xxx xx xx",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                }
            ),
            "anne_adi": forms.TextInput(attrs={"placeholder": "Anne adı"}),
            "anne_telefon": forms.TextInput(
                attrs={
                    "placeholder": "05xx xxx xx xx",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                }
            ),
            "il": forms.Select(attrs={"class": "sb-select"}),
            "ilce": forms.Select(attrs={"class": "sb-select"}),
            "dogum_tarihi": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        from takip.sinav_basvuru_choices import (
            ISTANBUL,
            ISTANBUL_ILCE_CHOICES,
        )

        super().__init__(*args, **kwargs)
        self.fields["il"].choices = [(ISTANBUL, ISTANBUL)]
        self.fields["il"].initial = ISTANBUL
        self.fields["ilce"].choices = ISTANBUL_ILCE_CHOICES
        if not self.is_bound and not self.initial.get("il"):
            self.initial["il"] = ISTANBUL

    def _clean_telefon_alan(self, alan: str) -> str:
        telefon = (self.cleaned_data.get(alan) or "").strip()
        digits = "".join(ch for ch in telefon if ch.isdigit())
        if len(digits) < 10:
            raise forms.ValidationError("Geçerli bir telefon numarası girin.")
        return telefon

    def clean_baba_telefon(self):
        return self._clean_telefon_alan("baba_telefon")

    def clean_anne_telefon(self):
        return self._clean_telefon_alan("anne_telefon")

    def clean_ad_soyad(self):
        return (self.cleaned_data.get("ad_soyad") or "").strip()

    def clean_il(self):
        from takip.sinav_basvuru_choices import ISTANBUL

        return ISTANBUL

    def clean_ilce(self):
        from takip.sinav_basvuru_choices import ISTANBUL_ILCELERI

        ilce = (self.cleaned_data.get("ilce") or "").strip()
        if ilce not in ISTANBUL_ILCELERI:
            raise forms.ValidationError("İstanbul ilçelerinden birini seçin.")
        return ilce


class SinavBasvuruMesajSablonForm(StyledModelForm):
    class Meta:
        from takip.models import SinavBasvuruMesajSablon

        model = SinavBasvuruMesajSablon
        fields = [
            "baslik",
            "metin",
            "aktif",
            "alici",
            "wa_template_name",
            "wa_template_lang",
            "sira",
        ]
        widgets = {
            "metin": forms.Textarea(attrs={"rows": 6}),
        }

