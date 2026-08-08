# Generated manually for idareci vazife / YÇT / yazılı tur

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("takip", "0046_haftalik_sohbet_mevzuu"),
    ]

    operations = [
        migrations.AddField(
            model_name="yazilisinav",
            name="tur",
            field=models.CharField(
                choices=[("ornek", "Örnek yazılı"), ("gercek", "Gerçek yazılı")],
                default="ornek",
                help_text="Kamp sürecindeki örnek veya okul gerçek yazılısı",
                max_length=10,
                verbose_name="Tür",
            ),
        ),
        migrations.AddField(
            model_name="yazilisinav",
            name="yazili_no",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Örn. 1. yazılı, 2. yazılı",
                verbose_name="Yazılı no",
            ),
        ),
        migrations.AlterModelOptions(
            name="yazilisinav",
            options={
                "ordering": ["sinav_tarihi", "yazili_no", "id"],
                "verbose_name": "Yazılı sınav",
                "verbose_name_plural": "Yazılı sınavlar",
            },
        ),
        migrations.CreateModel(
            name="PersonelVazife",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslik", models.CharField(max_length=200, verbose_name="Vazife")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama")),
                ("baslangic", models.DateField(verbose_name="Başlangıç")),
                ("bitis", models.DateField(blank=True, null=True, verbose_name="Bitiş / son tarih")),
                (
                    "durum",
                    models.CharField(
                        choices=[
                            ("atandi", "Atandı"),
                            ("onaylandi", "Onaylandı"),
                            ("devam", "Devam ediyor"),
                            ("tamamlandi", "Tamamlandı"),
                            ("iptal", "İptal"),
                        ],
                        default="atandi",
                        max_length=20,
                        verbose_name="Durum",
                    ),
                ),
                (
                    "oncelik",
                    models.CharField(
                        choices=[
                            ("dusuk", "Düşük"),
                            ("normal", "Normal"),
                            ("yuksek", "Yüksek"),
                            ("acil", "Acil"),
                        ],
                        default="normal",
                        max_length=10,
                        verbose_name="Öncelik",
                    ),
                ),
                ("personel_notu", models.TextField(blank=True, verbose_name="Personel notu")),
                ("onay_tarihi", models.DateTimeField(blank=True, null=True, verbose_name="Onay tarihi")),
                ("tamamlanma_tarihi", models.DateTimeField(blank=True, null=True, verbose_name="Tamamlanma tarihi")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "atanan",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vazifeler",
                        to="takip.personelprofili",
                        verbose_name="Atanan personel",
                    ),
                ),
                (
                    "atayan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="atadigi_vazifeler",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Atayan",
                    ),
                ),
                (
                    "sinif_sube",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="vazifeler",
                        to="takip.sinifsube",
                        verbose_name="İlgili sınıf",
                    ),
                ),
            ],
            options={
                "verbose_name": "Personel vazife",
                "verbose_name_plural": "Personel vazifeleri",
                "ordering": ["-olusturulma", "-id"],
            },
        ),
        migrations.CreateModel(
            name="YctOlay",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("baslik", models.CharField(max_length=200, verbose_name="Başlık")),
                ("aciklama", models.TextField(blank=True, verbose_name="Açıklama / plan")),
                ("baslangic", models.DateField(verbose_name="Başlangıç")),
                (
                    "bitis",
                    models.DateField(
                        blank=True,
                        help_text="Boş bırakılırsa tek günlük olay sayılır.",
                        null=True,
                        verbose_name="Bitiş",
                    ),
                ),
                (
                    "kategori",
                    models.CharField(
                        choices=[
                            ("genel", "Genel"),
                            ("yazili", "Yazılı / kamp"),
                            ("deneme", "Deneme"),
                            ("ktt", "KTT"),
                            ("etkinlik", "Etkinlik"),
                            ("tatil", "Tatil"),
                            ("toplanti", "Toplantı"),
                            ("program", "Program"),
                        ],
                        default="genel",
                        max_length=20,
                        verbose_name="Kategori",
                    ),
                ),
                ("tum_personel", models.BooleanField(default=True, verbose_name="Tüm personele görünür")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
                (
                    "olusturan",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="olusturdugu_yct_olaylari",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Oluşturan",
                    ),
                ),
            ],
            options={
                "verbose_name": "YÇT olayı",
                "verbose_name_plural": "YÇT olayları",
                "ordering": ["baslangic", "id"],
            },
        ),
    ]
