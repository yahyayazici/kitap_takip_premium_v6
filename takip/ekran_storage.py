"""Ekran modülünün medya deposu.

Neden ayrı bir depo?
--------------------
Projenin varsayılan deposu ``CLOUDINARY_URL`` tanımlıysa Cloudinary'dir.
Cloudinary ücretsiz planında video dosyası 100 MB ile sınırlıdır ve video
bant genişliği krediyi hızla tüketir — televizyonda gün boyu video döndüren
bu modül için uygun değildir.

Bu yüzden ekran modülünün dosyaları her zaman **dosya sisteminde** durur
(canlıda Render'a bağlanan kalıcı disk). Mevcut modüllerin deposuna
dokunulmaz: duyuru görselleri vb. nereye gidiyorsa oraya gitmeye devam eder.

``EKRAN_MEDIA_ROOT`` tanımlı değilse ``MEDIA_ROOT`` altındaki
``ekran-medya`` klasörü kullanılır; yerel geliştirmede ayar gerekmez.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class EkranDepolama(FileSystemStorage):
    """Konumunu ayarlardan **her erişimde** okuyan dosya deposu.

    Django, alan tanımındaki çağrılabilir depoyu sınıf yüklenirken bir kez
    çalıştırır; ``FileSystemStorage`` da yolunu ``cached_property`` ile
    dondurur. Bu ikisi birleşince yol, ilk import anında sabitlenirdi ve
    testlerdeki ``override_settings`` etkisiz kalırdı — testler geliştiricinin
    gerçek medya klasörüne dosya yazardı. Aşağıdaki üç özellik önbelleği
    kaldırıp değeri anlık okur.
    """

    @property
    def base_location(self):
        return self._value_or_setting(self._location, str(settings.EKRAN_MEDIA_ROOT))

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    @property
    def base_url(self):
        if self._base_url is not None and not self._base_url.endswith("/"):
            self._base_url += "/"
        return self._value_or_setting(self._base_url, settings.EKRAN_MEDIA_URL)


def ekran_depolama() -> EkranDepolama:
    """Alan tanımlarında ``storage=ekran_depolama`` olarak kullanılır.

    Çağrılabilir olması kasıtlı: Django migration'lara depo nesnesini gömmek
    yerine bu fonksiyona başvurur; sunucudaki yol değişince migration'ları
    yeniden yazmak gerekmez.
    """
    return EkranDepolama()
