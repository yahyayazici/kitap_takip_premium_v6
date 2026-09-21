"""Akıllı Tahta hesap yönetimi — yönetici formları."""

from __future__ import annotations

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from takip.akilli_tahta_models import AkilliTahtaHesap, SinifSeviyesi
from takip.forms import StyledModelForm


class AkilliTahtaHesapOlusturForm(StyledModelForm):
    username = forms.CharField(label="Kullanıcı adı", max_length=150)
    password = forms.CharField(label="Şifre", widget=forms.PasswordInput)

    class Meta:
        model = AkilliTahtaHesap
        fields = ["sinif_seviyesi", "aktif"]

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu kullanıcı adı zaten kullanılıyor.")
        return username

    def clean_password(self):
        sifre = self.cleaned_data["password"]
        validate_password(sifre)
        return sifre

    def clean_sinif_seviyesi(self):
        seviye = self.cleaned_data["sinif_seviyesi"]
        if AkilliTahtaHesap.objects.filter(sinif_seviyesi=seviye).exists():
            raise forms.ValidationError(
                f"{dict(SinifSeviyesi.choices)[seviye]} için zaten bir akıllı tahta hesabı var."
            )
        return seviye


class AkilliTahtaHesapDuzenleForm(StyledModelForm):
    class Meta:
        model = AkilliTahtaHesap
        fields = ["aktif"]


class SifreDegistirForm(forms.Form):
    password = forms.CharField(label="Yeni şifre", widget=forms.PasswordInput)

    def clean_password(self):
        sifre = self.cleaned_data["password"]
        validate_password(sifre)
        return sifre
