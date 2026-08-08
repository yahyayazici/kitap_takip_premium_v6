# Generated manually for PanelMetrik

from django.db import migrations, models


def seed(apps, schema_editor):
    PanelMetrik = apps.get_model("takip", "PanelMetrik")
    rows = (
        ("talebe", "Talebe", "Aktif kayıt", "blue", "users", True, True, False, 10),
        ("bugun_okunan", "Bugün okunan", "Toplam sayfa", "green", "book", True, False, False, 20),
        ("okuma_kaydi", "Okuma kaydı", "", "amber", "folder", True, False, False, 30),
        ("sinav", "Sınav", "", "violet", "clipboard", True, False, False, 40),
        ("aktif_deneme", "Aktif deneme", "Yayındaki denemeler", "amber", "chart", False, True, False, 50),
        ("ktt", "KTT", "Kayıtlı tarama", "violet", "target", False, True, False, 60),
        ("personel", "Personel", "Aktif personel", "green", "users", False, True, False, 15),
        ("sinif", "Sınıf", "Tanımlı sınıf", "blue", "groups", False, True, False, 25),
    )
    for anahtar, baslik, not_m, ton, icon, p, y, v, sira in rows:
        PanelMetrik.objects.get_or_create(
            anahtar=anahtar,
            defaults={
                "baslik": baslik,
                "not_metni": not_m,
                "ton": ton,
                "icon": icon,
                "goster_personel": p,
                "goster_yonetim": y,
                "goster_veli": v,
                "sira": sira,
                "aktif": True,
            },
        )


def unseed(apps, schema_editor):
    PanelMetrik = apps.get_model("takip", "PanelMetrik")
    PanelMetrik.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0049_panel_kisayol"),
    ]

    operations = [
        migrations.CreateModel(
            name="PanelMetrik",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anahtar", models.SlugField(help_text="Örn. talebe, bugun_okunan, aktif_deneme", max_length=40, unique=True, verbose_name="Anahtar")),
                ("baslik", models.CharField(max_length=60, verbose_name="Başlık")),
                ("not_metni", models.CharField(blank=True, help_text="Boş bırakılırsa varsayılan not kullanılır.", max_length=80, verbose_name="Alt not")),
                ("ton", models.CharField(choices=[("blue", "Mavi"), ("green", "Yeşil"), ("amber", "Turuncu"), ("violet", "Mor")], default="blue", max_length=12, verbose_name="Renk")),
                ("icon", models.CharField(default="users", max_length=20, verbose_name="İkon")),
                ("goster_personel", models.BooleanField(default=True, verbose_name="Personel")),
                ("goster_yonetim", models.BooleanField(default=False, verbose_name="Yönetim")),
                ("goster_veli", models.BooleanField(default=False, verbose_name="Veli")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Panel metriği",
                "verbose_name_plural": "Panel metrikleri",
                "ordering": ["sira", "id"],
            },
        ),
        migrations.RunPython(seed, unseed),
    ]
