"""Veli randevu formları."""

from __future__ import annotations

from django import forms

from takip.models import PersonelProfili
from takip.veli_randevu_models import RandevuMusaitlik, RandevuPersonelAyar


class RandevuPersonelAyarForm(forms.ModelForm):
    class Meta:
        model = RandevuPersonelAyar
        fields = ["aktif", "sure_dk", "aciklama"]
        widgets = {
            "aktif": forms.CheckboxInput(),
            "sure_dk": forms.NumberInput(attrs={"class": "input", "min": 10, "max": 120}),
            "aciklama": forms.TextInput(attrs={"class": "input"}),
        }


class RandevuMusaitlikForm(forms.ModelForm):
    class Meta:
        model = RandevuMusaitlik
        fields = ["hafta_gunu", "baslangic", "bitis", "aktif"]
        widgets = {
            "hafta_gunu": forms.Select(attrs={"class": "input"}),
            "baslangic": forms.TimeInput(attrs={"class": "input", "type": "time"}),
            "bitis": forms.TimeInput(attrs={"class": "input", "type": "time"}),
        }


class VeliRandevuOlusturForm(forms.Form):
    personel_id = forms.ModelChoiceField(
        queryset=PersonelProfili.objects.none(),
        label="Görüşmek istediğiniz personel",
        widget=forms.Select(attrs={"class": "veli-input"}),
    )
    slot = forms.ChoiceField(
        label="Uygun saat",
        choices=(),
        widget=forms.Select(attrs={"class": "veli-input"}),
    )
    konu = forms.CharField(
        required=False,
        label="Konu (opsiyonel)",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "veli-input", "placeholder": "Görüşme konusu"}),
    )


class RandevuGorusmeNotForm(forms.Form):
    ozet = forms.CharField(
        max_length=200,
        label="Özet",
        widget=forms.TextInput(attrs={"class": "input"}),
    )
    detay = forms.CharField(
        label="Görüşme notu",
        widget=forms.Textarea(attrs={"class": "input", "rows": 4}),
    )
    kararlar = forms.CharField(
        required=False,
        label="Alınan kararlar",
        widget=forms.Textarea(attrs={"class": "input", "rows": 2}),
    )
