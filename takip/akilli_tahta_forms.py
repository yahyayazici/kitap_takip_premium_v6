"""Akıllı Tahta Dosya Merkezi — formlar."""

from __future__ import annotations

from django import forms

from takip.akilli_tahta_models import AkilliTahtaDosya, SinifSeviyesi
from takip.forms import StyledModelForm
from takip.wave0_models import Ders


class AkilliTahtaDosyaForm(StyledModelForm):
    hedef_sinif_seviyeleri = forms.MultipleChoiceField(
        choices=SinifSeviyesi.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "choice-chip-grid"}),
        label="Hedef sınıf seviyeleri",
    )

    class Meta:
        model = AkilliTahtaDosya
        fields = [
            "baslik",
            "dosya",
            "icerik_turu",
            "ders",
            "aciklama",
            "tum_siniflar",
            "hedef_sinif_seviyeleri",
            "yayin_baslangic",
            "yayin_bitis",
            "ust_sirada",
            "indirme_izni",
        ]
        widgets = {
            "aciklama": forms.Textarea(attrs={"rows": 3}),
            "yayin_baslangic": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "yayin_bitis": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ders"].queryset = Ders.objects.filter(aktif=True)
        self.fields["ders"].required = False
        self.fields["yayin_baslangic"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["yayin_bitis"].input_formats = ["%Y-%m-%dT%H:%M"]
        if self.instance and self.instance.pk:
            self.fields["hedef_sinif_seviyeleri"].initial = list(
                self.instance.hedefler.values_list("sinif_seviyesi", flat=True)
            )

    def clean(self):
        temiz = super().clean()
        tum_siniflar = temiz.get("tum_siniflar")
        hedefler = temiz.get("hedef_sinif_seviyeleri")
        if not tum_siniflar and not hedefler:
            raise forms.ValidationError(
                "“Tüm sınıflara gönder” kapalıysa en az bir sınıf seviyesi seçmelisiniz."
            )
        yayin_bitis = temiz.get("yayin_bitis")
        yayin_baslangic = temiz.get("yayin_baslangic")
        if yayin_bitis and yayin_baslangic and yayin_bitis <= yayin_baslangic:
            raise forms.ValidationError(
                "Yayından kaldırılma tarihi, yayın başlangıcından sonra olmalı."
            )
        return temiz
