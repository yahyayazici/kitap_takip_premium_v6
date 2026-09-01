# Çinili Saray — Global UI / UX + Responsive Design System

**Durum:** Kalıcı anayasa  
**Kapsam:** Yalnızca görsel katman (HTML/CSS/UI JS görünümü)  
**Backend:** Dokunulmaz (modeller, views, urls, form field isimleri, POST/GET, yetki, veri, iş mantığı JS)

İlgili Cursor kuralı: `.cursor/rules/cinili-saray-ui.mdc`

---

## 1. Amaç

Cihaz cihaz / sayfa sayfa “yamalama” yerine tek tasarım sistemi:

1. Tutarlı marka, tipografi, boşluk, bileşenler  
2. Tüm panellerde aynı responsive davranış  
3. Geniş tablolarda kontrollü kaydırma + sabit başlık/sütun kalıbı  
4. Yeni ekranların anayasaya göre doğması  

---

## 2. Proje envanteri (özet)

| Katman | Ölçek |
|--------|------:|
| HTML template | ~302 |
| `static/css` | ~67 |
| `static/js` | ~27 |
| Base layout | 6 (personel, yönetim, öğretmen, veli, talebe, admin) + login/PDF/standalone |

### Base layout’lar

| Base | Body | Not |
|------|------|-----|
| `templates/base.html` | `v3-body` | Personel / etüt / genel panel |
| `templates/yonetim/base.html` | `yonetim-body` | Yönetim CRUD |
| `templates/ogretmen/base.html` | `ogretmen-body` | Öğretmen |
| `templates/veli/base.html` | `veli-body` | Veli |
| `templates/talebe/base.html` | `talebe-body` | Talebe |
| `templates/admin/base_site.html` | admin | Django admin cilt |
| Login / sınav başvuru / PDF | ayrı | Sistem dışı veya izole |

### Ekran aileleri

- Dashboard: personel, yönetim, öğretmen, veli, talebe  
- Personel modülleri: namaz, dini ders, etüt plan, dershane, rehberlik, temizlik, yemek, YÇT, vazife, …  
- Yönetim listeleri / formları  
- Raporlar (web) + PDF (izole)  
- Duyuru carousel + veli duyurular  
- Modal: etüt, dershane, KTT, temizlik  
- Dropdown: nav-groups, multi-select, bildirim zili  

---

## 3. CSS yükleme sırası (kanun)

Tüm panel base’lerinde hedef sıra:

1. Legacy shell (`app.css` / `yonetim.css`, topnav, v5, v6, nav-groups, dashboard-home, panel-unified, …)  
2. `cs-design-tokens.css` — **tek token kaynağı**  
3. `cs-design-constitution.css` + `cs-design-phase2…6`  
4. `{% block extra_css %}` — sayfa/modül CSS  
5. `cs-design-phase7.css` + `cs-design-phase8.css`  
6. **`cs-ui-system.css`** — son söz (alias, gutter, overflow, form/btn birliği)

Yeni global kural: tokens veya `cs-ui-system.css`.  
Yeni sayfa stili: `extra_css` modül dosyası; token’a bağla.

**Dondurulmuş (genişletme yok):** `premium-system-v4/v5/v6`, dağınık phase dosyalarına yeni özellik ekleme — uyumluluk için kalır, kanun `cs-ui-system`.

**İzole (zorunlu birleştirme yok):** `login-portal.css`, `sinav-basvuru.css`, `pdf-karne-a4.css` ve diğer PDF şablonları.

---

## 4. Design tokens

Dosya: `static/css/cs-design-tokens.css`

### Renk

| Token | Rol |
|-------|-----|
| `--cs-primary` / `--cs-primary-dark` | Marka navy |
| `--cs-accent` | Aksiyon mavisi |
| `--cs-background` / `--cs-surface` | Sayfa / kart |
| `--cs-border` | Çizgi |
| `--cs-text-primary` / `--secondary` / `--muted` | Metin |
| `--cs-success` / `--warning` / `--danger` / `--info` | Durum |

### Boşluk & layout

- `--cs-space-1` … `--cs-space-10` (4 → 64px)  
- `--cs-page-gutter`: `clamp(14px, 2.2vw, 28px)`  
- `--cs-section-gap`: `clamp(18px, 2.5vw, 28px)`  
- `--cs-content-wide`: max içerik genişliği  

### Radius & gölge

- `--cs-radius-sm|md|lg|xl|pill`  
- `--cs-shadow-xs|sm|md|lg|card|focus`  

### Tipografi

- Font: `--cs-font` (Poppins stack)  
- Başlık / gövde / caption clamp’leri tokens içinde  

### Bileşen

- `--cs-btn-h: 44px`, `--cs-input-h: 44px`, `--cs-touch-min: 44px`  

### Breakpoint token’ları

```css
--cs-bp-sm: 640px;
--cs-bp-md: 900px;
--cs-bp-lg: 1100px;
--cs-bp-nav: 1400px;
```

*(Media query içinde `var()` sınırlı destek — pratikte aynı px değerlerini kullan.)*

### Geriye dönük köprü

`--v6-*`, `--dash-*`, `--v5-*` → `--cs-*` map edilir.  
`panel-unified` vb. yeniden tanımlarsa `cs-ui-system.css` tekrar `--cs-*` lehine hizalar.

---

## 5. Bileşen standardı

### 5.1 Butonlar

| Rol | Tercih sınıf | Alias’lar (görsel eş) |
|-----|--------------|------------------------|
| Primary | `.primary-btn` | `.btn-primary`, `.cs-btn-primary` |
| Ghost | `.ghost-btn` | `.btn-ghost`, `.yonetim-head-ghost`, `.small-button` |
| Danger | `.btn-danger` | ilgili danger action sınıfları |

Kurallar: min-height 44px, radius `var(--cs-radius-md)`, tek satır metin, ikon+metin gap `var(--cs-space-2)`.

### 5.2 Sayfa başlığı

`.page-head`, `.patterned-page-head`, `.yonetim-page-head`, `.welcome-panel`  
Navy/hero yüzeyi; action butonları sağda wrap; mobilde kolon.

### 5.3 Kart

Beyaz yüzey, border `var(--cs-border)`, radius `var(--cs-radius-lg)`, gölge `var(--cs-shadow-sm|card)`.  
Padding `var(--cs-density-card-pad)`.

### 5.4 Form

- Label üstte, kontrol full width  
- Grid: masaüstü 2 kolon, ≤900px 2→1, ≤640px 1  
- Select mobilde `font-size: 16px`  
- **Field `name` değiştirilmez**

### 5.5 Tablo

- Wrap: `.responsive-table`, `.cs-table-wrap`, veya modül `*-wrap`  
- Wrap: `overflow: auto`, `max-width: 100%`, `overscroll-behavior: contain`  
- Sayfa: yatay kayma yok  
- Sticky isim/konu: wrap scrollport + CSS sticky ve/veya JS freeze (dini ders kalıbı)

### 5.6 Modal / popover / toast

| Kalıp | Seçici / API |
|-------|----------------|
| Etüt modal | `[data-ep-modal]` |
| Dershane modal | `[data-dp-modal]` |
| Temizlik modal | `[data-tz-modal]` |
| KTT modal | `#ktt-form-modal` |
| Bildirim | `bildirim-bell.js` |
| Toast | `[data-v3-toasts]` / `.v3-toast` |
| Nav dropdown | `nav-dropdown.js` |
| Multi-select | `multi-select-filter.js` |

JS API bozulmaz; yalnızca CSS ile hizalanır.

### 5.7 Duyuru & dashboard

- Duyuru: `duyuru-carousel`  
- Personel üst split: duyuru | YÇT (`personel-dash-split`)  
- Hızlı menü / metrik: mevcut includes  

---

## 6. Responsive kurallar

| Genişlik | Davranış |
|----------|----------|
| ≤640 | Tek kolon form; tablo wrap kaydırma; nav hamburger |
| ≤900 | 2→1 grid; tablet dikey |
| ≤1100 | Sidebar/aside alta inebilir |
| ≤1400 | Üst nav collapse (`--cs-bp-nav`) |

Landscape mobilde: tablo wrap `max-height` düşürülür; isim sütunu daraltılır — sayfa boşluğa kaymaz.

---

## 7. Overflow & sticky politikası

1. `body` / `.v3-main` / `.page-content`: `overflow-x: clip` (sayfa kaymasın).  
2. Geniş içerik: sadece iç wrap `overflow: auto`.  
3. Sticky bozulursa: sayfayı `overflow-x: visible` yaparak tüm viewport’u kaydırma — **yasak**. Freeze JS veya wrap içi sticky kullan.  
4. Modül örneği: `dini-ders-premium` + matrix freeze; `dershane-program-premium`.

---

## 8. Modül CSS köprüsü

Modül dosyaları (`*-premium.css`) yerel değişken kullanabilir; değerler `--cs-*` olmalı:

```css
.dd-page {
  --dd-navy: var(--cs-primary-dark);
  --dd-line: var(--cs-border-subtle);
  --dd-text: var(--cs-text-primary);
  --dd-muted: var(--cs-text-muted);
  --dd-radius: var(--cs-radius-lg);
}
```

`cs-ui-system.css` yaygın modül kökleri için bu alias’ları toplu uygular.

---

## 9. Tipografi & hareket

- Panel fontu: Poppins (`--cs-font`)  
- Login / sınav başvuru kendi fontunu tutabilir  
- Motion: `--cs-transition`; `prefers-reduced-motion` saygı  
- Yeni ekranda Comfortaa/Cormorant zorunlu değil  

---

## 10. Erişilebilirlik & dokunma

- İnteraktif min 44×44px  
- Kontrast: metin `--cs-text-primary` yüzey üzerinde  
- Focus: `--cs-shadow-focus`  
- İkon-only butonlarda `aria-label` korunur  

---

## 11. Yapılmayacaklar

- Backend / form name / URL değişikliği  
- Yeni mor/cream “AI landing” teması  
- Sayfa düzeyinde yatay kaydırma ile boşluk  
- Her sayfaya özel breakpoint ormanı  
- Template’lerde sınıf isimlerini toplu rename (önce CSS alias)  

---

## 12. Uygulama durumu

| Adım | Durum |
|------|--------|
| Token dosyası | Var (`cs-design-tokens.css`) |
| Cursor kuralı | `.cursor/rules/cinili-saray-ui.mdc` |
| Bu belge | `docs/UI_DESIGN_SYSTEM.md` |
| Son katman | `static/css/cs-ui-system.css` — tüm base’lere bağlı |
| Modül alias | `cs-ui-system` içinde toplu |
| Login/PDF | İzole bırakıldı |

---

## 13. Yeni ekran checklist

1. Doğru base’i extend et  
2. `extra_css` ile modül CSS; renkleri `--cs-*`  
3. Başlık + içerik gap `var(--cs-section-gap)`  
4. Tablo varsa wrap + overflow auto  
5. ≤640 / ≤900 / yatay kontrol  
6. Backend’e dokunma  

---

## 14. Bakım

- Token değişikliği → `cs-design-tokens.css` + cache bust  
- Global bileşen kuralı → `cs-ui-system.css`  
- Phase1–8’e yeni özellik ekleme; borç öde  
- Çakışma: tarayıcıda computed style; kazanan genelde `cs-ui-system` (en sonda)
