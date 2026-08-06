from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.db import transaction

from .models import (
    EtutHocasi,
    Kitap,
    KitapSinavi,
    OkumaKaydi,
    Sinav,
    SinavSonucu,
    SinifSube,
    Talebe,
    Zimmet,
)


admin.site.site_header = "Çinili Saray Yönetim Merkezi"
admin.site.site_title = "Çinili Saray Yönetim"
admin.site.index_title = "Sistem Yönetimi"


# =========================================================
# ETÜT HOCASI FORMU
# User seçmek yerine kullanıcı adı ve şifre doğrudan girilir.
# =========================================================

class EtutHocasiAdminForm(forms.ModelForm):
    kullanici_adi = forms.CharField(
        label="Kullanıcı adı",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Örn. yahya.yazici",
                "autocomplete": "off",
            }
        ),
    )

    sifre = forms.CharField(
        label="Şifre",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Yeni personelde zorunludur",
                "autocomplete": "new-password",
            }
        ),
        help_text=(
            "Yeni personel eklerken zorunludur. "
            "Düzenlerken boş bırakırsanız şifre değişmez."
        ),
    )

    class Meta:
        model = EtutHocasi
        fields = [
            "ad_soyad",
            "sorumlu_sinif_subeler",
            "aktif",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={
                    "placeholder": "Personelin adını ve soyadını yazın",
                }
            ),
            "sorumlu_sinif_subeler": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sorumlu_sinif_subeler"].queryset = (
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif", "sube")
        )

        if self.instance and self.instance.pk:
            self.fields["kullanici_adi"].initial = (
                self.instance.user.username
            )

    def clean_kullanici_adi(self):
        kullanici_adi = (
            self.cleaned_data["kullanici_adi"]
            .strip()
            .lower()
        )

        sorgu = User.objects.filter(
            username__iexact=kullanici_adi
        )

        if self.instance and self.instance.pk:
            sorgu = sorgu.exclude(
                pk=self.instance.user_id
            )

        if sorgu.exists():
            raise forms.ValidationError(
                "Bu kullanıcı adı zaten kullanılıyor."
            )

        return kullanici_adi

    def clean_sifre(self):
        sifre = self.cleaned_data.get("sifre", "")

        if not self.instance.pk and not sifre:
            raise forms.ValidationError(
                "Yeni personel için şifre zorunludur."
            )

        if sifre and len(sifre) < 8:
            raise forms.ValidationError(
                "Şifre en az 8 karakter olmalıdır."
            )

        return sifre

    @transaction.atomic
    def save(self, commit=True):
        personel = super().save(commit=False)

        kullanici_adi = self.cleaned_data["kullanici_adi"]
        sifre = self.cleaned_data.get("sifre")

        if personel.pk:
            user = personel.user
        else:
            user = User()

        user.username = kullanici_adi
        user.first_name = personel.ad_soyad
        user.is_staff = True
        user.is_active = personel.aktif

        if sifre:
            user.set_password(sifre)

        user.save()

        personel.user = user

        if commit:
            personel.save()
            self.save_m2m()

        return personel


# =========================================================
# TALEBE FORMU
# =========================================================

class TalebeAdminForm(forms.ModelForm):
    class Meta:
        model = Talebe
        fields = [
            "ad_soyad",
            "talebe_no",
            "sinif_sube",
            "etut_hocasi",
            "aktif",
        ]
        widgets = {
            "ad_soyad": forms.TextInput(
                attrs={
                    "placeholder": "Talebenin adını ve soyadını yazın",
                }
            ),
            "talebe_no": forms.TextInput(
                attrs={
                    "placeholder": "Talebe numarasını yazın",
                }
            ),
            "sinif_sube": forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["sinif_sube"].queryset = (
            SinifSube.objects.filter(aktif=True)
            .order_by("sinif", "sube")
        )

        self.fields["etut_hocasi"].queryset = (
            EtutHocasi.objects.filter(aktif=True)
            .prefetch_related("sorumlu_sinif_subeler")
            .order_by("ad_soyad")
        )


# =========================================================
# SINIF / ŞUBE
# =========================================================

@admin.register(SinifSube)
class SinifSubeAdmin(admin.ModelAdmin):
    list_display = (
        "sinif",
        "sube",
        "talebe_sayisi",
        "etut_hocasi_sayisi",
        "aktif",
    )

    list_filter = (
        "sinif",
        "sube",
        "aktif",
    )

    ordering = (
        "sinif",
        "sube",
    )

    list_editable = (
        "aktif",
    )

    fieldsets = (
        (
            "Sınıf ve Şube Bilgileri",
            {
                "fields": (
                    "sinif",
                    "sube",
                    "aktif",
                )
            },
        ),
    )

    @admin.display(description="Talebe sayısı")
    def talebe_sayisi(self, obj):
        return obj.talebeler.count()

    @admin.display(description="Etüt hocası sayısı")
    def etut_hocasi_sayisi(self, obj):
        return obj.etut_hocalari.count()


# =========================================================
# ETÜT HOCALARI
# =========================================================

@admin.register(EtutHocasi)
class EtutHocasiAdmin(admin.ModelAdmin):
    form = EtutHocasiAdminForm

    list_display = (
        "ad_soyad",
        "kullanici_adi_goster",
        "sorumlu_gruplar_goster",
        "talebe_sayisi",
        "aktif",
    )

    list_filter = (
        "aktif",
        "sorumlu_sinif_subeler__sinif",
        "sorumlu_sinif_subeler__sube",
    )

    search_fields = (
        "ad_soyad",
        "user__username",
    )

    ordering = (
        "ad_soyad",
    )

    fieldsets = (
        (
            "Personel Bilgileri",
            {
                "fields": (
                    "ad_soyad",
                    "kullanici_adi",
                    "sifre",
                    "aktif",
                )
            },
        ),
        (
            "Sorumlu Olduğu Sınıf ve Şubeler",
            {
                "fields": (
                    "sorumlu_sinif_subeler",
                )
            },
        ),
    )

    @admin.display(description="Kullanıcı adı")
    def kullanici_adi_goster(self, obj):
        return obj.user.username

    @admin.display(description="Sorumlu sınıflar")
    def sorumlu_gruplar_goster(self, obj):
        return obj.sorumlu_gruplar

    @admin.display(description="Talebe sayısı")
    def talebe_sayisi(self, obj):
        return obj.talebeler.count()


# =========================================================
# TALEBELER
# =========================================================

@admin.register(Talebe)
class TalebeAdmin(admin.ModelAdmin):
    form = TalebeAdminForm

    list_display = (
        "talebe_no",
        "ad_soyad",
        "sinif_sube_goster",
        "etut_hocasi",
        "aktif",
    )

    list_filter = (
        "sinif_sube",
        "etut_hocasi",
        "aktif",
    )

    search_fields = (
        "talebe_no",
        "ad_soyad",
        "etut_hocasi__ad_soyad",
    )

    ordering = (
        "sinif",
        "sube",
        "ad_soyad",
    )

    fieldsets = (
        (
            "Talebe Bilgileri",
            {
                "fields": (
                    "ad_soyad",
                    "talebe_no",
                    "sinif_sube",
                    "etut_hocasi",
                    "aktif",
                )
            },
        ),
    )

    @admin.display(description="Sınıf / Şube")
    def sinif_sube_goster(self, obj):
        if obj.sinif_sube:
            return obj.sinif_sube

        if obj.sube:
            return f"{obj.sinif}/{obj.sube}"

        return obj.sinif or "—"


# =========================================================
# KİTAPLAR
# =========================================================

@admin.register(Kitap)
class KitapAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "yazar",
        "yayinevi",
        "toplam_sayfa",
        "sinif_seviyesi",
        "aktif",
    )

    list_filter = (
        "aktif",
        "sinif_seviyesi",
    )

    search_fields = (
        "ad",
        "yazar",
        "yayinevi",
    )

    ordering = (
        "ad",
    )


# =========================================================
# KİTAP ZİMMETLERİ
# =========================================================

@admin.register(Zimmet)
class ZimmetAdmin(admin.ModelAdmin):
    list_display = (
        "talebe",
        "kitap",
        "etut_hocasi",
        "zimmet_tarihi",
        "durum",
        "ilerleme_yuzdesi",
    )

    list_filter = (
        "durum",
        "zimmet_tarihi",
        "etut_hocasi",
    )

    search_fields = (
        "talebe__ad_soyad",
        "talebe__talebe_no",
        "kitap__ad",
    )

    autocomplete_fields = (
        "talebe",
        "kitap",
        "etut_hocasi",
    )


# =========================================================
# GÜNLÜK OKUMA
# =========================================================

@admin.register(OkumaKaydi)
class OkumaKaydiAdmin(admin.ModelAdmin):
    list_display = (
        "zimmet",
        "tarih",
        "son_sayfa",
        "okunan_sayfa",
    )

    list_filter = (
        "tarih",
    )

    search_fields = (
        "zimmet__talebe__ad_soyad",
        "zimmet__kitap__ad",
    )

    autocomplete_fields = (
        "zimmet",
    )


# =========================================================
# KİTAP SINAVLARI
# =========================================================

@admin.register(KitapSinavi)
class KitapSinaviAdmin(admin.ModelAdmin):
    list_display = (
        "zimmet",
        "tarih",
        "dogru",
        "yanlis",
        "bos",
        "puan",
    )

    list_filter = (
        "tarih",
    )

    search_fields = (
        "zimmet__talebe__ad_soyad",
        "zimmet__kitap__ad",
    )


# =========================================================
# SINAVLAR
# =========================================================

@admin.register(Sinav)
class SinavAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "kitap",
        "etut_hocasi",
        "soru_sayisi",
        "sinav_tarihi",
        "aktif",
    )

    list_filter = (
        "aktif",
        "sinav_tarihi",
        "etut_hocasi",
    )

    search_fields = (
        "ad",
        "kitap__ad",
        "etut_hocasi__ad_soyad",
    )

    autocomplete_fields = (
        "kitap",
        "etut_hocasi",
    )


# =========================================================
# SINAV SONUÇLARI
# =========================================================

@admin.register(SinavSonucu)
class SinavSonucuAdmin(admin.ModelAdmin):
    list_display = (
        "sinav",
        "talebe",
        "dogru",
        "yanlis",
        "bos",
        "puan",
    )

    list_filter = (
        "sinav",
        "talebe__sinif_sube",
    )

    search_fields = (
        "sinav__ad",
        "talebe__ad_soyad",
        "talebe__talebe_no",
    )

    autocomplete_fields = (
        "sinav",
        "talebe",
    )

    readonly_fields = (
        "puan",
        "kayit_tarihi",
        "guncellenme_tarihi",
    )