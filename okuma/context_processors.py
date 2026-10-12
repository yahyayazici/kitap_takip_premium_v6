from django.conf import settings

from okuma.erisim import kullanici_yonetimi_acik


def kurum(request):
    return {
        "KURUM_ADI": getattr(settings, "KURUM_ADI", "Çinili Saray"),
        "OKUMA_KULLANICI_YONETIMI": kullanici_yonetimi_acik(),
    }
