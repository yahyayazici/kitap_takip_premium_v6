"""Admin şifresini sıfırla — canlı ortam (Render) için."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "admin kullanıcısının şifresini sıfırlar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="",
            help="Yeni şifre (zorunlu — güvenlik nedeniyle varsayılan yok).",
        )
        parser.add_argument(
            "--username",
            default="admin",
            help="Kullanıcı adı (varsayılan: admin)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

        if not password:
            raise CommandError(
                "--password zorunlu (güvenlik nedeniyle varsayılan şifre kaldırıldı)."
            )

        user, created = User.objects.get_or_create(username=username)
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        action = "oluşturuldu" if created else "güncellendi"
        self.stdout.write(
            self.style.SUCCESS(
                f"Kullanıcı '{username}' {action}. Yeni şifre ayarlandı."
            )
        )
