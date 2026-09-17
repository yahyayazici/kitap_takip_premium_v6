# Dijital Duyuru Ekranı — Kurulum, Kullanım ve Deployment

Kurumdaki televizyonlarda yayın yapan modül. Yönetim paneli ana site içinde
`/ekran/` altında, televizyon görüntüleyicisi ise `ekran.cinilisarayproje.com`
alt alan adının kökündedir.

---

## 1. Hızlı bakış

| Yüzey | Adres | Kimlik |
|-------|-------|--------|
| Pano (ana site) | `cinilisarayproje.com/ekran/` | Kurum hesabı |
| Pano (alt alan adı) | `ekran.cinilisarayproje.com/yonetim/` | Kurum hesabı (ayrı giriş) |
| Televizyon görüntüleyici | `ekran.cinilisarayproje.com/` | Cihaz anahtarı (giriş yok) |
| Cihaz API'si | `ekran.cinilisarayproje.com/api/cihaz/…` | `X-Ekran-Anahtar` başlığı |

> Oturum çerezi host'a özgüdür. Alt alan adında panele girmek isteyen kullanıcı
> orada bir kez daha giriş yapar. `SESSION_COOKIE_DOMAIN` **değiştirilmedi**;
> bu yüzden mevcut kullanıcıların ana paneldeki oturumları etkilenmez.

---

## 2. Canlıya alma adımları

### 2.1 DNS ve Render

`render.yaml` (Blueprint) şunları kendisi tanımlar:

* `ekran.cinilisarayproje.com` özel alan adı,
* `EKRAN_HOST` ve `EKRAN_MEDIA_ROOT` ortam değişkenleri,
* `/var/ekran-medya` yoluna bağlanan 10 GB kalıcı disk.

Blueprint senkronu çalıştığında Render bunları uygular; disk oluşturma
onayı panelden istenebilir.

**Elle yapılması gereken tek adım DNS'tir** — alan adı kaydı Render'ın
dışındadır. Namecheap → `cinilisarayproje.com` → **Advanced DNS**:

| Tür | Host | Değer | TTL |
|-----|------|-------|-----|
| CNAME | `ekran` | `kitap-takip-premium-v6.onrender.com` | Automatic |

Kayıt girildikten sonra Render → **Settings → Custom Domains** ekranında
`ekran.cinilisarayproje.com` satırı **Verified** olmalı; sertifika otomatik
gelir. Yayılma 5–30 dakika sürebilir.

Blueprint kullanılmıyorsa aynı üç şey panelden elle yapılır: Custom Domains'e
alan adı, Environment'a iki değişken, Disks'e `ekran-medya` diski.

### 2.2 Deploy

Yeni bağımlılık **tek**: `pypdfium2` (PDF sayfalarını sunucuda görsele çevirir).
Saf bir wheel'dir; ek apt paketi gerektirmez, Dockerfile değişmez.

`build.sh` ve `docker-start.sh` dosyalarına şu adım eklendi:

```bash
python manage.py seed_ekran_sablonlari
```

Bu komut sekiz yerleşik şablonu oluşturur/günceller ve tekrar tekrar
çalıştırılabilir.

### 2.3 Medya deposu — Render kalıcı diski

Ekran modülünün PDF/görsel/videoları **her zaman dosya sisteminde** durur;
projenin varsayılan deposu Cloudinary olsa bile. Gerekçe: Cloudinary ücretsiz
planında video 100 MB ile sınırlı ve bant genişliği krediyi hızla tüketiyor.
Diğer modüllerin deposuna dokunulmadı.

`render.yaml` şu tanımı içerir:

```yaml
    disk:
      name: ekran-medya
      mountPath: /var/ekran-medya
      sizeGB: 10
```

ve `EKRAN_MEDIA_ROOT=/var/ekran-medya` ortam değişkenini ayarlar.

**Blueprint kullanılmıyorsa** Render panelinden elle eklenmeli:
servis → **Settings → Disks → Add Disk** → ad `ekran-medya`,
mount path `/var/ekran-medya`, 10 GB. Ardından **Environment**'a
`EKRAN_MEDIA_ROOT=/var/ekran-medya` eklenir.

> Disk bağlı bir Render servisi tek örnekle çalışır. Starter planında zaten
> öyledir; ileride yatay ölçekleme gerekirse medya S3/R2 gibi bir nesne
> deposuna taşınmalıdır.

Dosyalar `/ekran-medya/...` adresinden, **byte-range destekli** bir uçtan
servis edilir (`takip/ekran_viewer_views.ekran_medyasi`). Django'nun kendi
`FileResponse`'u range desteklemez; akıllı televizyon tarayıcılarının çoğu
WebKit tabanlıdır ve `<video>` için 206 yanıtı bekler — range olmadan video
hiç başlamayabilir.

## 3. Yeni televizyon bağlama

1. Televizyonun tarayıcısında `ekran.cinilisarayproje.com` açılır, tam ekran yapılır.
2. Ekranda altı haneli bir kod belirir (15 dakika geçerli, tek kullanımlık).
3. Yönetim panelinde **Ekranlar → Ekran eşleştir**: kod, ekran adı ve kat girilir.
4. Ekran birkaç saniye içinde yayına geçer.

Kodun süresi dolarsa televizyon kendiliğinden yenisini gösterir; müdahale
gerekmez. Panelden **Ekranı yeniden yükle** denirse televizyon en geç bir
dakika içinde sayfayı tazeler.

---

## 4. Günlük kullanım — pano

Modüle girince doğrudan **pano** açılır: televizyonda görünecek ekranın
birebir aynısı olan bir tahta. Menüde yalnız iki başlık vardır (Pano ve
Ekranlar); liste/plan/kütüphane ekranları günlük kullanımda gerekmez.

**Akış üç adım:**

1. **Taslak seç** — boş tahtada "Neyle başlayalım?" kartları çıkar:
   tam ekran video, video + dikey afiş + alt söz, tam ekran sunum,
   sunum + dikey afiş, tam ekran söz, geri sayım, boş tahta.
2. **İçeriği koy** — video/afiş/PDF dosyasını doğrudan tahtaya sürükleyip
   bırak; bırakıldığı yere, kendi en-boy oranıyla yerleşir. Sonra fareyle
   taşı, köşelerden büyüt-küçült. Yazıyı tıklayıp değiştir.
3. **Ekranlara gönder** — tek düğme. Tüm ekranlar, seçtiğin ekranlar ya da
   kat seçilir. Televizyonlar en geç bir dakika içinde güncellenir.

Dosyası seçilmemiş bir video/afiş kutusu tahtada kesikli çerçeveyle görünür;
televizyona gitmez ve o hâliyle yayın çıkmaz (eksik dosya uyarısı verilir).

Pano gönderildikten sonra düzenlenirse üstte uyarı şeridi çıkar: ekranlarda
hâlâ eski hâli durur, yeni hâlin gitmesi için yeniden "Ekranlara gönder"
demek gerekir. Böylece yarım kalmış bir düzenleme ekrana düşmez.

### Arka planda ne oluyor?

Gönderme, veri modelindeki oynatma listesi + yayın planı katmanını kullanır;
ama bu kayıtlar panonun arkasında otomatik yönetilir (`__pano__<id>` adıyla)
ve kullanıcıya hiç gösterilmez. Zamanlama, öncelik ve çok sahneli akış
altyapısı yerinde durur — ileride "sınav haftası programı" gibi bir ihtiyaç
çıkarsa aynı modeller üzerinden kurulur.

### Gelişmiş ekranlar

Menüde yok ama adresleri çalışır ve yetkiye bağlıdır:

| Ekran | Adres |
|-------|-------|
| Özet / cihaz durumu | `/ekran/ozet/` |
| Tüm tasarımlar | `/ekran/tasarimlar/` |
| Çok sahneli stüdyo | `/ekran/tasarimlar/<id>/` |
| Oynatma listeleri | `/ekran/listeler/` |
| Yayın planları (tarih/saat/öncelik) | `/ekran/yayinlar/` |
| Medya kütüphanesi | `/ekran/medya/` |
| Geçmiş ve işlem kayıtları | `/ekran/gecmis/` |

## 5. Acil duyuru

**Acil Duyuru** sayfasından tek işlemle tüm ekranların, seçilen katların ya da
tek tek ekranların üzerine duyuru bindirilir. Ekranlar duyuruyu en geç bir
dakika içinde gösterir. **Kapat** denince normal yayına kaldıkları yerden
döner.

---

## 6. Teknik kararlar ve gerekçeleri

### 6.1 Neden WebSocket / SSE yok?

Sunucu Render'da **gunicorn WSGI** ile `2 worker × 2 thread` çalışıyor; yani
aynı anda dört isteğe bakabiliyor. WebSocket ya da SSE, her televizyon için bir
thread'i süresiz meşgul eder — dört televizyon tüm paneli kilitlerdi.

Bunun yerine **damga (stamp) tabanlı yoklama** kullanılıyor:

* Televizyon 10 saniyede bir `/api/cihaz/yoklama/` adresine küçük bir istek atar.
* Yanıt yalnızca bir SHA-256 damgası, acil duyuru durumu ve sunucu saatidir.
* Damga değişmedikçe **hiçbir içerik yeniden indirilmez**.
* Damga değişince televizyon paketi bir kez çeker ve önbelleğe alır.

Damga; yayın paketini, acil duyuruyu ve yeniden yükleme isteğini birlikte
özetler. Pratikte güncellemeler ekranlara 10 saniye içinde yansır.

Bağlantı koparsa yoklama aralığı üstel olarak 2 dakikaya kadar uzar; bağlantı
gelince hemen normale döner. Sonsuz yeniden yükleme döngüsü oluşmaz.

### 6.2 Neden PDF sunucuda görsele çevriliyor?

Televizyon sayfası günlerce açık kalır. Tarayıcıda PDF motoru çalıştırmak
(pdf.js) her sayfada yeniden render demektir: takılma ve bellek birikimi
riski yüksektir. Bunun yerine PDF, yüklenirken `pypdfium2` ile sayfa sayfa
PNG'ye çevrilir. Televizyon yalnız görsel oynatır — akıcı, öngörülebilir ve
çevrim dışı önbelleğe alınabilir.

Sayfalar **beyaz zemin üzerine** çizilir; aksi hâlde saydam PDF'ler koyu
sahnede siyah görünürdü. İlk 120 sayfa alınır.

### 6.3 Neden canvas kütüphanesi (Fabric/Konva) kullanılmadı?

Sahnede gerçek `<video>` öğesi, canlı saat ve akan yazı var; bunlar DOM
öğeleridir. Ayrıca stüdyo tuvalinin televizyon çıktısının **birebir** aynısı
olması isteniyordu. Bu yüzden tek bir render motoru (`static/ekran/js/engine.js`)
yazıldı; hem stüdyo hem televizyon aynı JSON'u aynı kodla çizer. Sonuç: sıfır
yeni JavaScript bağımlılığı.

### 6.4 Çözünürlük bağımsızlığı

Öğe konum ve ölçüleri **tasarım uzayında** (varsayılan 1920×1080) saklanır;
televizyon bunu `transform: scale()` ile kendi çözünürlüğüne oturtur. 1366×768,
1920×1080 ve 4K aynı veriyle bozulmadan çalışır. Tuval ölçüsü proje bazında
tutulduğu için dikey (1080×1920) ekran desteği veri modelini değiştirmeden
eklenebilir; tasarım oluştururken "Dikey ekran" seçeneği hâlihazırda vardır.

### 6.5 Çevrim dışı çalışma

Televizyon sayfası kök kapsamda bir service worker kaydeder
(`ekran.<domain>/sw.js`). Kabuk (HTML/CSS/JS) ve yayındaki medya dosyaları
önbelleğe alınır; en fazla 220 medya tutulur, en eskiler atılır. İnternet
kesilirse son yayın oynamaya devam eder, ekran boş kalmaz. API yanıtları
**asla** önbellekten verilmez — bayat bir yayın oynatılmaz.

Son yayın ayrıca `localStorage`'a yazılır; televizyon yeniden başlatılırsa ağ
gelmeden önce bile oynamaya başlar.

### 6.6 Veritabanı yükü

Nabız 10 saniyede bir gelir ama `EkranCihaz.son_baglanti` en fazla 30 saniyede
bir güncellenir. Olay tablosuna yalnız **durum değişimleri** yazılır (çevrim
içi/dışı geçişi, yeni yayın alımı, hata). Böylece 256 MB'lık Postgres gereksiz
yazma yüküyle dolmaz.

---

## 7. Güvenlik

* **Cihaz anahtarı**: 32 baytlık rastgele değer, televizyonun `localStorage`'ında
  durur, her istekte `X-Ekran-Anahtar` başlığıyla gider. Bir cihaz yalnız kendi
  yayınını görebilir.
* **Eşleştirme kodu**: 15 dakika geçerli, tek kullanımlık, karıştırılması kolay
  karakterler (0/O, 1/I) alfabede yok.
* **Kayıt sınırı**: bir IP saatte en çok 8 yeni eşleşmemiş cihaz kaydedebilir.
* **Dosya doğrulama**: uzantıya güvenilmez; her yüklemede içeriğin ilk baytları
  (magic number) kontrol edilir. Uzantı ile içerik uyuşmazsa dosya reddedilir.
  **SVG hiç kabul edilmez** — script barındırabilen tek görsel formatıdır.
* **XSS**: render motoru metni her zaman `textContent` ile yazar, `innerHTML`
  hiç kullanılmaz.
* **Silme koruması**: kullanımdaki medya dosyası silinemez (`on_delete=PROTECT`);
  panel hangi tasarımlarda kullanıldığını söyler.
* **Yetki**: mevcut RBAC'a `ekran` modülü olarak kayıtlı. İşlemler: `view`,
  `create`, `edit`, `delete`, `upload_media`, `manage_template`, `schedule`,
  `publish`, `emergency`, `manage_device`, `view_history`. Varsayılan olarak
  idareci, iç mesul ve eğitim mesulü rollerine açıktır; **Rol & Yetki Yönetimi**
  ekranından ayrıntılandırılabilir.

---

## 8. Dosya haritası

| Dosya | İçerik |
|-------|--------|
| `takip/ekran_models.py` | Tüm veri modeli |
| `takip/ekran_service.py` | Serileştirme, sürümleme, yayın derleme, zamanlama |
| `takip/ekran_media_service.py` | Yükleme, doğrulama, PDF sayfalama |
| `takip/ekran_views.py` | Yönetim paneli görünümleri |
| `takip/ekran_api_views.py` | Cihaz API'si |
| `takip/ekran_viewer_views.py` | Televizyon sayfası, service worker, QR |
| `takip/ekran_urls.py` | Panel adresleri (namespace: `ekran`) |
| `takip/ekran_viewer_urls.py` | Televizyon ve API adresleri |
| `config/ekran_urls.py` | Alt alan adının kök urlconf'u |
| `config/middleware.py` → `EkranHostMiddleware` | Host'a göre urlconf seçimi |
| `static/ekran/js/engine.js` | **Ortak render motoru** (stüdyo + televizyon) |
| `static/ekran/js/studyo.js` | Tasarım stüdyosu |
| `static/ekran/js/viewer.js` | Televizyon oynatıcısı |
| `static/ekran/js/viewer-sw.js` | Çevrim dışı service worker |
| `templates/ekran/` | Tüm şablonlar |
| `takip/tests/test_ekran_*.py` | Testler |

### Statik dosya sürümü

`takip/ekran_viewer_views.VARLIK_SURUMU` tek kaynaktır. Ekranın CSS/JS
dosyalarından biri değiştiğinde bu sabiti artırın: şablonlar `?v=` ekler,
service worker aynı adresleri ön belleğe alır ve televizyonlardaki eski
önbellek temizlenir.

---

## 9. Testler

```bash
python manage.py test takip.tests.test_ekran_medya
python manage.py test takip.tests.test_ekran_yayin
python manage.py test takip.tests.test_ekran_zamanlama
python manage.py test takip.tests.test_ekran_cihaz_api
python manage.py test takip.tests.test_ekran_sayfalar
```

Kapsam: dosya doğrulama ve XSS reddi, tekilleştirme, PDF sayfalama, sahne
kaydının gidiş-dönüşü, sürüm oluşturma/geri yükleme, yayın derleme ve damga
değişimi, taslak düzenlemesinin yayını bozmaması, kat/cihaz/tüm ekran
hedefleme, gün-saat-öncelik çözümlemesi, gece yarısını aşan aralık, acil
duyurunun yayını kesmesi ve kapanınca geri dönmesi, cihaz eşleştirme
(süre/tek kullanım/IP sınırı), yetkisiz kullanıcının yayın yapamaması ve
tüm sayfaların açılması.
