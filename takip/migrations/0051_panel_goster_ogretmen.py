# Öğretmen hedefi — kısayol + özet kart

from django.db import migrations, models


def seed_ogretmen(apps, schema_editor):
    PanelMetrik = apps.get_model("takip", "PanelMetrik")
    PanelKisayol = apps.get_model("takip", "PanelKisayol")

    metrikler = (
        ("sorumlu_sinif", "Sorumlu sınıf", "", "blue", "groups", 10),
        ("ogretmen_ogrenci", "Toplam öğrenci", "", "green", "users", 20),
        ("aktif_hafta", "Aktif hafta", "Hafta", "amber", "calendar", 30),
    )
    for anahtar, baslik, not_m, ton, icon, sira in metrikler:
        obj, created = PanelMetrik.objects.get_or_create(
            anahtar=anahtar,
            defaults={
                "baslik": baslik,
                "not_metni": not_m,
                "ton": ton,
                "icon": icon,
                "goster_personel": False,
                "goster_yonetim": False,
                "goster_veli": False,
                "goster_ogretmen": True,
                "sira": sira,
                "aktif": True,
            },
        )
        if not created:
            obj.goster_ogretmen = True
            obj.save(update_fields=["goster_ogretmen"])

    kisayollar = (
        (
            "ogretmen_not",
            "Not Girişi",
            "Yoklama ve haftalık not",
            "clipboard",
            "NG",
            "ogretmen_not_girisi",
            10,
        ),
        (
            "ogretmen_program",
            "Ders Programı",
            "Haftalık program",
            "calendar",
            "DP",
            "ogretmen_ders_programi",
            20,
        ),
        (
            "ogretmen_degerlendirme",
            "Değerlendirmeler",
            "Not ve karne",
            "chart",
            "DG",
            "ogretmen_degerlendirmeler",
            30,
        ),
    )
    for anahtar, baslik, alt, icon, mark, url_name, sira in kisayollar:
        obj, created = PanelKisayol.objects.get_or_create(
            anahtar=anahtar,
            defaults={
                "baslik": baslik,
                "alt_baslik": alt,
                "icon": icon,
                "mark": mark,
                "url_name": url_name,
                "goster_personel": False,
                "goster_yonetim": False,
                "goster_veli": False,
                "goster_ogretmen": True,
                "sira": sira,
                "aktif": True,
            },
        )
        if not created:
            obj.goster_ogretmen = True
            if not obj.url_name:
                obj.url_name = url_name
            obj.save(update_fields=["goster_ogretmen", "url_name"])


def unseed_ogretmen(apps, schema_editor):
    PanelMetrik = apps.get_model("takip", "PanelMetrik")
    PanelKisayol = apps.get_model("takip", "PanelKisayol")
    PanelMetrik.objects.filter(
        anahtar__in=("sorumlu_sinif", "ogretmen_ogrenci", "aktif_hafta")
    ).delete()
    PanelKisayol.objects.filter(
        anahtar__in=("ogretmen_not", "ogretmen_program", "ogretmen_degerlendirme")
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0050_panel_metrik"),
    ]

    operations = [
        migrations.AddField(
            model_name="panelkisayol",
            name="goster_ogretmen",
            field=models.BooleanField(default=False, verbose_name="Öğretmen"),
        ),
        migrations.AddField(
            model_name="panelmetrik",
            name="goster_ogretmen",
            field=models.BooleanField(default=False, verbose_name="Öğretmen"),
        ),
        migrations.RunPython(seed_ogretmen, unseed_ogretmen),
    ]
