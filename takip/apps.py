from django.apps import AppConfig

class TakipConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "takip"
    verbose_name = "Kitap Takip Sistemi"

    def ready(self):
        # Sınav başvurusu hatırlatmaları: yalnızca gunicorn işçisinde çalışır
        # (migrate, test ve diğer yönetim komutlarında başlamaz).
        from takip.sinav_bildirim_service import zamanlayiciyi_baslat

        zamanlayiciyi_baslat()
