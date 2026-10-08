from django.db import migrations, models
import django.db.models.deletion


def ornek_formu_ekle(apps, schema_editor):
    Form = apps.get_model("takip", "OptikForm")
    Alan = apps.get_model("takip", "OptikFormAlani")
    from takip.deneme_optik import (
        ORNEK_ALANLAR,
        ORNEK_FORM_ACIKLAMA,
        ORNEK_FORM_AD,
        ORNEK_KODLAMA,
        ORNEK_SATIR,
    )

    if Form.objects.filter(ad=ORNEK_FORM_AD).exists():
        return
    form = Form.objects.create(
        ad=ORNEK_FORM_AD,
        aciklama=ORNEK_FORM_ACIKLAMA,
        satir_uzunluk=ORNEK_SATIR,
        kodlama=ORNEK_KODLAMA,
    )
    Alan.objects.bulk_create(
        [
            Alan(form=form, tur=tur, baslangic=bas, bitis=bit, sira=sira)
            for sira, (tur, bas, bit) in enumerate(ORNEK_ALANLAR)
        ]
    )


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0114_nehari_gunluk_odev"),
    ]

    operations = [
        migrations.CreateModel(
            name="OptikForm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ad", models.CharField(max_length=120, unique=True, verbose_name="Form adı")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama")),
                ("satir_uzunluk", models.PositiveIntegerField(verbose_name="Satır uzunluğu")),
                ("kodlama", models.CharField(default="cp1254", help_text="cp1254 Türkçe Windows, utf-8 düz metin.", max_length=20, verbose_name="Harf düzeni")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Optik form",
                "verbose_name_plural": "Optik formlar",
                "ordering": ["ad"],
            },
        ),
        migrations.CreateModel(
            name="OptikFormAlani",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tur", models.CharField(choices=[("tc", "TC"), ("numara", "Öğrenci no"), ("numara_kontrol", "Numara taşma kontrolü"), ("kitapcik", "Kitapçık"), ("sinif", "Sınıf"), ("sube", "Şube"), ("ad", "Ad soyad"), ("sik", "Şık bölgesi")], max_length=20, verbose_name="Tür")),
                ("baslangic", models.PositiveIntegerField(verbose_name="Başlangıç kolonu")),
                ("bitis", models.PositiveIntegerField(verbose_name="Bitiş kolonu")),
                ("sira", models.PositiveIntegerField(default=0)),
                ("form", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="alanlar", to="takip.optikform", verbose_name="Form")),
            ],
            options={
                "verbose_name": "Optik form alanı",
                "verbose_name_plural": "Optik form alanları",
                "ordering": ["sira", "id"],
            },
        ),
        migrations.CreateModel(
            name="DenemeOptik",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anahtar_a", models.TextField(verbose_name="A kitapçık anahtarı")),
                ("anahtar_b", models.TextField(blank=True, verbose_name="B kitapçık anahtarı")),
                ("dagilim", models.TextField(help_text="Şeritteki sıra. Her satır: turkce 15", verbose_name="Ders sırası")),
                ("kazanimlar", models.TextField(blank=True, help_text="İsteğe bağlı. Her satır bir soru, şeritteki sırayla.", verbose_name="Soru kazanımları")),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                ("deneme", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="optik", to="takip.denemesinavi", verbose_name="Deneme")),
                ("form", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="denemeler", to="takip.optikform", verbose_name="Optik form")),
            ],
            options={
                "verbose_name": "Deneme optik tanımı",
                "verbose_name_plural": "Deneme optik tanımları",
            },
        ),
        migrations.RunPython(ornek_formu_ekle, migrations.RunPython.noop),
    ]
