"""Yönetim — rol ve yetki ekranları."""

from django import forms
from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from takip.models import (
    KullaniciRol,
    PersonelProfili,
    Rol,
    RolIslemYetki,
    RolModulErisim,
    YetkiIslem,
    YetkiModul,
)
from takip.permissions.service import can, clear_permission_cache

from .yonetim_views import yonetici_gerekli


class RolTanimForm(forms.ModelForm):
    class Meta:
        model = Rol
        fields = ["ad", "slug", "aciklama", "legacy_ana_rol", "sira", "aktif"]
        widgets = {
            "ad": forms.TextInput(attrs={"class": "cs-input"}),
            "slug": forms.TextInput(attrs={"class": "cs-input", "placeholder": "ornek-rol"}),
            "aciklama": forms.Textarea(attrs={"class": "cs-input", "rows": 3}),
            "legacy_ana_rol": forms.Select(attrs={"class": "cs-input"}),
            "sira": forms.NumberInput(attrs={"class": "cs-input", "min": 0}),
            "aktif": forms.CheckboxInput(attrs={"class": "cs-checkbox"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        self.fields["slug"].help_text = "Boş bırakılırsa addan otomatik üretilir."
        self.fields["legacy_ana_rol"].required = False
        self.fields["legacy_ana_rol"].help_text = (
            "Personel formundaki Ana Rol ile eşlemek için seçin (isteğe bağlı)."
        )
        self.fields["legacy_ana_rol"].widget = forms.Select(
            attrs={"class": "cs-input"},
            choices=[("", "— Yok —")] + list(PersonelProfili.Rol.choices),
        )
        self.fields["sira"].initial = self.fields["sira"].initial or 100
        self.fields["aktif"].initial = True

    def clean_slug(self):
        slug = (self.cleaned_data.get("slug") or "").strip()
        ad = (self.cleaned_data.get("ad") or "").strip()
        if not slug:
            slug = slugify(ad, allow_unicode=False) or slugify(ad) or "rol"
        slug = slug[:40]
        qs = Rol.objects.filter(slug=slug)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Bu kod zaten kullanılıyor.")
        return slug


def _personel_rbac_senkronize() -> int:
    """Personel ana_rol → RBAC Rol + birincil KullaniciRol (eksik bağları tamamlar)."""
    sayac = 0
    roller: dict[str, Rol] = {}
    for r in Rol.objects.filter(aktif=True):
        roller[r.slug] = r
        if r.legacy_ana_rol:
            roller[r.legacy_ana_rol] = r
    for personel in PersonelProfili.objects.select_related("user", "rol").filter(
        aktif=True, user__isnull=False
    ):
        hedef = roller.get(personel.ana_rol)
        if hedef is None:
            continue
        guncelle = False
        if personel.rol_id != hedef.id:
            personel.rol = hedef
            personel.save(update_fields=["rol"])
            guncelle = True
        kayit, created = KullaniciRol.objects.get_or_create(
            user=personel.user,
            rol=hedef,
            defaults={"birincil": True},
        )
        if created:
            guncelle = True
        if not kayit.birincil:
            KullaniciRol.objects.filter(user=personel.user, birincil=True).exclude(
                pk=kayit.pk
            ).update(birincil=False)
            kayit.birincil = True
            kayit.save(update_fields=["birincil"])
            guncelle = True
        if guncelle:
            sayac += 1
    if sayac:
        clear_permission_cache()
    return sayac


def _rol_izin_iskeleti(rol: Rol) -> None:
    """Yeni rol için tüm modüllerde boş erişim/izin satırları oluşturur."""
    for modul in YetkiModul.objects.filter(aktif=True):
        RolModulErisim.objects.get_or_create(
            rol=rol, modul=modul, defaults={"erisim": False}
        )
        for islem in modul.islemler.all():
            RolIslemYetki.objects.get_or_create(
                rol=rol, islem=islem, defaults={"izin": False}
            )


@yonetici_gerekli
def rol_listesi(request):
    if not can(request.user, "rbac", "view"):
        messages.error(request, "Rol yönetimi için yetkiniz yok.")
        return redirect("yonetim:dashboard")

    if request.method == "POST" and request.POST.get("action") == "varsayilan_yukle":
        if not can(request.user, "rbac", "edit"):
            messages.error(request, "Varsayılan rolleri yükleme yetkiniz yok.")
            return redirect("yonetim:rol_listesi")
        from takip.management.commands.seed_wave0 import (
            seed_modul_katalogu,
            seed_roller,
            sync_personel_roller,
        )

        with transaction.atomic():
            moduller = seed_modul_katalogu()
            roller = seed_roller(moduller)
            sync_personel_roller(roller)
        clear_permission_cache()
        messages.success(
            request,
            f"Varsayılan roller yüklendi ({len(roller)} rol). Yetkileri satırdan düzenleyebilirsiniz.",
        )
        return redirect("yonetim:rol_listesi")

    senkron = _personel_rbac_senkronize()
    if senkron:
        messages.info(
            request,
            f"{senkron} personelin rol bağları güncellendi (ana rol → yetki matrisi).",
        )

    roller = Rol.objects.filter(aktif=True).order_by("sira", "ad")
    return render(
        request,
        "yonetim/rol_listesi.html",
        {
            "roller": roller,
            "rbac_duzenleyebilir": can(request.user, "rbac", "edit"),
        },
    )


@yonetici_gerekli
def rol_ekle(request):
    if not can(request.user, "rbac", "edit"):
        messages.error(request, "Rol ekleme yetkiniz yok.")
        return redirect("yonetim:rol_listesi")

    form = RolTanimForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            rol = form.save(commit=False)
            rol.sistem_rolu = False
            rol.save()
            _rol_izin_iskeleti(rol)
        clear_permission_cache()
        messages.success(request, f"“{rol.ad}” eklendi. Şimdi yetkilerini seçin.")
        return redirect("yonetim:rol_duzenle", pk=rol.pk)

    return render(
        request,
        "yonetim/form.html",
        {
            "form": form,
            "sayfa_basligi": "Yeni Rol Tanımla",
            "sayfa_aciklama": "Rol adı ve kodunu girin; kayıttan sonra modül yetkilerini işaretlersiniz.",
            "geri_url": "yonetim:rol_listesi",
        },
    )


@yonetici_gerekli
def rol_duzenle(request, pk):
    if not can(request.user, "rbac", "edit"):
        messages.error(request, "Rol düzenleme yetkiniz yok.")
        return redirect("yonetim:rol_listesi")

    rol = get_object_or_404(Rol, pk=pk)
    moduller = (
        YetkiModul.objects.filter(aktif=True)
        .prefetch_related("islemler")
        .order_by("sira")
    )

    if request.method == "POST":
        for modul in moduller:
            erisim = request.POST.get(f"modul_{modul.kod}") == "on"
            RolModulErisim.objects.update_or_create(
                rol=rol,
                modul=modul,
                defaults={"erisim": erisim},
            )
            for islem in modul.islemler.all():
                izin = request.POST.get(f"islem_{modul.kod}_{islem.kod}") == "on"
                RolIslemYetki.objects.update_or_create(
                    rol=rol,
                    islem=islem,
                    defaults={"izin": izin},
                )

        clear_permission_cache()
        messages.success(request, f"{rol.ad} yetkileri güncellendi.")
        return redirect("yonetim:rol_listesi")

    # Modül kataloğu boşsa varsayılanları yükle (yetki satırları görünsün)
    if not moduller.exists():
        from takip.management.commands.seed_wave0 import seed_modul_katalogu

        seed_modul_katalogu()
        moduller = (
            YetkiModul.objects.filter(aktif=True)
            .prefetch_related("islemler")
            .order_by("sira")
        )

    modul_erisim = {
        e.modul_id: e.erisim
        for e in rol.modul_erisimleri.select_related("modul")
    }
    islem_yetki = {
        y.islem_id: y.izin
        for y in rol.islem_yetkileri.select_related("islem")
    }

    satirlar = []
    for modul in moduller:
        satirlar.append(
            {
                "modul": modul,
                "erisim": modul_erisim.get(modul.id, False),
                "islemler": [
                    {
                        "islem": islem,
                        "izin": islem_yetki.get(islem.id, False),
                    }
                    for islem in modul.islemler.all()
                ],
            }
        )

    return render(
        request,
        "yonetim/rol_duzenle.html",
        {
            "rol": rol,
            "satirlar": satirlar,
        },
    )
