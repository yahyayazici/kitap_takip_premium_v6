"""Finans formları."""

from __future__ import annotations

from django import forms

from takip.finans_models import FinansIndirim, FinansTahsilat, FinansUcretPolitikasi


class FinansTahsilatForm(forms.Form):
    tutar = forms.DecimalField(
        min_value=0.01,
        max_digits=12,
        decimal_places=2,
        label="Tutar",
        widget=forms.NumberInput(attrs={"class": "fn-input", "step": "0.01"}),
    )
    tarih = forms.DateField(
        label="Tarih",
        widget=forms.DateInput(attrs={"class": "fn-input", "type": "date"}),
    )
    yontem = forms.ChoiceField(
        choices=FinansTahsilat.Yontem.choices,
        label="Ödeme yöntemi",
        widget=forms.Select(attrs={"class": "fn-input"}),
    )
    tur = forms.ChoiceField(
        choices=FinansTahsilat.Tur.choices,
        label="Tür",
        widget=forms.Select(attrs={"class": "fn-input"}),
    )
    taksit_id = forms.IntegerField(required=False, widget=forms.HiddenInput())
    aciklama = forms.CharField(
        required=False,
        label="Açıklama",
        widget=forms.Textarea(attrs={"class": "fn-input", "rows": 2}),
    )


class FinansYeniKayitForm(forms.Form):
    talebe_id = forms.ChoiceField(
        label="Öğrenci",
        choices=(),
        widget=forms.Select(attrs={"class": "fn-input fn-select"}),
    )
    indirim_tutari = forms.DecimalField(
        required=False,
        initial=0,
        max_digits=12,
        decimal_places=2,
        label="İndirim tutarı",
        widget=forms.NumberInput(attrs={"class": "fn-input", "step": "0.01"}),
    )
    pesinat = forms.DecimalField(
        required=False,
        initial=0,
        max_digits=12,
        decimal_places=2,
        label="Peşinat",
        widget=forms.NumberInput(attrs={"class": "fn-input", "step": "0.01"}),
    )
    taksit_sayisi = forms.IntegerField(
        initial=10,
        min_value=1,
        max_value=24,
        label="Taksit sayısı",
        widget=forms.NumberInput(attrs={"class": "fn-input"}),
    )


class FinansPolitikaForm(forms.ModelForm):
    class Meta:
        model = FinansUcretPolitikasi
        fields = ["sinif_seviyesi", "tutar", "aktif"]
        widgets = {
            "sinif_seviyesi": forms.Select(attrs={"class": "fn-input"}),
            "tutar": forms.NumberInput(attrs={"class": "fn-input", "step": "0.01"}),
            "aktif": forms.CheckboxInput(attrs={"class": "fn-checkbox"}),
        }


class FinansIndirimForm(forms.ModelForm):
    class Meta:
        model = FinansIndirim
        fields = ["ad", "kod", "tur", "deger", "aktif", "baslangic", "bitis", "aciklama"]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "fn-input"}),
            "kod": forms.TextInput(attrs={"class": "fn-input"}),
            "tur": forms.Select(attrs={"class": "fn-input"}),
            "deger": forms.NumberInput(attrs={"class": "fn-input", "step": "0.01"}),
            "aktif": forms.CheckboxInput(attrs={"class": "fn-checkbox"}),
            "baslangic": forms.DateInput(attrs={"class": "fn-input", "type": "date"}),
            "bitis": forms.DateInput(attrs={"class": "fn-input", "type": "date"}),
            "aciklama": forms.TextInput(attrs={"class": "fn-input"}),
        }
