from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0054_bildirim"),
    ]

    operations = [
        migrations.AddField(
            model_name="yazilisinav",
            name="ders",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="yazili_sinavlar",
                to="takip.ders",
                verbose_name="Ders",
            ),
        ),
        migrations.AddField(
            model_name="yazilisinav",
            name="hedef_siniflar",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Virgülle: 7-A, 7-B",
                max_length=255,
                verbose_name="Hedef sınıflar",
            ),
        ),
        migrations.AlterField(
            model_name="yazilisinav",
            name="soru_sayisi",
            field=models.PositiveIntegerField(
                blank=True,
                default=0,
                help_text="Puan girişinde kullanılmaz; isteğe bağlı.",
                verbose_name="Soru sayısı",
            ),
        ),
        migrations.AlterField(
            model_name="yazilisonuc",
            name="puan",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                verbose_name="Puan (100)",
            ),
        ),
    ]
