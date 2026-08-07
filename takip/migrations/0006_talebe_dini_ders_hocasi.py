from django.db import migrations, models
import django.db.models.deletion


def dini_ders_hocasini_kopyala(apps, schema_editor):
    Talebe = apps.get_model("takip", "Talebe")

    for talebe in Talebe.objects.filter(dini_ders_hocasi__isnull=True).iterator():
        talebe.dini_ders_hocasi_id = talebe.etut_hocasi_id
        talebe.save(update_fields=["dini_ders_hocasi_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0005_personelprofili"),
    ]

    operations = [
        migrations.AddField(
            model_name="talebe",
            name="dini_ders_hocasi",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dini_ders_talebeleri",
                to="takip.etuthocasi",
                verbose_name="Dini ders hocası",
            ),
        ),
        migrations.RunPython(
            dini_ders_hocasini_kopyala,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="talebe",
            name="dini_ders_hocasi",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="dini_ders_talebeleri",
                to="takip.etuthocasi",
                verbose_name="Dini ders hocası",
            ),
        ),
    ]
