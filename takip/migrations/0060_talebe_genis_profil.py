from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0059_toplanti_alt_baslik"),
    ]

    operations = [
        migrations.AddField(
            model_name="talebe",
            name="kimlik_adi",
            field=models.CharField(blank=True, max_length=60, verbose_name="Kimlikteki adı"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="kimlik_soyadi",
            field=models.CharField(blank=True, max_length=60, verbose_name="Kimlikteki soyadı"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="cinsiyet",
            field=models.CharField(
                blank=True,
                choices=[("erkek", "Erkek"), ("kadin", "Kadın")],
                max_length=10,
                verbose_name="Cinsiyet",
            ),
        ),
        migrations.AddField(
            model_name="talebe",
            name="baba_adi",
            field=models.CharField(blank=True, max_length=80, verbose_name="Baba adı"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="anne_adi",
            field=models.CharField(blank=True, max_length=80, verbose_name="Anne adı"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="dogum_yeri",
            field=models.CharField(blank=True, max_length=120, verbose_name="Doğum yeri"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="memleket",
            field=models.CharField(blank=True, max_length=120, verbose_name="Memleketi"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="diller",
            field=models.CharField(blank=True, max_length=200, verbose_name="Bildiği diller"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="dahili_seviye",
            field=models.CharField(blank=True, max_length=80, verbose_name="Dahili seviyesi"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="dahili_ders_mesulu",
            field=models.CharField(blank=True, max_length=120, verbose_name="Dahili ders mesulü"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="dahili_ders_grubu",
            field=models.CharField(blank=True, max_length=80, verbose_name="Dahili ders grubu"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="okul_seviyesi",
            field=models.CharField(blank=True, max_length=80, verbose_name="Okul seviyesi"),
        ),
        migrations.AddField(
            model_name="talebe",
            name="aile_durumu",
            field=models.CharField(
                blank=True,
                choices=[
                    ("beraber", "Anne – baba beraber"),
                    ("ayri", "Anne – baba ayrı"),
                    ("ayri_baba_uvey", "Anne – baba ayrı – baba üvey"),
                    ("ayri_anne_uvey", "Anne – baba ayrı – anne üvey"),
                    ("anne_vefat", "Anne vefat"),
                    ("anne_vefat_anne_uvey", "Anne vefat – anne üvey"),
                ],
                max_length=30,
                verbose_name="Aile durumu",
            ),
        ),
    ]
