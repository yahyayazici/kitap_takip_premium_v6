"""
Local-only Responsive QA bootstrap.

- Applies pending migrations to the local SQLite DB (schema sync; no model edits).
- Ensures isolated QA users for personel / yönetim / öğretmen / veli / talebe.
- Refuses to run against non-SQLite / non-DEBUG environments.

Does not seed fake production students and does not change business logic.
Existing talebe rows are only linked (veli/talebe hesap); not deleted or rewritten.
"""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command
from django.db import connection

QA_PASSWORD_DEFAULT_ENV = "QA_PASSWORD"


def _env(*keys: str, default: str = "") -> str:
    for key in keys:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return default


class Command(BaseCommand):
    help = "Local QA bootstrap: migrate SQLite + ensure role-isolated QA users (DEBUG/sqlite only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=_env("QA_USERNAME", "QA_PERSONEL_USERNAME", default="qa_responsive_bot"),
        )
        parser.add_argument(
            "--password",
            default=_env("QA_PASSWORD", "QA_PERSONEL_PASSWORD"),
            help="If omitted, password is left unchanged for existing users; "
            "required when creating a new QA user.",
        )
        parser.add_argument(
            "--skip-migrate",
            action="store_true",
            help="Only ensure QA users; do not run migrate.",
        )
        parser.add_argument(
            "--skip-roles",
            action="store_true",
            help="Only ensure the staff bot; skip öğretmen/veli/talebe/yonetim fixtures.",
        )

    def handle(self, *args, **options):
        engine = connection.settings_dict.get("ENGINE", "")
        db_name = str(connection.settings_dict.get("NAME", ""))

        if not settings.DEBUG:
            raise SystemExit("Refusing qa_bootstrap_local: DEBUG must be True.")
        if "sqlite" not in engine:
            raise SystemExit(
                f"Refusing qa_bootstrap_local: expected sqlite, got {engine}."
            )
        if any(h in db_name.lower() for h in ("prod", "render", "postgres")):
            raise SystemExit(
                f"Refusing qa_bootstrap_local: suspicious DB NAME={db_name!r}."
            )

        self.stdout.write(f"DB: {engine} → {db_name}")

        if not options["skip_migrate"]:
            self.stdout.write("Running migrate (local SQLite only)...")
            call_command("migrate", interactive=False, verbosity=1)
            self.stdout.write(self.style.SUCCESS("migrate OK"))

        password = options["password"]
        staff = self._ensure_staff_bot(options["username"], password)
        if not options["skip_roles"]:
            if not password:
                password = _env(QA_PASSWORD_DEFAULT_ENV)
            if not password:
                raise SystemExit(
                    "Role fixtures require --password or QA_PASSWORD."
                )
            self._ensure_role_users(password)
            self._write_local_env(staff.username, password)

        self.stdout.write(
            "Next: start runserver, then cd qa/responsive && npm run auth && npm run qa:sprint5"
        )

    def _ensure_staff_bot(self, username: str, password: str):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        changed = created
        if not user.is_staff or not user.is_superuser or not user.is_active:
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            changed = True
        if password:
            user.set_password(password)
            changed = True
        elif created:
            raise SystemExit(
                "New QA user requires --password or QA_PASSWORD / QA_PERSONEL_PASSWORD."
            )
        if changed:
            user.save()
        self.stdout.write(
            self.style.SUCCESS(
                f"Staff QA user: {user.username} ({'created' if created else 'updated/existing'})"
            )
        )
        return user

    def _ensure_user(self, username: str, password: str, *, staff: bool, superuser: bool):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "is_staff": staff,
                "is_superuser": superuser,
                "is_active": True,
            },
        )
        dirty = created
        if user.is_staff != staff or user.is_superuser != superuser or not user.is_active:
            user.is_staff = staff
            user.is_superuser = superuser
            user.is_active = True
            dirty = True
        user.set_password(password)
        dirty = True
        if dirty:
            user.save()
        return user, created

    def _ensure_role_users(self, password: str):
        from takip.models import (
            EtutHocasi,
            PersonelProfili,
            Talebe,
            TalebeHesap,
            VeliHesap,
            VeliTalebeBaglantisi,
        )
        from takip.wave0_models import KullaniciRol, Rol, VeliKisi

        yonetim_name = _env("QA_YONETIM_USERNAME", default="qa_yonetim")
        ogretmen_name = _env("QA_OGRETMEN_USERNAME", default="qa_ogretmen")
        veli_name = _env("QA_VELI_USERNAME", default="qa_veli")
        talebe_name = _env("QA_TALEBE_USERNAME", default="qa_talebe")

        idareci_rol = Rol.objects.filter(slug="idareci", aktif=True).first()
        yonetim, y_created = self._ensure_user(
            yonetim_name, password, staff=True, superuser=False
        )
        profil, _ = PersonelProfili.objects.get_or_create(
            user=yonetim,
            defaults={
                "ad_soyad": "QA Yönetim",
                "ana_rol": PersonelProfili.Rol.IDARECI,
                "rol": idareci_rol,
                "aktif": True,
            },
        )
        if profil.ana_rol != PersonelProfili.Rol.IDARECI or not profil.aktif:
            profil.ana_rol = PersonelProfili.Rol.IDARECI
            profil.aktif = True
            if idareci_rol:
                profil.rol = idareci_rol
            profil.save()
        if idareci_rol:
            KullaniciRol.objects.get_or_create(
                user=yonetim,
                rol=idareci_rol,
                defaults={"birincil": True},
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Yönetim QA user: {yonetim.username} ({'created' if y_created else 'existing'})"
            )
        )

        ogretmen, o_created = self._ensure_user(
            ogretmen_name, password, staff=False, superuser=False
        )
        hoca, _ = EtutHocasi.objects.get_or_create(
            user=ogretmen,
            defaults={"ad_soyad": "QA Öğretmen", "aktif": True},
        )
        if not hoca.aktif:
            hoca.aktif = True
            hoca.save(update_fields=["aktif"])
        rehber_rol = Rol.objects.filter(slug="rehber_ogretmeni", aktif=True).first()
        if rehber_rol:
            KullaniciRol.objects.get_or_create(
                user=ogretmen,
                rol=rehber_rol,
                defaults={"birincil": False},
            )
        sinif = None
        from takip.models import SinifSube

        sinif = SinifSube.objects.filter(aktif=True).order_by("sinif", "sube").first()
        if sinif and not hoca.sorumlu_sinif_subeler.filter(pk=sinif.pk).exists():
            hoca.sorumlu_sinif_subeler.add(sinif)
        self.stdout.write(
            self.style.SUCCESS(
                f"Öğretmen QA user: {ogretmen.username} ({'created' if o_created else 'existing'})"
            )
        )

        veli_user, v_created = self._ensure_user(
            veli_name, password, staff=False, superuser=False
        )
        veli, _ = VeliHesap.objects.get_or_create(
            user=veli_user,
            defaults={"ad_soyad": "QA Veli", "aktif": True},
        )
        if not veli.aktif:
            veli.aktif = True
            veli.save(update_fields=["aktif"])
        talebe_for_veli = (
            Talebe.objects.filter(durum=Talebe.Durum.AKTIF)
            .order_by("id")
            .first()
        )
        if talebe_for_veli:
            VeliTalebeBaglantisi.objects.get_or_create(
                veli=veli,
                talebe=talebe_for_veli,
                defaults={"yakinlik": VeliKisi.Yakinlik.VELI},
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Veli QA user: {veli_user.username} ({'created' if v_created else 'existing'})"
            )
        )

        talebe_user, t_created = self._ensure_user(
            talebe_name, password, staff=False, superuser=False
        )
        talebe_for_panel = (
            Talebe.objects.filter(durum=Talebe.Durum.AKTIF)
            .exclude(pk=getattr(talebe_for_veli, "pk", 0))
            .filter(talebe_hesabi__isnull=True)
            .order_by("id")
            .first()
        )
        if talebe_for_panel is None:
            talebe_for_panel = (
                Talebe.objects.filter(durum=Talebe.Durum.AKTIF)
                .filter(talebe_hesabi__isnull=True)
                .order_by("id")
                .first()
            )
        if talebe_for_panel is None:
            raise SystemExit("No aktif talebe available to attach QA talebe hesabı.")
        TalebeHesap.objects.get_or_create(
            user=talebe_user,
            defaults={"talebe": talebe_for_panel, "aktif": True},
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Talebe QA user: {talebe_user.username} → {talebe_for_panel.ad_soyad} "
                f"({'created' if t_created else 'existing'})"
            )
        )

    def _write_local_env(self, staff_username: str, password: str):
        auth_dir = Path(settings.BASE_DIR) / "qa" / "responsive" / ".auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        env_path = auth_dir / "local.env"
        lines = {
            "BASE_URL": os.environ.get("BASE_URL") or "http://127.0.0.1:8000",
            "QA_USERNAME": staff_username,
            "QA_PASSWORD": password,
            "QA_PERSONEL_USERNAME": _env("QA_PERSONEL_USERNAME", default=staff_username),
            "QA_PERSONEL_PASSWORD": password,
            "QA_YONETIM_USERNAME": _env("QA_YONETIM_USERNAME", default="qa_yonetim"),
            "QA_YONETIM_PASSWORD": password,
            "QA_OGRETMEN_USERNAME": _env("QA_OGRETMEN_USERNAME", default="qa_ogretmen"),
            "QA_OGRETMEN_PASSWORD": password,
            "QA_VELI_USERNAME": _env("QA_VELI_USERNAME", default="qa_veli"),
            "QA_VELI_PASSWORD": password,
            "QA_TALEBE_USERNAME": _env("QA_TALEBE_USERNAME", default="qa_talebe"),
            "QA_TALEBE_PASSWORD": password,
        }
        existing = {}
        if env_path.exists():
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
                    continue
                key, _, val = raw.partition("=")
                existing[key.strip()] = val
        existing.update(lines)
        body = "\n".join(f"{k}={v}" for k, v in existing.items()) + "\n"
        env_path.write_text(body, encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote {env_path} (gitignored)"))
