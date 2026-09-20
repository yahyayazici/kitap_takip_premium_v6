import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _egitim_yili_ve_sira_no_ata(apps, schema_editor):
    """Mevcut denemelere en iyi tahminle eğitim yılı + sıra no atar.

    Yeni alanlar hepsi nullable/varsayılanlı; bu adım sadece kullanışlılık
    için — yönetici sonradan sıra numarasını arayüzden düzeltebilir.
    """
    DenemeSinavi = apps.get_model("takip", "DenemeSinavi")
    EgitimYili = apps.get_model("takip", "EgitimYili")

    yillar = list(EgitimYili.objects.all())

    def _yil_bul(tarih):
        if tarih is None:
            return None
        for yil in yillar:
            if yil.baslangic and yil.bitis and yil.baslangic <= tarih <= yil.bitis:
                return yil
        return None

    denemeler = list(
        DenemeSinavi.objects.filter(tur="grup").order_by("sinav_tarihi", "id")
    )
    for deneme in denemeler:
        deneme.egitim_yili = _yil_bul(deneme.sinav_tarihi)

    gruplar: dict[tuple, list] = {}
    for deneme in denemeler:
        anahtar = (deneme.egitim_yili_id, (deneme.sinif_seviyesi or "").strip())
        gruplar.setdefault(anahtar, []).append(deneme)

    for grup in gruplar.values():
        for sira, deneme in enumerate(grup, start=1):
            deneme.sira_no = sira

    if denemeler:
        DenemeSinavi.objects.bulk_update(denemeler, ["egitim_yili", "sira_no"])


def _geri_al(apps, schema_editor):
    # Sıra no / eğitim yılı geri alınmıyor — alanlar nullable, sıfırlamaya gerek yok.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0094_alter_ekranmedya_dosya_alter_ekranmedya_onizleme_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="denemesinavi",
            name="tur",
            field=models.CharField(
                choices=[("grup", "Grup denemesi"), ("bireysel", "Bireysel deneme")],
                default="grup",
                max_length=10,
                verbose_name="Deneme türü",
            ),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="sira_no",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                help_text="Eğitim yılı + sınıf seviyesi içinde kurum sırası (örn. 4. Deneme).",
                verbose_name="Sıra numarası",
            ),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="yayin",
            field=models.CharField(
                blank=True,
                help_text="Denemenin gerçek adı/yayını (sıra numarasını belirlemez).",
                max_length=120,
                verbose_name="Yayın",
            ),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="egitim_yili",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="denemeler",
                to="takip.egitimyili",
                verbose_name="Eğitim yılı",
            ),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="toplam_soru",
            field=models.PositiveIntegerField(default=0, verbose_name="Toplam soru"),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="excel_dosyasi",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="deneme/excel/%Y/%m/",
                verbose_name="Excel dosyası",
            ),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="hedef_sinif_subeler",
            field=models.ManyToManyField(
                blank=True,
                help_text="Boşsa tüm sınıf seviyesi kapsanır (grup denemesi).",
                related_name="hedefli_denemeler",
                to="takip.sinifsube",
                verbose_name="Hedef sınıflar",
            ),
        ),
        migrations.AddField(
            model_name="denemesinavi",
            name="bireysel_talebe",
            field=models.ForeignKey(
                blank=True,
                null=True,
                help_text="Yalnızca bireysel deneme türü için.",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="bireysel_denemeleri",
                to="takip.talebe",
                verbose_name="Bireysel deneme sahibi",
            ),
        ),
        migrations.AddConstraint(
            model_name="denemesinavi",
            constraint=models.UniqueConstraint(
                condition=models.Q(("sira_no__isnull", False)),
                fields=("egitim_yili", "sinif_seviyesi", "sira_no"),
                name="deneme_sira_no_benzersiz",
            ),
        ),
        migrations.AlterModelOptions(
            name="denemesonucu",
            options={
                "ordering": ["-puan", "-toplam_net", "talebe__ad_soyad"],
                "verbose_name": "Deneme sonucu",
                "verbose_name_plural": "Deneme sonuçları",
            },
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="sinif_sirasi",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Sınıf sırası"
            ),
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="sinif_toplam",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Sınıf mevcudu"
            ),
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="seviye_sirasi",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Sınıf seviyesi sırası"
            ),
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="seviye_toplam",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Sınıf seviyesi mevcudu"
            ),
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="kurum_sirasi",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Kurum sırası"
            ),
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="kurum_toplam",
            field=models.PositiveIntegerField(
                blank=True, null=True, verbose_name="Kurum mevcudu"
            ),
        ),
        migrations.AddField(
            model_name="denemesonucu",
            name="dis_siralama_metni",
            field=models.CharField(
                blank=True,
                help_text="Excel'de bulunan yayın/Türkiye geneli sıralaması (ham metin, kurum içi sıralamayla karıştırılmaz).",
                max_length=200,
                verbose_name="Harici sıralama",
            ),
        ),
        migrations.CreateModel(
            name="DenemeExcelYukleme",
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
                ("dosya_hash", models.CharField(max_length=64, verbose_name="Dosya hash (sha256)")),
                ("dosya_adi", models.CharField(blank=True, max_length=255, verbose_name="Dosya adı")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                (
                    "deneme",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="excel_yuklemeleri",
                        to="takip.denemesinavi",
                        verbose_name="Deneme",
                    ),
                ),
                (
                    "yukleyen",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deneme_excel_yuklemeleri",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Yükleyen",
                    ),
                ),
            ],
            options={
                "verbose_name": "Deneme Excel yüklemesi",
                "verbose_name_plural": "Deneme Excel yüklemeleri",
                "ordering": ["-olusturulma", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="denemeexcelyukleme",
            index=models.Index(fields=["deneme", "dosya_hash"], name="deneme_excel_hash_idx"),
        ),
        migrations.RunPython(_egitim_yili_ve_sira_no_ata, _geri_al),
    ]
