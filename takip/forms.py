from django import forms
from django.utils import timezone

from .models import Kitap, KitapSinavi, OkumaKaydi, Talebe


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
        widget=forms.CheckboxSelectMultiple,
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