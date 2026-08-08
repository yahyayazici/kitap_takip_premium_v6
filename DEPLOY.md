# Çinili Saray Proje — Render + cinilisarayproje.com

Canlı panel: **https://cinilisarayproje.com**  
Render yedek adres: **https://kitap-takip-premium-v6.onrender.com**

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

## 8. İlk admin

Render Shell:

```bash
python manage.py createsuperuser
```
