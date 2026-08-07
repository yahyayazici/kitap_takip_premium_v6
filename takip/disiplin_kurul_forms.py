"""Disiplin Kurulu formları."""

from __future__ import annotations

from django import forms

from takip.disiplin_kurul_models import DisiplinKurulKarar, DisiplinKurulu
from takip.disiplin_kurul_service import DEFAULT_GUNDEM, kurul_ayarlari, varsayilan_gundem_listesi
from takip.models import PersonelProfili, Talebe
from takip.permissions.scope import yetkili_talebeler


class DisiplinKurulOlusturForm(forms.Form):
    talebe = forms.ModelChoiceField(
        queryset=Talebe.objects.none(),
        label="Öğrenci",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    toplanti_tarihi = forms.DateField(
        label="Toplantı tarihi",
        widget=forms.DateInput(attrs={"type": "date", "class": "dk-input"}),
    )
    toplanti_saati = forms.TimeField(
        label="Toplantı saati",
        required=False,
        widget=forms.TimeInput(attrs={"type": "time", "class": "dk-input"}),
    )
    toplanti_yeri = forms.CharField(
        label="Toplantı yeri",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "dk-input", "placeholder": "Örn: Rehberlik Odası"}),
    )
    genel_aciklama = forms.CharField(
        label="Toplantı notu / açıklama",
        required=False,
        widget=forms.Textarea(attrs={"class": "dk-input", "rows": 3}),
    )
    gundem_metin = forms.CharField(
        label="Gündem maddeleri",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "dk-input",
                "rows": 8,
                "placeholder": "Her satır bir gündem maddesi",
            }
        ),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["talebe"].queryset = yetkili_talebeler(user).order_by("ad_soyad")
        ayar = kurul_ayarlari()
        if not self.initial.get("toplanti_yeri") and ayar.varsayilan_toplanti_yeri:
            self.initial["toplanti_yeri"] = ayar.varsayilan_toplanti_yeri
        if not self.initial.get("gundem_metin"):
            gundem = varsayilan_gundem_listesi()
            self.initial["gundem_metin"] = "\n".join(gundem or DEFAULT_GUNDEM)

    def temiz_gundem(self) -> list[str]:
        raw = self.cleaned_data.get("gundem_metin") or ""
        return [line.strip() for line in raw.splitlines() if line.strip()]


class DisiplinKurulAyarForm(forms.Form):
    kurul_adi = forms.CharField(
        label="Kurul adı",
        max_length=160,
        widget=forms.TextInput(attrs={"class": "dk-input"}),
    )
    varsayilan_toplanti_yeri = forms.CharField(
        label="Varsayılan toplantı yeri",
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "dk-input"}),
    )


class DisiplinKurulVarsayilanUyeForm(forms.Form):
    personel = forms.ModelChoiceField(
        queryset=PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad"),
        label="Personel",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    kurul_gorevi = forms.ChoiceField(
        choices=[],
        label="Kuruldaki görevi",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    sira = forms.IntegerField(
        label="Sıra",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"class": "dk-input"}),
    )
    aktif = forms.BooleanField(label="Aktif", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        from takip.disiplin_kurul_models import DisiplinKurulKatilimci

        super().__init__(*args, **kwargs)
        self.fields["kurul_gorevi"].choices = DisiplinKurulKatilimci.KurulGorevi.choices


class DisiplinKurulVarsayilanGundemForm(forms.Form):
    baslik = forms.CharField(
        label="Gündem maddesi",
        max_length=240,
        widget=forms.TextInput(attrs={"class": "dk-input"}),
    )
    sira = forms.IntegerField(
        label="Sıra",
        required=False,
        min_value=1,
        widget=forms.NumberInput(attrs={"class": "dk-input"}),
    )
    aktif = forms.BooleanField(label="Aktif", required=False, initial=True)


class DisiplinKurulKatilimciForm(forms.Form):
    personel = forms.ModelChoiceField(
        queryset=PersonelProfili.objects.filter(aktif=True).order_by("ad_soyad"),
        label="Personel",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    kurul_gorevi = forms.ChoiceField(
        choices=[],
        label="Kuruldaki görevi",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )

    def __init__(self, *args, **kwargs):
        from takip.disiplin_kurul_models import DisiplinKurulKatilimci

        super().__init__(*args, **kwargs)
        self.fields["kurul_gorevi"].choices = DisiplinKurulKatilimci.KurulGorevi.choices


class DisiplinKurulKararForm(forms.ModelForm):
    class Meta:
        model = DisiplinKurulKarar
        fields = (
            "metin",
            "kategori",
            "sorumlu",
            "baslangic_tarihi",
            "kontrol_tarihi",
            "durum",
            "iliskili_modul",
            "notlar",
        )
        widgets = {
            "metin": forms.Textarea(attrs={"class": "dk-input", "rows": 3}),
            "kategori": forms.Select(attrs={"class": "dk-input"}),
            "sorumlu": forms.Select(attrs={"class": "dk-input"}),
            "baslangic_tarihi": forms.DateInput(attrs={"type": "date", "class": "dk-input"}),
            "kontrol_tarihi": forms.DateInput(attrs={"type": "date", "class": "dk-input"}),
            "durum": forms.Select(attrs={"class": "dk-input"}),
            "iliskili_modul": forms.Select(attrs={"class": "dk-input"}),
            "notlar": forms.Textarea(attrs={"class": "dk-input", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        from django.contrib.auth.models import User

        super().__init__(*args, **kwargs)
        self.fields["sorumlu"].queryset = User.objects.filter(
            personel_profili__aktif=True
        ).order_by("personel_profili__ad_soyad")


class DisiplinKurulKararDurumForm(forms.Form):
    durum = forms.ChoiceField(
        choices=DisiplinKurulKarar.Durum.choices,
        label="Durum",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    not_metni = forms.CharField(
        label="Takip notu",
        required=False,
        widget=forms.Textarea(attrs={"class": "dk-input", "rows": 2}),
    )


class DisiplinKurulRaporForm(forms.Form):
    talebe = forms.ModelChoiceField(
        queryset=Talebe.objects.none(),
        required=False,
        label="Öğrenci",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    kurul_turu = forms.ChoiceField(
        choices=[("", "Tümü")] + list(DisiplinKurulu.KurulTuru.choices),
        required=False,
        label="Kurul türü",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    kategori = forms.ChoiceField(
        choices=[("", "Tümü")] + list(DisiplinKurulKarar.Kategori.choices),
        required=False,
        label="Kategori",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    durum = forms.ChoiceField(
        choices=[("", "Tümü")] + list(DisiplinKurulKarar.Durum.choices),
        required=False,
        label="Durum",
        widget=forms.Select(attrs={"class": "dk-input"}),
    )
    tarih_bas = forms.DateField(
        required=False,
        label="Başlangıç",
        widget=forms.DateInput(attrs={"type": "date", "class": "dk-input"}),
    )
    tarih_bit = forms.DateField(
        required=False,
        label="Bitiş",
        widget=forms.DateInput(attrs={"type": "date", "class": "dk-input"}),
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["talebe"].queryset = yetkili_talebeler(user).order_by("ad_soyad")
