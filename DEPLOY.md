# Çinili Saray Proje — Render + cinilisarayproje.com

Canlı panel: **https://cinilisarayproje.com**  
Render yedek adres: **https://kitap-takip-premium-v6.onrender.com**

## Performans (önerilen ücretli plan)

Free plan boşta uykuya geçer; ilk tıklamada 10–40 sn bekletir. Üretim için:

| Servis | Plan | Yaklaşık |
|--------|------|----------|
| Web | **Starter** | ~$7/ay |
| Postgres | **Basic 256 MB** | ~$6/ay |

Dashboard: servis → **Settings** → **Instance Type** → Starter.  
Veritabanı → **Settings** → **Instance Type** → Basic-256mb.

## 1. Kodu GitHub'a gönder

```bash
git add .
git commit -m "cinilisarayproje.com domain ayarları"
git push origin main
```

Push sonrası Render otomatik deploy eder.

## 2. Render — özel domain ekle

1. https://dashboard.render.com → servis **kitap-takip-premium-v6**
2. **Settings** → **Custom Domains** → **Add Custom Domain**
3. Sırayla ekle:
   - `cinilisarayproje.com`
   - `www.cinilisarayproje.com`
4. Render her domain için DNS kayıtlarını gösterir — Namecheap'e aynen gir.

## 3. Namecheap DNS kayıtları

Namecheap → **Domain List** → `cinilisarayproje.com` → **Manage** → **Advanced DNS**

| Tür | Host | Değer | TTL |
|-----|------|-------|-----|
| **CNAME** | `www` | `kitap-takip-premium-v6.onrender.com` | Automatic |
| **URL Redirect** veya **A Record** | `@` | Render'ın verdiği IP (Custom Domains ekranında) | Automatic |

**Kök domain (@) için iki seçenek:**

**A) Render A kaydı (önerilen)**  
Custom Domains ekranında `cinilisarayproje.com` için gösterilen **A record IP**'yi Namecheap'te `@` host'una ekle.

**B) www yönlendirmesi**  
Kök domain'i Namecheap **URL Redirect Record** ile `https://www.cinilisarayproje.com` adresine yönlendir; `www` CNAME'i Render'a bağla.

> DNS yayılımı 5–30 dakika (bazen 24 saat) sürebilir.

## 4. Render ortam değişkenleri

**Environment** sekmesinde şunlar olmalı:

| Değişken | Değer |
|----------|--------|
| `CUSTOM_DOMAIN` | `cinilisarayproje.com,www.cinilisarayproje.com` |
| `CANONICAL_HOST` | `cinilisarayproje.com` |
| `PANEL_PUBLIC_URL` | `https://cinilisarayproje.com` |
| `PANEL_NAME` | `Çinili Saray Proje` |
| `PANEL_SHORT` | `Çinili Saray Proje` |
| `DEBUG` | `False` |

`render.yaml` bu değerleri Blueprint ile otomatik ayarlar; elle değiştirdiysen yukarıdakilerle eşleştir.

### Yapay zeka (Claude API)

Analizler (Gelişim/Deneme/Kurum Zekası, KTT değerlendirmesi, veli özetleri) ve panel asistanı Claude API kullanır.

| Değişken | Değer |
|----------|--------|
| `ANTHROPIC_API_KEY` | Claude Console'dan alınan anahtar — **yalnızca** Render Environment'a girilir (`sync: false`), repoya yazılmaz |
| `AI_ANALIZ_MODEL` / `AI_SOHBET_MODEL` | Varsayılan `claude-opus-5-5` |

Anahtar boşsa site çalışmaya devam eder; analizler ve asistan kural tabanlı modda kalır.
Diğer sınır ve zaman aşımı ayarları için `.env.example` dosyasındaki `AI_*` değişkenlerine bakın.
Eski `OPENAI_API_KEY` ve `AI_ASSISTANT_MODEL` değişkenleri artık kullanılmıyor; Render'dan silinebilir.

## 5. SSL (HTTPS)

Render, DNS doğrulandıktan sonra Let's Encrypt sertifikasını otomatik verir. Custom Domains ekranında **Verified** yeşil olmalı.

## 6. Test

DNS yayıldıktan sonra:

- https://cinilisarayproje.com/giris/
- https://www.cinilisarayproje.com/giris/ (www de eklediysen)
- https://kitap-takip-premium-v6.onrender.com → otomatik `cinilisarayproje.com`'a yönlendirilmeli

## 7. Yerel geliştirme

```bash
cp .env.example .env
python manage.py runserver
```

## 8. KTT / soru takip PDF (WeasyPrint)

Eski “Tam Sayılarda Problemler” PDF’i **WeasyPrint 69** ile üretilir (madalya, KPI ikonları, başarı çubuğu, tek A4 sayfa). Canlıda Pango/Cairo yoksa motor **xhtml2pdf**’e düşer; tasarım bozulur.

Dockerfile Pango + Cairo kurar. Mevcut servis native Python ise Dashboard’da runtime’ı **Docker** yapın:

1. Render → `kitap-takip-premium-v6` → **Settings** → **Build** → **Source** → **Edit**
2. Runtime: **Docker**
3. Deploy

Blueprint kullanıyorsanız `render.yaml` zaten `runtime: docker`.

PDF indirmede yanıt başlığı `X-PDF-Engine: weasyprint` olmalı. Acrobat’ta **Üretici: WeasyPrint**.

## 9. İlk admin

Render Shell:

```bash
python manage.py createsuperuser
```

## E-Kitap alt alan adı (`ekitap.cinilisarayproje.com`)

Akıllı tahtada deneme kitapçığını flipbook olarak göstermek için. Aynı Render servisinde çalışır
(ayrı sunucu/ücret yok) ama ana sitenin kullanıcı sistemine bağlı değildir:
yönetici girişi `EKITAP_YONETICI_SIFRE` ile, tahta görüntüleme yöneticinin belirlediği PIN ile yapılır.
Arama motorlarına kapalıdır (`noindex` + `robots.txt`).

1. **Kodu yayınla:** dal `main`'e birleşince Render otomatik deploy eder; `migrate` başlangıçta çalışır.
2. **Render → Environment:** `EKITAP_YONETICI_SIFRE` ekleyin (uzun, tahmin edilemez bir şifre).
   `EKITAP_HOST` ve `EKITAP_MEDIA_ROOT` Blueprint (`render.yaml`) ile gelir; Blueprint kullanmıyorsanız elle girin:
   `EKITAP_HOST=ekitap.cinilisarayproje.com`, `EKITAP_MEDIA_ROOT=/var/ekran-medya/ekitap-medya`
   (mevcut kalıcı diskin alt klasörü — deploy'da dosyalar silinmez).
3. **Render → Settings → Custom Domains → Add Custom Domain:** `ekitap.cinilisarayproje.com`.
4. **Namecheap → Advanced DNS → Add New Record:**

   | Tür | Host | Değer | TTL |
   |-----|------|-------|-----|
   | **CNAME** | `ekitap` | `kitap-takip-premium-v6.onrender.com` | Automatic |

5. Render'da domain **Verified** olunca HTTPS sertifikası otomatik gelir (5–30 dk).
6. `https://ekitap.cinilisarayproje.com/yonetim/` → şifreyle girin → **Görüntüleme PIN'i** belirleyin →
   **+ Yeni kitap** ile PDF'leri yükleyin. Sayfalar arka planda görsele çevrilir (birkaç saniye–1 dk).
7. Tahtada `https://ekitap.cinilisarayproje.com/` açılır, PIN girilir. PIN oturumu tarayıcıda kalır;
   PIN'i değiştirirseniz tüm tahtalar yeniden PIN ister.

Yerelde deneme: `EKITAP_YONETICI_SIFRE=deneme python manage.py runserver` → `http://ekitap.localhost:8000/`.
