"""Wave 0 seed — modül kataloğu, roller, varsayılan yetkiler, kernel demo verisi."""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from takip.models import (
    Brans,
    Ders,
    DiniDersSeviyesi,
    Donem,
    EgitimYili,
    KullaniciRol,
    PersonelProfili,
    Rol,
    RolIslemYetki,
    RolKapsam,
    RolModulErisim,
    YetkiIslem,
    YetkiModul,
)
from takip.permissions.registry import (
    ADMIN_ONLY_EDIT_MODULES,
    LEGACY_ROL_ETIKETLERI,
    LEGACY_ROL_MODULLER,
    LEGACY_TUM_TALEBE_ROLLER,
    MODUL_KATALOGU,
    STANDARD_ACTIONS,
)
from takip.permissions.service import clear_permission_cache
from takip.soru_takip_service import seed_soru_takip_dersleri
from takip.akademik_mudahale_service import seed_mudahale_turleri
from takip.dini_ders_mufredat import seed_dini_ders_mufredat
from takip.dini_ders_takip_service import seed_dini_ders_ornek_atamalar


def seed_modul_katalogu() -> dict[str, YetkiModul]:
    moduller: dict[str, YetkiModul] = {}
    for tanim in MODUL_KATALOGU:
        modul, _ = YetkiModul.objects.update_or_create(
            kod=tanim.kod,
            defaults={
                "ad": tanim.ad,
                "sira": tanim.sira,
                "aktif": True,
            },
        )
        for sira, (kod, ad) in enumerate(tanim.islemler, start=1):
            YetkiIslem.objects.update_or_create(
                modul=modul,
                kod=kod,
                defaults={"ad": ad, "sira": sira},
            )
        moduller[tanim.kod] = modul
    return moduller


def seed_roller(moduller: dict[str, YetkiModul]) -> dict[str, Rol]:
    roller: dict[str, Rol] = {}
    sira = 0
    for slug, ad in LEGACY_ROL_ETIKETLERI.items():
        sira += 10
        rol, _ = Rol.objects.update_or_create(
            slug=slug,
            defaults={
                "ad": ad,
                "legacy_ana_rol": slug,
                "sira": sira,
                "aktif": True,
                "sistem_rolu": slug in {"idareci", "ic_mesul"},
            },
        )
        roller[slug] = rol

        erisim_moduller = LEGACY_ROL_MODULLER.get(slug, frozenset())
        for modul_kod, modul in moduller.items():
            erisim = modul_kod in erisim_moduller
            RolModulErisim.objects.update_or_create(
                rol=rol,
                modul=modul,
                defaults={"erisim": erisim},
            )

            islemler = modul.islemler.all()
            for islem in islemler:
                izin = False
                if not erisim:
                    izin = False
                elif (
                    modul_kod in ADMIN_ONLY_EDIT_MODULES
                    and islem.kod in {"create", "edit", "delete"}
                ):
                    izin = slug in {"idareci", "ic_mesul"}
                elif modul_kod in ADMIN_ONLY_EDIT_MODULES and islem.kod in {
                    "export_pdf",
                    "export_excel",
                }:
                    izin = erisim
                elif modul_kod == "deneme" and islem.kod == "delete":
                    izin = False
                elif modul_kod == "deneme" and islem.kod in {"create", "edit"}:
                    izin = slug in {"idareci", "ic_mesul"}
                elif islem.kod == "view":
                    izin = True
                elif slug in {"idareci", "ic_mesul"} and modul_kod == "deneme":
                    izin = islem.kod in {
                        "view",
                        "create",
                        "edit",
                        "export_pdf",
                        "export_excel",
                    }
                elif slug in {"idareci", "ic_mesul"}:
                    izin = True
                elif slug == "egitim_mesul" and islem.kod != "delete":
                    izin = modul_kod not in {"rbac", "sistem_ayarlari"}
                elif slug in LEGACY_TUM_TALEBE_ROLLER and islem.kod in {
                    "create",
                    "edit",
                    "export_pdf",
                    "export_excel",
                }:
                    izin = True
                elif slug == "etut_mesul" and modul_kod in {
                    "egitim_kitap",
                    "gelisim_dosyasi",
                    "ktt",
                    "deneme",
                    "soru_takip",
                    "akademik_mudahale",
                    "etut_plani",
                    "dini_ders_takip",
                    "yazili_takip",
                }:
                    if modul_kod == "deneme":
                        izin = islem.kod == "view"
                    elif modul_kod == "etut_plani":
                        izin = islem.kod in {
                            "view",
                            "create",
                            "edit",
                            "delete",
                            "export_pdf",
                        }
                    elif modul_kod == "yazili_takip":
                        # Kamp/sınav tanımı admin; etüt kendi grubuna sonuç girer
                        izin = islem.kod in {
                            "view",
                            "edit",
                            "export_pdf",
                            "export_excel",
                        }
                    elif modul_kod == "dini_ders_takip":
                        izin = islem.kod in {
                            "view",
                            "edit",
                            "export_pdf",
                            "export_excel",
                        }
                    elif modul_kod == "namaz_yoklama":
                        izin = islem.kod in {
                            "view",
                            "create",
                            "edit",
                            "export_pdf",
                            "export_excel",
                        }
                    elif modul_kod == "akademik_mudahale":
                        izin = islem.kod in {
                            "view",
                            "create",
                            "edit",
                            "delete",
                            "export_pdf",
                            "export_excel",
                        }
                    elif modul_kod == "ktt":
                        izin = islem.kod in {
                            "view",
                            "create",
                            "edit",
                            "export_pdf",
                            "export_excel",
                        }
                    else:
                        izin = islem.kod in {"view", "create", "edit", "export_pdf"}

                elif slug == "rehber_ogretmeni":
                    if modul_kod == "rehberlik":
                        izin = islem.kod in {
                            "view",
                            "create",
                            "edit",
                            "export_pdf",
                        }
                    elif modul_kod in {"veli_iletisim", "veli_randevu"}:
                        izin = islem.kod in {"view", "create", "edit"}
                    elif modul_kod in {
                        "egitim_kitap",
                        "gelisim_dosyasi",
                        "raporlar",
                        "asistan",
                    }:
                        izin = islem.kod in {"view", "export_pdf"}

                RolIslemYetki.objects.update_or_create(
                    rol=rol,
                    islem=islem,
                    defaults={"izin": izin},
                )

        RolKapsam.objects.filter(rol=rol).delete()
        if slug in LEGACY_TUM_TALEBE_ROLLER:
            RolKapsam.objects.create(
                rol=rol,
                tip=RolKapsam.KapsamTipi.TUM,
                deger={},
            )
        else:
            RolKapsam.objects.create(
                rol=rol,
                tip=RolKapsam.KapsamTipi.ETUT_GRUBU,
                deger={},
            )

    return roller


def sync_personel_roller(roller: dict[str, Rol]) -> None:
    for profil in PersonelProfili.objects.select_related("user"):
        rol = roller.get(profil.ana_rol)
        if rol and profil.rol_id != rol.id:
            profil.rol = rol
            profil.save(update_fields=["rol"])

        if rol:
            KullaniciRol.objects.update_or_create(
                user=profil.user,
                rol=rol,
                defaults={"birincil": True},
            )


def seed_kernel_demo() -> None:
    yil, _ = EgitimYili.objects.get_or_create(
        ad="2025-2026",
        defaults={
            "baslangic": date(2025, 9, 1),
            "bitis": date(2026, 6, 30),
            "aktif": True,
        },
    )
    Donem.objects.get_or_create(
        egitim_yili=yil,
        ad="1. Dönem",
        defaults={
            "baslangic": date(2025, 9, 1),
            "bitis": date(2026, 1, 31),
            "aktif": True,
        },
    )

    branslar = [
        ("Türkçe", 1),
        ("Matematik", 2),
        ("Fen", 3),
        ("Sosyal", 4),
        ("Din", 5),
        ("Paragraf", 6),
    ]
    for ad, sira in branslar:
        Brans.objects.get_or_create(ad=ad, defaults={"sira": sira, "aktif": True})

    for seviye, sira in [
        ("Seviye 1", 1),
        ("Seviye 2", 2),
        ("Seviye 3", 3),
        ("Seviye 4", 4),
    ]:
        DiniDersSeviyesi.objects.get_or_create(
            ad=seviye,
            defaults={"sira": sira, "aktif": True},
        )

    turkce = Brans.objects.filter(ad="Türkçe").first()
    if turkce:
        Ders.objects.get_or_create(
            ad="Türkçe",
            defaults={"brans": turkce, "sira": 1, "aktif": True},
        )


class Command(BaseCommand):
    help = "Wave 0 — RBAC kataloğu, roller ve kernel demo verisini yükler."

    @transaction.atomic
    def handle(self, *args, **options):
        moduller = seed_modul_katalogu()
        roller = seed_roller(moduller)
        sync_personel_roller(roller)
        seed_kernel_demo()
        seed_soru_takip_dersleri()
        seed_mudahale_turleri()
        seed_dini_ders_mufredat()
        seed_dini_ders_ornek_atamalar()
        clear_permission_cache()

        self.stdout.write(
            self.style.SUCCESS(
                f"Wave 0 seed tamam: {len(moduller)} modül, {len(roller)} rol."
            )
        )
