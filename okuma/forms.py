from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User

from okuma.models import Deneme, DenemeTuru, DenemeTuruDers, Ogrenci, OptikSablon, Soru
from okuma.services.lgs import LGS_YILLARI
from okuma.services.optik import numara_normalize


class DenemeForm(forms.ModelForm):
    tur = forms.ModelChoiceField(
        label="Deneme türü",
        queryset=DenemeTuru.objects.filter(aktif=True),
        empty_label=None,
        help_text="Sınıf, dersler, soru sayıları ve optik düzeni bu türden gelir.",
    )
    lgs_yili = forms.TypedChoiceField(
        label="LGS katsayı yılı",
        coerce=int,
        choices=[(y, y) for y in reversed(LGS_YILLARI)],
        initial=LGS_YILLARI[-1],
        help_text="Yalnızca “geçmiş yıl katsayıları” modunda kullanılır.",
    )

    class Meta:
        model = Deneme
        fields = ["ad", "tur", "tarih", "yanlis_katsayi", "puan_modu", "lgs_yili", "aciklama"]
        widgets = {
            "tarih": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "aciklama": forms.Textarea(attrs={"rows": 2}),
        }


class DenemeDuzenleForm(DenemeForm):
    """Tür, sonradan değiştirilemez (testler ve okunan satırlar ona bağlı)."""

    class Meta(DenemeForm.Meta):
        fields = ["ad", "tarih", "yanlis_katsayi", "puan_modu", "lgs_yili", "aciklama"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("tur")


class AnahtarForm(forms.Form):
    dosya = forms.FileField(label="Cevap anahtarı ve kazanım Excel'i", help_text=".xlsx")


class OptikForm(forms.Form):
    dosya = forms.FileField(label="Optik okuyucu dosyası", help_text=".dat veya .txt")
    sablon = forms.ModelChoiceField(label="Optik şablon", queryset=OptikSablon.objects.all())
    otomatik_ogrenci = forms.BooleanField(
        label="Kayıtsız numaralar için öğrenci aç",
        required=False,
        help_text="Kapalıysa listede olmayan numaralar hatalı satır olarak işaretlenir.",
    )


class SatirForm(forms.Form):
    numara = forms.CharField(max_length=20, required=False)
    kitapcik = forms.CharField(max_length=1, required=False)
    dahil = forms.BooleanField(required=False)


class OgrenciForm(forms.ModelForm):
    class Meta:
        model = Ogrenci
        fields = ["numara", "ad_soyad", "sinif_seviyesi", "sube", "aktif"]
        labels = {"sinif_seviyesi": "Sınıf"}

    def clean_numara(self):
        numara = numara_normalize(self.cleaned_data["numara"])
        if not numara.isdigit():
            raise forms.ValidationError("Numara yalnızca rakamlardan oluşmalı.")
        cakisan = Ogrenci.objects.filter(numara=numara).exclude(pk=self.instance.pk)
        if cakisan.exists():
            raise forms.ValidationError(f"{numara} numarası {cakisan.first().ad_soyad or 'başka bir öğrenci'} için kayıtlı.")
        return numara

    def clean_sube(self):
        return self.cleaned_data["sube"].strip().replace("i", "İ").upper()


class OgrenciTopluForm(forms.Form):
    metin = forms.CharField(
        label="Listeyi yapıştırın",
        required=False,
        widget=forms.Textarea(attrs={"rows": 10, "placeholder": "48\tAhmet Selim Gündüz\t7\tA\n50\tAli Yılmaz\t7\tB\n57 Mehmet Kaya 7A"}),
        help_text="Her satıra bir öğrenci: numara, ad soyad, sınıf, şube. Excel'den kopyalayıp yapıştırabilirsiniz.",
    )
    dosya = forms.FileField(
        label="ya da Excel dosyası",
        required=False,
        help_text="Başlıklar: Numara · Ad Soyad (veya Ad, Soyad) · Sınıf · Şube",
    )
    varsayilan_sinif = forms.CharField(label="Sınıfı yazılmayanlar için sınıf", required=False, max_length=10)

    def clean(self):
        veri = super().clean()
        if not veri.get("metin", "").strip() and not veri.get("dosya"):
            raise forms.ValidationError("Liste yapıştırın ya da Excel dosyası seçin.")
        return veri


class SablonForm(forms.ModelForm):
    class Meta:
        model = OptikSablon
        fields = [
            "ad",
            "kodlama",
            "numara_bas",
            "numara_uzunluk",
            "kitapcik_bas",
            "sinif_bas",
            "sinif_uzunluk",
            "sube_bas",
            "sube_uzunluk",
            "ad_bas",
            "ad_uzunluk",
            "cevap_bas",
            "aciklama",
        ]
        widgets = {"aciklama": forms.Textarea(attrs={"rows": 2})}


class SoruForm(forms.ModelForm):
    dogru = forms.ChoiceField(choices=[(c, c) for c in "ABCDE"], label="Doğru")

    class Meta:
        model = Soru
        fields = ["dogru", "ek_dogrular", "iptal"]

    def clean_ek_dogrular(self):
        deger = "".join(sorted(set(self.cleaned_data["ek_dogrular"].upper()) & set("ABCDE")))
        return deger


class KullaniciOlusturForm(UserCreationForm):
    first_name = forms.CharField(label="Ad soyad", max_length=150, required=False)
    is_superuser = forms.BooleanField(label="Yönetici", required=False, help_text="Kullanıcıları yönetebilir.")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ["username", "first_name", "is_superuser"]

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = True
        if commit:
            user.save()
        return user


class KullaniciDuzenleForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "is_active", "is_superuser"]
        labels = {"first_name": "Ad soyad", "is_active": "Aktif", "is_superuser": "Yönetici"}
        help_texts = {"is_active": "", "is_superuser": "Kullanıcıları yönetebilir."}


class SifreForm(SetPasswordForm):
    pass


class DenemeTuruDersForm(forms.ModelForm):
    class Meta:
        model = DenemeTuruDers
        fields = ["ders", "soru_sayisi", "optik_blok", "katsayi"]

    def clean(self):
        veri = super().clean()
        if veri.get("soru_sayisi") and veri.get("optik_blok") and veri["soru_sayisi"] > veri["optik_blok"]:
            raise forms.ValidationError("Soru sayısı optikteki kutu sayısından fazla olamaz.")
        return veri


DenemeTuruDersFormSet = forms.modelformset_factory(DenemeTuruDers, form=DenemeTuruDersForm, extra=0)
