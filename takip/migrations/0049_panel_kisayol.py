# Generated manually for PanelKisayol

from django.db import migrations, models


def seed_ve_gorsel_tasi(apps, schema_editor):
    PanelKisayol = apps.get_model("takip", "PanelKisayol")
    PanelKisayolGorsel = apps.get_model("takip", "PanelKisayolGorsel")

    katalog = (
        ("kitap", "Kitap Takip", "Zimmet, okuma ve arşiv", "book", "KT", "kitap_listesi", True, False, False),
        ("talebeler", "Talebeler", "Liste ve profiller", "users", "TL", "talebe_listesi", True, True, False),
        ("etut", "Etüt Grupları", "Grupları yönet", "groups", "EG", "etut_plan_panel", True, False, False),
        ("gunluk_takip", "Günlük Takip", "Yoklama ve takip", "clipboard", "GT", "gunluk_takip_panel", True, False, False),
        ("rehberlik", "Rehberlik", "Rehber öğretmen görüşmeleri", "chat", "RH", "rehberlik_listesi", True, False, False),
        ("veli_iletisim", "Veli & Talebe İletişim", "Veli ve öğrenci görüşmeleri", "phone", "Vİ", "iletisim_listesi", True, False, False),
        ("deneme", "Deneme Sonuçları", "Deneme analizi", "chart", "DN", "deneme_listesi", True, False, False),
        ("ktt", "KTT Takip", "Kazanım tarama testleri", "target", "KTT", "ktt_listesi", True, False, False),
        ("gorevler", "Görevler", "İmam, temizlik, yemek", "check", "GV", "", True, False, False),
        ("dosyalar", "Dosyalar", "Gelişim dosyaları", "folder", "GD", "talebe_listesi", True, False, False),
        ("takvim", "Takvim", "Kurum programı", "calendar", "TK", "program_panel", True, True, False),
        ("raporlar", "Raporlar", "Filtre ve PDF çıktı", "pie", "RP", "raporlar", True, True, False),
        ("ayarlar", "Ayarlar", "Kurum ve modül ayarları", "settings", "AY", "yonetim:dashboard", True, True, False),
        ("veli_duyurular", "Duyurular", "Kurum duyuruları", "chat", "DY", "veli_duyurular", False, False, True),
        ("veli_ana", "Ana Sayfa", "Öğrenci seçimi", "users", "AN", "veli_dashboard", False, False, True),
    )

    gorsel_map = {
        g.anahtar: g
        for g in PanelKisayolGorsel.objects.all()
    }

    for i, (anahtar, baslik, alt, icon, mark, url_name, p, y, v) in enumerate(katalog):
        eski = gorsel_map.get(anahtar)
        obj, _ = PanelKisayol.objects.get_or_create(
            anahtar=anahtar,
            defaults={
                "baslik": baslik,
                "alt_baslik": alt,
                "icon": icon,
                "mark": mark,
                "url_name": url_name,
                "goster_personel": p,
                "goster_yonetim": y,
                "goster_veli": v,
                "sira": i * 10,
                "aktif": True,
            },
        )
        if eski and eski.gorsel and not obj.gorsel:
            obj.gorsel = eski.gorsel
            obj.baslik = obj.baslik or eski.baslik or baslik
            obj.save(update_fields=["gorsel", "baslik", "guncellenme"])


def unseed(apps, schema_editor):
    PanelKisayol = apps.get_model("takip", "PanelKisayol")
    PanelKisayol.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("takip", "0048_panel_kisayol_gorsel"),
    ]

    operations = [
        migrations.CreateModel(
            name="PanelKisayol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("anahtar", models.SlugField(help_text="Örn. kitap, talebeler, ozel-duyuru", max_length=40, unique=True, verbose_name="Anahtar")),
                ("baslik", models.CharField(max_length=80, verbose_name="Başlık")),
                ("alt_baslik", models.CharField(blank=True, max_length=120, verbose_name="Alt yazı")),
                ("icon", models.CharField(default="book", help_text="book, users, groups, clipboard, chat, phone, chart, target, check, folder, calendar, pie, settings", max_length=20, verbose_name="İkon")),
                ("mark", models.CharField(blank=True, help_text="Banner sağ üst (ör. KT)", max_length=8, verbose_name="Kısaltma")),
                ("url_name", models.CharField(blank=True, help_text="Django url name (ör. kitap_listesi, yonetim:talebe_listesi, veli_duyurular)", max_length=120, verbose_name="URL adı")),
                ("url_ozel", models.CharField(blank=True, help_text="Doğrudan yol: /panel/... veya https://...", max_length=300, verbose_name="Özel URL")),
                ("gorsel", models.ImageField(blank=True, help_text="Önerilen: 640×400 (16:10).", null=True, upload_to="panel_kisayol/", verbose_name="Banner görseli")),
                ("goster_personel", models.BooleanField(default=True, verbose_name="Personel")),
                ("goster_yonetim", models.BooleanField(default=False, verbose_name="Yönetim / Admin")),
                ("goster_veli", models.BooleanField(default=False, verbose_name="Veli")),
                ("sira", models.PositiveSmallIntegerField(default=0, verbose_name="Sıra")),
                ("aktif", models.BooleanField(default=True, verbose_name="Aktif")),
                ("olusturulma", models.DateTimeField(auto_now_add=True)),
                ("guncellenme", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Panel kısayolu",
                "verbose_name_plural": "Panel kısayolları",
                "ordering": ["sira", "id"],
            },
        ),
        migrations.RunPython(seed_ve_gorsel_tasi, unseed),
    ]
