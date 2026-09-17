"""Dijital Duyuru Ekranı — yönetim formları."""

from __future__ import annotations

from django import forms
from django.utils import timezone

from takip.ekran_models import (
    EkranAcilDuyuru,
    EkranCihaz,
    EkranKonumu,
    EkranMedya,
    EkranOynatmaListesi,
    EkranProje,
    EkranYayinPlani,
    TUVAL_GENISLIK,
    TUVAL_YUKSEKLIK,
)

TUVAL_SECENEKLERI = (
    (f"{TUVAL_GENISLIK}x{TUVAL_YUKSEKLIK}", "Yatay ekran · 1920 × 1080 (16:9)"),
    (f"{TUVAL_YUKSEKLIK}x{TUVAL_GENISLIK}", "Dikey ekran · 1080 × 1920 (9:16)"),
)


class TasarimForm(forms.ModelForm):
    tuval = forms.ChoiceField(
        choices=TUVAL_SECENEKLERI,
        label="Ekran biçimi",
        initial=TUVAL_SECENEKLERI[0][0],
        help_text="Sonradan değiştirilebilir; öğe konumları orantılı korunur.",
    )

    class Meta:
        model = EkranProje
        fields = ["ad", "aciklama"]
        labels = {"ad": "Tasarım adı", "aciklama": "Açıklama"}
        widgets = {
            "ad": forms.TextInput(attrs={"placeholder": "Örn. Giriş Kat Günlük Yayın"}),
            "aciklama": forms.TextInput(attrs={"placeholder": "İsteğe bağlı kısa açıklama"}),
        }

    def kaydet(self, kullanici=None) -> EkranProje:
        proje = super().save(commit=False)
        genislik, _, yukseklik = self.cleaned_data["tuval"].partition("x")
        proje.tuval_genislik = int(genislik)
        proje.tuval_yukseklik = int(yukseklik)
        if kullanici and kullanici.is_authenticated:
            proje.olusturan = kullanici
            proje.son_duzenleyen = kullanici
        proje.save()
        return proje


class KonumForm(forms.ModelForm):
    class Meta:
        model = EkranKonumu
        fields = ["ad", "aciklama", "sira", "aktif"]
        labels = {"ad": "Konum adı", "aciklama": "Açıklama", "sira": "Sıra", "aktif": "Aktif"}
        widgets = {"ad": forms.TextInput(attrs={"placeholder": "Örn. Giriş Katı"})}


class CihazEslestirmeForm(forms.Form):
    kod = forms.CharField(
        label="Ekranda görünen kod",
        max_length=12,
        widget=forms.TextInput(
            attrs={"placeholder": "ÖRN. K7M2P4", "autocapitalize": "characters", "autocomplete": "off"}
        ),
    )
    ad = forms.CharField(label="Ekran adı", max_length=120)
    konum = forms.ModelChoiceField(
        queryset=EkranKonumu.objects.filter(aktif=True),
        label="Kat / konum",
        required=False,
        empty_label="Konum seçilmedi",
    )

    def temiz_kod(self) -> str:
        return (self.cleaned_data.get("kod") or "").strip().upper()

    def clean_kod(self) -> str:
        kod = (self.cleaned_data.get("kod") or "").strip().upper()
        if not kod:
            raise forms.ValidationError("Kodu girin.")

        cihaz = EkranCihaz.objects.filter(
            eslestirme_kodu=kod,
            durum=EkranCihaz.Durum.BEKLIYOR,
        ).first()
        if cihaz is None:
            raise forms.ValidationError(
                "Bu kod bulunamadı. Televizyondaki kodu kontrol edin — "
                "kodun süresi dolmuşsa ekran birkaç saniye içinde yenisini gösterir."
            )
        if not cihaz.kod_gecerli_mi:
            raise forms.ValidationError(
                "Bu kodun süresi dolmuş. Televizyon birkaç saniye içinde yeni kod gösterecek."
            )
        self.cihaz = cihaz
        return kod


class CihazDuzenleForm(forms.ModelForm):
    class Meta:
        model = EkranCihaz
        fields = ["ad", "konum", "durum", "notlar"]
        labels = {"ad": "Ekran adı", "konum": "Kat / konum", "durum": "Durum", "notlar": "Notlar"}
        widgets = {"notlar": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["konum"].queryset = EkranKonumu.objects.filter(aktif=True)
        self.fields["konum"].empty_label = "Konum seçilmedi"
        # Eşleştirme bekleyen cihaz panelden "aktif" yapılmaz; eşleştirme
        # akışı bunu kendisi yapar.
        self.fields["durum"].choices = [
            (deger, etiket)
            for deger, etiket in EkranCihaz.Durum.choices
            if deger != EkranCihaz.Durum.BEKLIYOR
        ]


class OynatmaListesiForm(forms.ModelForm):
    class Meta:
        model = EkranOynatmaListesi
        fields = ["ad", "aciklama", "donguye_al", "aktif"]
        labels = {
            "ad": "Liste adı",
            "aciklama": "Açıklama",
            "donguye_al": "Bitince başa dön",
            "aktif": "Aktif",
        }
        widgets = {"ad": forms.TextInput(attrs={"placeholder": "Örn. Normal Gün Yayını"})}


class YayinPlaniForm(forms.ModelForm):
    gun_secimi = forms.MultipleChoiceField(
        choices=EkranYayinPlani.GUN_ADLARI,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Haftanın günleri",
        help_text="Hiçbiri seçilmezse her gün yayınlanır.",
    )
    hedef_konumlar = forms.ModelMultipleChoiceField(
        queryset=EkranKonumu.objects.filter(aktif=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Katlar",
    )
    hedef_cihazlar = forms.ModelMultipleChoiceField(
        queryset=EkranCihaz.objects.filter(durum=EkranCihaz.Durum.AKTIF),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Tek tek ekranlar",
    )

    class Meta:
        model = EkranYayinPlani
        fields = [
            "ad",
            "liste",
            "baslangic_tarih",
            "bitis_tarih",
            "baslangic_saat",
            "bitis_saat",
            "oncelik",
            "tum_ekranlar",
        ]
        labels = {
            "ad": "Yayın adı",
            "liste": "Oynatma listesi",
            "baslangic_tarih": "Başlangıç tarihi",
            "bitis_tarih": "Bitiş tarihi",
            "baslangic_saat": "Başlangıç saati",
            "bitis_saat": "Bitiş saati",
            "oncelik": "Öncelik",
            "tum_ekranlar": "Tüm ekranlarda yayınla",
        }
        widgets = {
            "baslangic_tarih": forms.DateInput(attrs={"type": "date"}),
            "bitis_tarih": forms.DateInput(attrs={"type": "date"}),
            "baslangic_saat": forms.TimeInput(attrs={"type": "time"}),
            "bitis_saat": forms.TimeInput(attrs={"type": "time"}),
        }
        help_texts = {
            "oncelik": "Aynı saate denk gelen yayınlarda sayısı büyük olan ekrana çıkar.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["liste"].queryset = EkranOynatmaListesi.objects.filter(aktif=True)
        if self.instance.pk:
            self.fields["gun_secimi"].initial = [str(g) for g in (self.instance.gunler or [])]
            self.fields["hedef_konumlar"].initial = EkranKonumu.objects.filter(
                yayin_hedefleri__plan=self.instance
            )
            self.fields["hedef_cihazlar"].initial = EkranCihaz.objects.filter(
                yayin_hedefleri__plan=self.instance
            )

    def clean(self):
        temiz = super().clean()
        bas, bit = temiz.get("baslangic_tarih"), temiz.get("bitis_tarih")
        if bas and bit and bit < bas:
            self.add_error("bitis_tarih", "Bitiş tarihi başlangıçtan önce olamaz.")

        if not temiz.get("tum_ekranlar"):
            if not temiz.get("hedef_konumlar") and not temiz.get("hedef_cihazlar"):
                raise forms.ValidationError(
                    "Yayının nereye gideceğini seçin: tüm ekranlar, en az bir kat ya da en az bir ekran."
                )
        return temiz


class AcilDuyuruForm(forms.ModelForm):
    hedef_konumlar = forms.ModelMultipleChoiceField(
        queryset=EkranKonumu.objects.filter(aktif=True),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Katlar",
    )
    hedef_cihazlar = forms.ModelMultipleChoiceField(
        queryset=EkranCihaz.objects.filter(durum=EkranCihaz.Durum.AKTIF),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Ekranlar",
    )

    class Meta:
        model = EkranAcilDuyuru
        fields = ["baslik", "mesaj", "ton", "gorsel", "video", "sesli_uyari", "bitis", "tum_ekranlar"]
        labels = {
            "baslik": "Başlık",
            "mesaj": "Açıklama",
            "ton": "Görünüm",
            "gorsel": "Görsel",
            "video": "Video",
            "sesli_uyari": "Sesli uyarı çal",
            "bitis": "Otomatik kapanma zamanı",
            "tum_ekranlar": "Tüm ekranlarda göster",
        }
        widgets = {
            "mesaj": forms.Textarea(attrs={"rows": 3}),
            "bitis": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }
        help_texts = {"bitis": "Boş bırakılırsa elle kapatılana kadar yayında kalır."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["gorsel"].queryset = EkranMedya.objects.filter(tur=EkranMedya.Tur.GORSEL)
        self.fields["video"].queryset = EkranMedya.objects.filter(tur=EkranMedya.Tur.VIDEO)
        self.fields["gorsel"].empty_label = "Görsel yok"
        self.fields["video"].empty_label = "Video yok"

    def clean(self):
        temiz = super().clean()
        bitis = temiz.get("bitis")
        if bitis and bitis <= timezone.now():
            self.add_error("bitis", "Kapanma zamanı gelecekte olmalı.")
        if not temiz.get("tum_ekranlar"):
            if not temiz.get("hedef_konumlar") and not temiz.get("hedef_cihazlar"):
                raise forms.ValidationError(
                    "Acil duyurunun nereye gideceğini seçin: tüm ekranlar, kat ya da ekran."
                )
        return temiz
