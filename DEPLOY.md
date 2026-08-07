# Çinili Saray Proje — Render yayın rehberi

## 1. GitHub'a gönder

Terminalde proje klasöründe:

```bash
git add .
git commit -m "Çinili Saray Proje adı ve Render yayın ayarları"
git push origin feature/cinili-saray-panel
```

İstersen `main` branch'ine merge edip onu da push edebilirsin.

## 2. Render'da yeni servis

1. https://render.com adresine gir, GitHub hesabını bağla.
2. **New +** → **Blueprint** (veya **Web Service**).
3. Repo: `yahyayazici/kitap_takip_premium_v6`
4. Branch: `main` veya `feature/cinili-saray-panel`
5. Blueprint kullanıyorsan `render.yaml` otomatik okunur:
   - Web servisi: `cinili-saray-proje`
   - PostgreSQL: `cinili-saray-db`

## 3. Ortam değişkenleri (Render panel)

| Değişken | Değer |
|----------|--------|
| `DEBUG` | `False` |
| `SECRET_KEY` | Render otomatik üretir |
| `DATABASE_URL` | PostgreSQL bağlantısı (Blueprint ile gelir) |
| `PANEL_NAME` | `Çinili Saray Proje` |
| `PANEL_SHORT` | `Çinili Saray Proje` |

## 4. İlk admin kullanıcı

Deploy bittikten sonra Render → **Shell**:

```bash
python manage.py createsuperuser
```

## 5. Canlı adres

Render size şuna benzer bir adres verir:

`https://cinili-saray-proje.onrender.com`

Bu adres otomatik `ALLOWED_HOSTS` ve CSRF ayarlarına eklenir.

## 6. Yerel geliştirme

`.env.example` dosyasını `.env` olarak kopyala ve yerel değerleri gir.

```bash
cp .env.example .env
python manage.py runserver
```
