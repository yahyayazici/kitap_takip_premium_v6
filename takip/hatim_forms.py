"""Hatim Takip Merkezi formları."""

from __future__ import annotations

from django import forms

from takip.hatim_models import HatimProgrami
from takip.hatim_service import personel_listesi_secenekleri
from takip.models import PersonelProfili


class HatimProgramiForm(forms.ModelForm):
    katilimcilar = forms.ModelMultipleChoiceField(
        queryset=PersonelProfili.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Katılımcılar",
        help_text="Personel hatmi için aktif personel listesinden seçin.",
    )

    class Meta:
        model = HatimProgrami
        fields = (
            "ad",
            "tur",
            "aciklama",
            "baslangic_tarihi",
            "program_bitis_tarihi",
            "son_tamamlama_saati",
            "kisi_basina_cuz",
            "cuz_dagitim_yontemi",
            "tekrar_turu",
            "tekrar_gun_araligi",
            "cuz_donem_stratejisi",
            "hafta_sonu_dahil",
            "yeni_donem_otomatik",
            "eksik_aktar",
            "gecikmis_sakla",
            "yarim_son_donem",
            "hatirlatma_program_baslangic",
            "hatirlatma_yeni_donem",
            "hatirlatma_bitis_12h",
            "hatirlatma_bitis_2h",
            "hatirlatma_sure_gecti",
            "hatirlatma_program_tamamlandi",
        )
        widgets = {
            "baslangic_tarihi": forms.DateInput(attrs={"type": "date"}),
            "program_bitis_tarihi": forms.DateInput(attrs={"type": "date"}),
            "son_tamamlama_saati": forms.TimeInput(attrs={"type": "time"}),
            "aciklama": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["katilimcilar"].queryset = personel_listesi_secenekleri()
        self.fields["program_bitis_tarihi"].required = False
        for name in self.fields:
            css = "hatim-input"
            if isinstance(self.fields[name].widget, forms.CheckboxInput):
                continue
            self.fields[name].widget.attrs.setdefault("class", css)

    def clean(self):
        cleaned = super().clean()
        bas = cleaned.get("baslangic_tarihi")
        bit = cleaned.get("program_bitis_tarihi")
        if bas and bit and bit < bas:
            self.add_error(
                "program_bitis_tarihi",
                "Program bitişi başlangıçtan önce olamaz.",
            )
        tur = cleaned.get("tur")
        katilimcilar = cleaned.get("katilimcilar")
        if tur == HatimProgrami.Tur.PERSONEL and not self.instance.pk:
            if not katilimcilar:
                self.add_error("katilimcilar", "En az bir katılımcı seçin.")
        return cleaned


class HatimProgramTamamlaForm(forms.Form):
    dua_yapildi = forms.BooleanField(
        required=False,
        label="Dua yapıldı olarak işaretle",
    )
    onay = forms.BooleanField(
        required=True,
        label="Programı tamamlamak istediğimi onaylıyorum",
    )


class CuzManuelAtamaForm(forms.Form):
    katilimci_id = forms.IntegerField(widget=forms.HiddenInput)
    cuz_baslangic = forms.IntegerField(min_value=1, max_value=30, label="Başlangıç cüz")
    cuz_bitis = forms.IntegerField(min_value=1, max_value=30, label="Bitiş cüz")
