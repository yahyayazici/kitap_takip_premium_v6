"""Mezun takip merkezi formları."""

from __future__ import annotations

from django import forms
from django.contrib.auth.models import User

from takip.mezun_models import (
    MezunBasari,
    MezunEtkinlik,
    MezunGuncellemeGorevi,
    MezunIletisim,
    MezunProfil,
)
from takip.mezun_service import ALAN_ETIKETLERI


class MezunProfilGuncelleForm(forms.ModelForm):
    class Meta:
        model = MezunProfil
        fields = [
            "mezuniyet_yili",
            "mezuniyet_tarihi",
            "lgs_puani",
            "lgs_yuzdelik",
            "yerlestigi_lise",
            "lise_yerlesme_yili",
            "universite",
            "bolum",
            "universite_yerlesme_yili",
            "yks_puani",
            "yks_sira",
            "meslek",
            "calistigi_kurum",
            "sehir",
            "ulke",
            "iletisim_telefon",
            "iletisim_eposta",
            "iletisim_adres",
            "iletisim_durumu",
            "kurum_bagi",
            "notlar",
        ]
        widgets = {
            "mezuniyet_tarihi": forms.DateInput(attrs={"class": "mz-input", "type": "date"}),
            "iletisim_adres": forms.Textarea(attrs={"class": "mz-input", "rows": 2}),
            "notlar": forms.Textarea(attrs={"class": "mz-input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in ("iletisim_adres", "notlar", "mezuniyet_tarihi"):
                field.widget.attrs.setdefault("class", "mz-input")


class MezunIletisimForm(forms.ModelForm):
    class Meta:
        model = MezunIletisim
        fields = ["tur", "tarih", "aciklama"]
        widgets = {
            "tur": forms.Select(attrs={"class": "mz-input"}),
            "tarih": forms.DateInput(attrs={"class": "mz-input", "type": "date"}),
            "aciklama": forms.Textarea(attrs={"class": "mz-input", "rows": 3}),
        }


class MezunBasariForm(forms.ModelForm):
    class Meta:
        model = MezunBasari
        fields = ["baslik", "kategori", "tarih", "aciklama", "kurum_yarisma", "arsivde_goster"]
        widgets = {
            "baslik": forms.TextInput(attrs={"class": "mz-input"}),
            "kategori": forms.Select(attrs={"class": "mz-input"}),
            "tarih": forms.DateInput(attrs={"class": "mz-input", "type": "date"}),
            "aciklama": forms.Textarea(attrs={"class": "mz-input", "rows": 2}),
            "kurum_yarisma": forms.TextInput(attrs={"class": "mz-input"}),
            "arsivde_goster": forms.CheckboxInput(attrs={"class": "mz-checkbox"}),
        }


class MezunEtkinlikForm(forms.ModelForm):
    class Meta:
        model = MezunEtkinlik
        fields = ["ad", "tur", "tarih", "saat", "yer", "aciklama"]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "mz-input"}),
            "tur": forms.Select(attrs={"class": "mz-input"}),
            "tarih": forms.DateInput(attrs={"class": "mz-input", "type": "date"}),
            "saat": forms.TimeInput(attrs={"class": "mz-input", "type": "time"}),
            "yer": forms.TextInput(attrs={"class": "mz-input"}),
            "aciklama": forms.Textarea(attrs={"class": "mz-input", "rows": 2}),
        }


class MezunGorevForm(forms.ModelForm):
    talep_edilen_alanlar = forms.MultipleChoiceField(
        choices=[(k, v) for k, v in ALAN_ETIKETLERI.items()],
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "choice-chip-grid choice-chip-grid--wide"}
        ),
        label="Talep edilen bilgiler",
    )
    sorumlu = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("first_name", "username"),
        widget=forms.Select(attrs={"class": "mz-input"}),
        label="Sorumlu personel",
    )

    class Meta:
        model = MezunGuncellemeGorevi
        fields = ["baslik", "aciklama", "sorumlu", "son_tarih", "mezuniyet_yili"]
        widgets = {
            "baslik": forms.TextInput(attrs={"class": "mz-input"}),
            "aciklama": forms.Textarea(attrs={"class": "mz-input", "rows": 2}),
            "son_tarih": forms.DateInput(attrs={"class": "mz-input", "type": "date"}),
            "mezuniyet_yili": forms.NumberInput(attrs={"class": "mz-input"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.talep_edilen_alanlar = self.cleaned_data.get("talep_edilen_alanlar") or []
        if commit:
            instance.save()
        return instance
