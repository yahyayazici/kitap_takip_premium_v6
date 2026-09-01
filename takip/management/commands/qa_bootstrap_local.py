"""
Local-only Responsive QA bootstrap.

- Applies pending migrations to the local SQLite DB (schema sync; no model edits).
- Ensures a staff QA user exists for Playwright storageState login.
- Refuses to run against non-SQLite / non-DEBUG environments.

Does not seed fake production data and does not change business logic.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, call_command
from django.db import connection


class Command(BaseCommand):
    help = "Local QA bootstrap: migrate SQLite + ensure QA login user (DEBUG/sqlite only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.environ.get("QA_USERNAME")
            or os.environ.get("QA_PERSONEL_USERNAME")
            or "qa_responsive_bot",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("QA_PASSWORD")
            or os.environ.get("QA_PERSONEL_PASSWORD")
            or "",
            help="If omitted, password is left unchanged for existing users; "
            "required when creating a new QA user.",
        )
        parser.add_argument(
            "--skip-migrate",
            action="store_true",
            help="Only ensure QA user; do not run migrate.",
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
            # NAME for sqlite is a file path; still guard odd misconfig.
            raise SystemExit(
                f"Refusing qa_bootstrap_local: suspicious DB NAME={db_name!r}."
            )

        self.stdout.write(f"DB: {engine} → {db_name}")

        if not options["skip_migrate"]:
            self.stdout.write("Running migrate (local SQLite only)...")
            call_command("migrate", interactive=False, verbosity=1)
            self.stdout.write(self.style.SUCCESS("migrate OK"))

        username = options["username"]
        password = options["password"]
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
                f"QA user ready: {user.username} ({'created' if created else 'updated/existing'})"
            )
        )
        self.stdout.write(
            "Next: start runserver, then cd qa/responsive && npm run qa:smoke"
        )
