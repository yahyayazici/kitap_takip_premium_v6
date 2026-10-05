"""E-Kitap dosya deposu.

Dosyalar herkese açık bir URL'den **servis edilmez**; sayfa görselleri yalnızca
PIN doğrulanmış oturuma ``ekitap_views.sayfa_gorseli`` üzerinden verilir.
Canlıda ``EKITAP_MEDIA_ROOT`` Render kalıcı diskine ayarlanır (bkz. render.yaml).
Konum ayarlardan her erişimde okunur ki testlerdeki ``override_settings`` çalışsın.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class EKitapDepolama(FileSystemStorage):
    @property
    def base_location(self):
        return self._value_or_setting(self._location, str(settings.EKITAP_MEDIA_ROOT))

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        # Doğrudan URL yok; dosyalar yetki kontrollü görünümden servis edilir.
        return None


def ekitap_depolama() -> EKitapDepolama:
    return EKitapDepolama()
