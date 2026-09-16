"""Web Push abonelik kaydı — tarayıcı/telefon, bildirime izin verince burada saklanır."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class PushAbonelik(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_abonelikleri",
        verbose_name="Kullanıcı",
    )
    endpoint = models.URLField(max_length=500, unique=True, verbose_name="Endpoint")
    p256dh = models.CharField(max_length=255, verbose_name="p256dh anahtarı")
    auth = models.CharField(max_length=255, verbose_name="Auth anahtarı")
    user_agent = models.CharField(max_length=255, blank=True, verbose_name="Cihaz/Tarayıcı")
    olusturulma = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Push aboneliği"
        verbose_name_plural = "Push abonelikleri"
        ordering = ["-olusturulma"]
        indexes = [
            models.Index(fields=["user"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.endpoint[:40]}…"
