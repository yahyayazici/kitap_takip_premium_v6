from django.db import migrations

SORU_TAKIP_DERS_ADLARI = (
    "Türkçe",
    "Paragraf",
    "Matematik",
    "Fen Bilimleri",
    "Sosyal Bilgiler",
    "İngilizce",
    "Din Kültürü",
)

BRANS_MAP = {
    "Türkçe": "Türkçe",
    "Paragraf": "Türkçe",
    "Matematik": "Matematik",
    "Fen Bilimleri": "Fen",
    "Sosyal Bilgiler": "Sosyal",
    "İngilizce": "Türkçe",
    "Din Kültürü": "Din",
}


def _dersleri_ekle(apps, schema_editor):
    """SORU_TAKIP_DERS_ADLARI'ndaki eksik dersleri (özellikle Din Kültürü ve
    Paragraf) oluşturur. Var olanlara dokunmaz — idempotent."""
    Brans = apps.get_model("takip", "Brans")
    Ders = apps.get_model("takip", "Ders")

    for sira, ad in enumerate(SORU_TAKIP_DERS_ADLARI, start=1):
        brans, _ = Brans.objects.get_or_create(
            ad=BRANS_MAP.get(ad, "Türkçe"),
            defaults={"sira": sira, "aktif": True},
        )
        Ders.objects.get_or_create(
            ad=ad,
            defaults={"brans": brans, "sira": sira, "aktif": True},
        )


def _geri_al(apps, schema_editor):
    # Ders/Brans kayıtları başka verilerle ilişkili olabileceğinden geri
    # alınmıyor; bu sadece eksik seed verisini tamamlayan bir adım.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0095_deneme_analiz_sistemi"),
    ]

    operations = [
        migrations.RunPython(_dersleri_ekle, _geri_al),
    ]
