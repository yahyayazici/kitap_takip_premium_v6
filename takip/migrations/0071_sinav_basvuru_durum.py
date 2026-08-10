from django.db import migrations, models
import django.db.models.deletion


def seed_ve_tasi(apps, schema_editor):
    Durum = apps.get_model("takip", "SinavBasvuruDurum")
    Basvuru = apps.get_model("takip", "SinavBasvuru")

    defaults = [
        ("yeni", "Yeni", 1, ""),
        ("inceleniyor", "İnceleniyor", 2, ""),
        ("kabul", "Kabul", 3, "kabul"),
        ("red", "Red", 4, "red"),
    ]
    kod_map = {}
    for kod, ad, sira, mesaj in defaults:
        obj, _ = Durum.objects.get_or_create(
            kod=kod,
            defaults={
                "ad": ad,
                "sira": sira,
                "aktif": True,
                "mesaj_an_kodu": mesaj,
            },
        )
        kod_map[kod] = obj

    for basvuru in Basvuru.objects.all():
        eski = (getattr(basvuru, "durum_eski", None) or "yeni").strip()
        durum = kod_map.get(eski) or kod_map["yeni"]
        basvuru.durum_id = durum.id
        basvuru.save(update_fields=["durum_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0070_sinav_basvuru_mesaj"),
    ]

    operations = [
        migrations.CreateModel(
            name="SinavBasvuruDurum",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("kod", models.SlugField(max_length=40, unique=True, verbose_name="Kod")),
                ("ad", models.CharField(max_length=80, verbose_name="Durum adı")),
                (
                    "sira",
                    models.PositiveSmallIntegerField(default=0, verbose_name="Sıra"),
                ),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                (
                    "mesaj_an_kodu",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Bu duruma geçince tetiklenecek mesaj anı kodu "
                            "(örn. kabul, red)."
                        ),
                        max_length=40,
                        verbose_name="WhatsApp mesaj anı",
                    ),
                ),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Sınav başvuru durumu",
                "verbose_name_plural": "Sınav başvuru durumları",
                "ordering": ["sira", "ad"],
            },
        ),
        migrations.RenameField(
            model_name="sinavbasvuru",
            old_name="durum",
            new_name="durum_eski",
        ),
        migrations.AddField(
            model_name="sinavbasvuru",
            name="durum",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="basvurular",
                to="takip.sinavbasvurudurum",
                verbose_name="Durum",
            ),
        ),
        migrations.RunPython(seed_ve_tasi, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="sinavbasvuru",
            name="durum",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="basvurular",
                to="takip.sinavbasvurudurum",
                verbose_name="Durum",
            ),
        ),
        migrations.RemoveField(
            model_name="sinavbasvuru",
            name="durum_eski",
        ),
    ]
