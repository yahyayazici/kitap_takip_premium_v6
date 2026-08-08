# Kitap Takip Premium — Render yayın rehberi

## 1. GitHub'a gönder

Terminalde proje klasöründe:

```bash
git add .
git commit -m "Kitap Takip Premium marka ve Render yayın ayarları"
git push origin main
```

## 2. Render'da servis

1. https://render.com adresine gir, GitHub hesabını bağla.
2. **New +** → **Blueprint** (veya **Web Service**).
3. Repo: `yahyayazici/kitap_takip_premium_v6`
4. Branch: `main`
5. Blueprint kullanıyorsan `render.yaml` otomatik okunur:
   - Web servisi: `kitap-takip-premium-v6`
   - PostgreSQL: `kitap-takip-db`

## 3. Ortam değişkenleri (Render panel)

| Değişken | Değer |
|----------|--------|
| `DEBUG` | `False` |
| `SECRET_KEY` | Render otomatik üretir |
| `DATABASE_URL` | PostgreSQL bağlantısı (Blueprint ile gelir) |
| `PANEL_NAME` | `Kitap Takip Premium` |
| `PANEL_SHORT` | `Kitap Takip Premium` |
| `PANEL_PUBLIC_URL` | `https://kitap-takip-premium-v6.onrender.com` |

**Not:** `CUSTOM_DOMAIN` ve `CANONICAL_HOST` tanımlıysa Render panelinden silin; aksi halde cinilisarayproje.com yönlendirmesi devam eder.

## 4. İlk admin kullanıcı

Deploy bittikten sonra Render → **Shell**:

```bash
python manage.py createsuperuser
```

## 5. Canlı adres

`https://kitap-takip-premium-v6.onrender.com`

Bu adres otomatik `ALLOWED_HOSTS` ve CSRF ayarlarına eklenir.

## 6. Yerel geliştirme

`.env.example` dosyasını `.env` olarak kopyala ve yerel değerleri gir.

```bash
cp .env.example .env
python manage.py runserver
```
