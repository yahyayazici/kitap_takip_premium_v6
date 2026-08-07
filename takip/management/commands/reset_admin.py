"""Admin şifresini sıfırla — canlı ortam (Render) için."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "admin kullanıcısının şifresini sıfırlar."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default="Admin123!",
            help="Yeni şifre (varsayılan: Admin123!)",
        )
        parser.add_argument(
            "--username",
            default="admin",
            help="Kullanıcı adı (varsayılan: admin)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]

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
