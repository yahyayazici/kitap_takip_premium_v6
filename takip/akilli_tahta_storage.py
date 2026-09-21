"""Akıllı Tahta modülünün medya deposu.

``ekran_storage.py`` ile aynı gerekçe ve desen: PDF/görsel/video hacmi
Cloudinary'nin ücretsiz sınırlarını aşar, bu yüzden dosyalar her zaman
dosya sisteminde durur (canlıda Render kalıcı diski). Konum ayarlardan
**her erişimde** okunur ki testlerdeki ``override_settings`` etkili olsun.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class AkilliTahtaDepolama(FileSystemStorage):
    @property
    def base_location(self):
        return self._value_or_setting(self._location, str(settings.AKILLI_TAHTA_MEDIA_ROOT))

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        if self._base_url is not None and not self._base_url.endswith("/"):
            self._base_url += "/"
        return self._value_or_setting(self._base_url, settings.AKILLI_TAHTA_MEDIA_URL)


def akilli_tahta_depolama() -> AkilliTahtaDepolama:
    """Alan tanımlarında ``storage=akilli_tahta_depolama`` olarak kullanılır."""
    return AkilliTahtaDepolama()
