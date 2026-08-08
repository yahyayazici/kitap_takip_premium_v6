from django import forms
from django.contrib import admin
from django.contrib.auth.models import User
from django.db import transaction

from config.branding import PANEL_NAME, PANEL_SHORT

from .models import (
    Duyuru,
    EtutHocasi,
    ImamMuezzinAtama,
    ImamMuezzinListesi,
    Kitap,
    KitapSinavi,
    OkumaKaydi,
    PersonelProfili,
    ProgramPlan,
    ProgramSatir,
    Sinav,
    SinavSonucu,
    SinifSube,
    Talebe,
    TemizlikAlani,
    TemizlikAtama,
    TemizlikListesi,
    YemekciAtama,
    YemekciListesi,
    YemekOgun,
    Zimmet,
    Rol,
    YetkiModul,
    VeliKisi,
    EgitimYili,
    Brans,
    Ders,
    DiniDersSeviyesi,
    KttSinav,
    KttSonucu,
    GunlukSoruKaydi,
    GunlukSoruDersSatiri,
    MudahaleTuru,
    AkademikMudahale,
    DenemeSinavi,
    DenemeSonucu,
    DenemeBransSonucu,
    DenemeEslestirmeAlias,
    EtutHaftaPlani,
    EtutPlanFaaliyet,
)


admin.site.site_header = f"{PANEL_SHORT} · Yönetim Merkezi"
admin.site.site_title = PANEL_SHORT
admin.site.index_title = "Sistem Yönetimi"


# =========================================================
# PERSONEL PROFİLLERİ
# =========================================================

@admin.register(PersonelProfili)
class PersonelProfiliAdmin(admin.ModelAdmin):
    list_display = (
        "ad_soyad",
        "ana_rol",
        "kullanici_adi_goster",
        "aktif",
    )
    list_filter = ("ana_rol", "aktif")
    search_fields = ("ad_soyad", "user__username")
    ordering = ("ad_soyad",)

    @admin.display(description="Kullanıcı adı")
    def kullanici_adi_goster(self, obj):
        return obj.user.username


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
            "sorumlu_sinif_subeler": forms.CheckboxSelectMultiple(
                attrs={"class": "choice-chip-grid"}
            ),
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
            "dini_ders_hocasi",
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
        self.fields["dini_ders_hocasi"].queryset = (
            EtutHocasi.objects.filter(aktif=True)
            .prefetch_related("sorumlu_sinif_subeler")
            .order_by("ad_soyad")
        )


# =========================================================
# PROGRAMLAR
# =========================================================

class ProgramSatirInline(admin.TabularInline):
    model = ProgramSatir
    extra = 1


@admin.register(ProgramPlan)
class ProgramPlanAdmin(admin.ModelAdmin):
    list_display = ("ad", "baslangic_tarihi", "bitis_tarihi", "aktif")
    list_filter = ("aktif",)
    search_fields = ("ad",)
    inlines = [ProgramSatirInline]


# =========================================================
# İMAM / MÜEZZİN
# =========================================================

class ImamMuezzinAtamaInline(admin.TabularInline):
    model = ImamMuezzinAtama
    extra = 0
    autocomplete_fields = ("imam", "muezzin")


@admin.register(ImamMuezzinListesi)
class ImamMuezzinListesiAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "baslangic_tarihi",
        "bitis_tarihi",
        "aktif",
        "cumartesi_dahil",
        "pazar_dahil",
    )
    list_filter = ("aktif", "cumartesi_dahil", "pazar_dahil")
    search_fields = ("ad",)
    filter_horizontal = ("talebe_havuzu",)
    inlines = [ImamMuezzinAtamaInline]


@admin.register(ImamMuezzinAtama)
class ImamMuezzinAtamaAdmin(admin.ModelAdmin):
    list_display = ("liste", "tarih", "imam", "muezzin", "manuel_duzenlendi")
    list_filter = ("liste", "manuel_duzenlendi")
    search_fields = ("liste__ad", "imam__ad_soyad", "muezzin__ad_soyad")
    autocomplete_fields = ("imam", "muezzin")


# =========================================================
# TEMİZLİK
# =========================================================

class TemizlikAtamaInline(admin.TabularInline):
    model = TemizlikAtama
    extra = 0
    autocomplete_fields = ("talebe",)


@admin.register(TemizlikAlani)
class TemizlikAlaniAdmin(admin.ModelAdmin):
    list_display = ("ad", "sira", "aktif")
    list_filter = ("aktif",)
    search_fields = ("ad",)
    ordering = ("sira", "ad")


@admin.register(TemizlikListesi)
class TemizlikListesiAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "baslangic_tarihi",
        "bitis_tarihi",
        "aktif",
    )
    list_filter = ("aktif",)
    search_fields = ("ad",)
    filter_horizontal = ("alanlar", "talebe_havuzu")
    inlines = [TemizlikAtamaInline]


@admin.register(TemizlikAtama)
class TemizlikAtamaAdmin(admin.ModelAdmin):
    list_display = ("liste", "tarih", "alan", "talebe", "manuel_duzenlendi")
    list_filter = ("liste", "manuel_duzenlendi", "alan")
    search_fields = ("liste__ad", "alan__ad", "talebe__ad_soyad")
    autocomplete_fields = ("talebe",)


# =========================================================
# YEMEKÇİLİK
# =========================================================

class YemekciAtamaInline(admin.TabularInline):
    model = YemekciAtama
    extra = 0
    autocomplete_fields = ("talebe", "yardimci")


@admin.register(YemekOgun)
class YemekOgunAdmin(admin.ModelAdmin):
    list_display = ("ad", "sira", "aktif")
    list_filter = ("aktif",)
    search_fields = ("ad",)
    ordering = ("sira", "ad")


@admin.register(YemekciListesi)
class YemekciListesiAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "baslangic_tarihi",
        "bitis_tarihi",
        "aktif",
    )
    list_filter = ("aktif",)
    search_fields = ("ad",)
    filter_horizontal = ("ogunler", "talebe_havuzu")
    inlines = [YemekciAtamaInline]


@admin.register(YemekciAtama)
class YemekciAtamaAdmin(admin.ModelAdmin):
    list_display = (
        "liste",
        "tarih",
        "ogun",
        "talebe",
        "yardimci",
        "manuel_duzenlendi",
    )
    list_filter = ("liste", "manuel_duzenlendi", "ogun")
    search_fields = (
        "liste__ad",
        "ogun__ad",
        "talebe__ad_soyad",
        "yardimci__ad_soyad",
    )
    autocomplete_fields = ("talebe", "yardimci")


# =========================================================
# DUYURULAR
# =========================================================

@admin.register(Duyuru)
class DuyuruAdmin(admin.ModelAdmin):
    list_display = (
        "sira",
        "baslik",
        "kategori",
        "hedef_kitle",
        "baslangic",
        "bitis",
        "aktif",
    )
    list_filter = ("kategori", "hedef_kitle", "aktif", "ton")
    search_fields = ("baslik", "ozet")
    ordering = ("sira", "-baslangic")


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
        "dini_ders_hocasi",
        "aktif",
    )

    list_filter = (
        "sinif_sube",
        "etut_hocasi",
        "dini_ders_hocasi",
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
                    "dini_ders_hocasi",
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


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ("ad", "slug", "aktif", "sistem_rolu", "sira")
    search_fields = ("ad", "slug")
    ordering = ("sira", "ad")


@admin.register(YetkiModul)
class YetkiModulAdmin(admin.ModelAdmin):
    list_display = ("ad", "kod", "sira", "aktif")
    ordering = ("sira",)


@admin.register(EgitimYili)
class EgitimYiliAdmin(admin.ModelAdmin):
    list_display = ("ad", "baslangic", "bitis", "aktif")


@admin.register(Brans)
class BransAdmin(admin.ModelAdmin):
    list_display = ("ad", "sira", "aktif")


@admin.register(Ders)
class DersAdmin(admin.ModelAdmin):
    list_display = ("ad", "brans", "sira", "aktif")
    list_filter = ("brans",)


@admin.register(DiniDersSeviyesi)
class DiniDersSeviyesiAdmin(admin.ModelAdmin):
    list_display = ("ad", "sira", "aktif")
    filter_horizontal = ("hocalar",)


from takip.dini_ders_takip_models import (  # noqa: E402
    DiniDersKonu,
    DiniDersKonuKaydi,
    DiniDersTakipAlani,
)


@admin.register(DiniDersTakipAlani)
class DiniDersTakipAlaniAdmin(admin.ModelAdmin):
    list_display = ("ad", "sira", "aktif")


@admin.register(DiniDersKonu)
class DiniDersKonuAdmin(admin.ModelAdmin):
    list_display = ("ad", "alan", "seviye", "sira", "aktif")
    list_filter = ("alan", "seviye", "aktif")


@admin.register(DiniDersKonuKaydi)
class DiniDersKonuKaydiAdmin(admin.ModelAdmin):
    list_display = ("talebe", "konu", "tamamlandi", "guncellenme")
    list_filter = ("tamamlandi", "konu__alan")


@admin.register(VeliKisi)
class VeliKisiAdmin(admin.ModelAdmin):
    list_display = ("ad_soyad", "talebe", "yakinlik", "telefon", "birincil")
    list_filter = ("yakinlik", "birincil")
    search_fields = ("ad_soyad", "talebe__ad_soyad")


@admin.register(KttSinav)
class KttSinavAdmin(admin.ModelAdmin):
    list_display = (
        "ad",
        "ders",
        "sinif_seviyesi",
        "sinav_tarihi",
        "etut_hocasi",
        "veliye_goster",
        "aktif",
    )
    list_filter = ("sinif_seviyesi", "veliye_goster", "aktif")
    search_fields = ("ad", "etut_hocasi__ad_soyad")


@admin.register(KttSonucu)
class KttSonucuAdmin(admin.ModelAdmin):
    list_display = (
        "talebe",
        "ktt",
        "dogru",
        "yanlis",
        "bos",
        "net",
        "puan",
    )
    list_filter = ("ktt__ders",)
    search_fields = ("talebe__ad_soyad", "ktt__ad")


class GunlukSoruDersSatiriInline(admin.TabularInline):
    model = GunlukSoruDersSatiri
    extra = 0
    readonly_fields = ("net",)


@admin.register(GunlukSoruKaydi)
class GunlukSoruKaydiAdmin(admin.ModelAdmin):
    list_display = (
        "talebe",
        "tarih",
        "kitap_okunan_sayfa",
        "kaydeden",
        "guncellenme",
    )
    list_filter = ("tarih",)
    search_fields = ("talebe__ad_soyad",)
    inlines = [GunlukSoruDersSatiriInline]


@admin.register(MudahaleTuru)
class MudahaleTuruAdmin(admin.ModelAdmin):
    list_display = ("ad", "ikon", "renk", "sira", "aktif")
    list_filter = ("aktif",)


@admin.register(AkademikMudahale)
class AkademikMudahaleAdmin(admin.ModelAdmin):
    list_display = (
        "talebe",
        "tarih",
        "mudahale_turu",
        "ders",
        "konu",
        "sure_dakika",
        "olusturan",
    )
    list_filter = ("mudahale_turu", "tarih")
    search_fields = ("talebe__ad_soyad", "konu")


@admin.register(DenemeSinavi)
class DenemeSinaviAdmin(admin.ModelAdmin):
    list_display = ("ad", "sinav_tarihi", "sinif_seviyesi", "durum", "yukleyen")
    list_filter = ("durum", "sinif_seviyesi")


class DenemeBransSonucuInline(admin.TabularInline):
    model = DenemeBransSonucu
    extra = 0


@admin.register(DenemeSonucu)
class DenemeSonucuAdmin(admin.ModelAdmin):
    list_display = ("talebe", "deneme", "toplam_net", "puan")
    list_filter = ("deneme",)
    inlines = [DenemeBransSonucuInline]


@admin.register(DenemeEslestirmeAlias)
class DenemeEslestirmeAliasAdmin(admin.ModelAdmin):
    list_display = ("excel_adi", "talebe")
    search_fields = ("excel_adi", "talebe__ad_soyad")


class EtutPlanFaaliyetInline(admin.TabularInline):
    model = EtutPlanFaaliyet
    extra = 0


@admin.register(EtutHaftaPlani)
class EtutHaftaPlaniAdmin(admin.ModelAdmin):
    list_display = (
        "etut_hocasi",
        "hafta_baslangic",
        "hafta_bitis",
        "durum",
    )
    list_filter = ("durum",)
    inlines = [EtutPlanFaaliyetInline]