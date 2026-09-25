"""Ana sayfa karşılama sözü — tek satır. Metin boşsa bantta yer kaplamaz."""

from django.db import models


class KarsilamaSozu(models.Model):
    metin = models.TextField(blank=True, verbose_name="Söz")
    kaynak = models.CharField(
        max_length=160,
        blank=True,
        verbose_name="Kaynak",
        help_text="İsteğe bağlı. Hadis, kişi veya kitap adı.",
    )
    guncellenme = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Karşılama sözü"
        verbose_name_plural = "Karşılama sözü"

    def __str__(self) -> str:
        return (self.metin or "Karşılama sözü")[:80]
