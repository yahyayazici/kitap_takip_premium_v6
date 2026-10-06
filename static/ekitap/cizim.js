/* E-Kitap — geçici çizim: kalem, fosforlu kalem, silgi, perde, çözüm alanı.
 *
 * GİZLİLİK: Çizimler hiçbir kalıcı depolamaya yazılmaz (sunucu, veritabanı,
 * localStorage, sessionStorage, IndexedDB yok). Yalnızca bu sayfanın
 * belleğinde, açık soru oturumu boyunca tutulur:
 *   - sorular arasında geçerken her sorunun çizimi korunur,
 *   - soru görünümü kapatılınca (çizim varsa onay sorulur) hepsi silinir,
 *   - kitap görünümündeki çizim modu bitince çizimler silinir,
 *   - sayfa yenilenince doğal olarak kaybolur.
 *
 * Çizimler SVG vektörüdür ve kâğıt koordinatlarında saklanır; yakınlaştırma,
 * kaydırma ve ekran boyutu değişse de sorunun üstünde aynı yerde kalır.
 */
(function () {
    'use strict';

    var SVGNS = 'http://www.w3.org/2000/svg';
    var RENKLER = { siyah: '#14181F', mavi: '#1E5BD6', kirmizi: '#D2232A' };
    var KALINLIK_PX = { ince: 2.5, orta: 4.5, kalin: 8 }; // sığdırılmış görünümde ekran pikseli
    var FOSFOR_PX = 24;
    var FOSFOR_RENK = '#FFD400';
    var SILGI_PX = 16;
    var IPTAL_SURESI = 350; // ms: ikinci parmak bu süre içinde gelirse çizgi yok sayılır
    var IPTAL_UZUNLUK_PX = 40;

    function el(ad, oz) {
        var e = document.createElementNS(SVGNS, ad);
        for (var k in oz) if (Object.prototype.hasOwnProperty.call(oz, k)) e.setAttribute(k, oz[k]);
        return e;
    }

    function yolVerisi(n) {
        if (!n.length) return '';
        if (n.length === 1) return 'M' + n[0][0] + ' ' + n[0][1] + 'l0.01 0';
        var d = 'M' + n[0][0].toFixed(1) + ' ' + n[0][1].toFixed(1);
        for (var i = 1; i < n.length - 1; i++) {
            var mx = (n[i][0] + n[i + 1][0]) / 2;
            var my = (n[i][1] + n[i + 1][1]) / 2;
            d += 'Q' + n[i][0].toFixed(1) + ' ' + n[i][1].toFixed(1) + ' ' + mx.toFixed(1) + ' ' + my.toFixed(1);
        }
        var son = n[n.length - 1];
        return d + 'L' + son[0].toFixed(1) + ' ' + son[1].toFixed(1);
    }

    function noktaDoğruUzaklik(px, py, a, b) {
        var dx = b[0] - a[0], dy = b[1] - a[1];
        var l2 = dx * dx + dy * dy;
        var t = l2 ? Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / l2)) : 0;
        return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy));
    }

    /* —— Çizim yüzeyi ———————————————————————————————————————————————————
     * ayar.nokta(clientX, clientY) → {x, y} (yüzey birimi)
     * ayar.ekranBirim()  → şu anki 1 ekran pikseli kaç yüzey birimi (yakınlaştırma dahil)
     * ayar.sigdirBirim() → sığdırılmış görünümde 1 ekran pikseli kaç yüzey birimi
     */
    function Yuzey(svg, ayar) {
        this.svg = svg;
        this.ayar = ayar;
        this.katman = el('g', { 'class': 'ek-cizim-ogeler' });
        svg.appendChild(this.katman);
        this.ogeler = [];
        this.gecmis = [];
        this.ileri = [];
        this.aktif = null;
    }

    Yuzey.prototype.cizgiVarMi = function () {
        return this.ogeler.some(function (o) { return o.tur === 'cizgi'; });
    };

    Yuzey.prototype._ekle = function (o) {
        this.ogeler.push(o);
        // Şık perdesi en altta durur: öğretmenin üstüne yazdıkları görünür kalır.
        if (o.ozel === 'siklar') this.katman.insertBefore(o.el, this.katman.firstChild);
        else this.katman.appendChild(o.el);
    };

    Yuzey.prototype._cikar = function (o) {
        var i = this.ogeler.indexOf(o);
        if (i >= 0) this.ogeler.splice(i, 1);
        if (o.el.parentNode) o.el.parentNode.removeChild(o.el);
    };

    Yuzey.prototype._kaydet = function (islem) {
        this.gecmis.push(islem);
        this.ileri = [];
        this._degisti();
    };

    Yuzey.prototype._degisti = function () {
        if (this.ayar.degisti) this.ayar.degisti();
    };

    Yuzey.prototype._noktalar = function (e) {
        var liste = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
        if (!liste || !liste.length) liste = [e];
        var self = this;
        return liste.map(function (k) {
            var p = self.ayar.nokta(k.clientX, k.clientY);
            return [p.x, p.y];
        });
    };

    Yuzey.prototype.perdeBul = function (x, y) {
        for (var i = this.ogeler.length - 1; i >= 0; i--) {
            var o = this.ogeler[i];
            if (o.tur === 'perde' && x >= o.x && x <= o.x + o.w && y >= o.y && y <= o.y + o.h) return o;
        }
        return null;
    };

    Yuzey.prototype.perdeOlustur = function (x, y, w, h, ozel) {
        var b = this.ayar.sigdirBirim();
        var g = el('g', { 'class': 'ek-perde' + (ozel ? ' ek-perde-' + ozel : '') });
        g.appendChild(el('rect', {
            x: x, y: y, width: w, height: h, rx: 6 * b,
            'stroke-width': 2 * b, 'stroke-dasharray': (8 * b) + ' ' + (6 * b)
        }));
        var yazi = el('text', {
            x: x + w / 2, y: y + h / 2, 'text-anchor': 'middle', 'dominant-baseline': 'central',
            'font-size': Math.min(h * 0.32, 20 * b)
        });
        yazi.textContent = ozel === 'siklar' ? 'Şıklar gizli · açmak için dokunun' : 'Gizli · açmak için dokunun';
        g.appendChild(yazi);
        return { tur: 'perde', x: x, y: y, w: w, h: h, el: g, ozel: ozel || '' };
    };

    Yuzey.prototype.basla = function (e, arac, ayarlar) {
        var p = this.ayar.nokta(e.clientX, e.clientY);
        var b = this.ayar.sigdirBirim();
        var simdi = Date.now();
        if (arac === 'kalem' || arac === 'fosfor') {
            var fosfor = arac === 'fosfor';
            var gen = (fosfor ? FOSFOR_PX : KALINLIK_PX[ayarlar.kalinlik] || KALINLIK_PX.orta) * b;
            var yol = el('path', {
                'class': fosfor ? 'ek-cizgi ek-cizgi-fosfor' : 'ek-cizgi',
                stroke: fosfor ? FOSFOR_RENK : (RENKLER[ayarlar.renk] || RENKLER.mavi),
                'stroke-width': gen
            });
            var cizgi = { tur: 'cizgi', noktalar: [[p.x, p.y]], gen: gen, el: yol };
            yol.setAttribute('d', yolVerisi(cizgi.noktalar));
            this.katman.appendChild(yol);
            this.aktif = { tur: 'cizgi', id: e.pointerId, oge: cizgi, t0: simdi, uzunluk: 0 };
        } else if (arac === 'silgi') {
            this.aktif = { tur: 'silgi', id: e.pointerId, silinen: [] };
            this._sil(p.x, p.y);
        } else if (arac === 'perde') {
            var var_olan = this.perdeBul(p.x, p.y);
            this.aktif = { tur: 'perde', id: e.pointerId, bas: p, hedef: var_olan, onizleme: null, t0: simdi };
        } else if (arac === 'el') {
            var acilacak = this.perdeBul(p.x, p.y);
            if (!acilacak) return false;
            this.aktif = { tur: 'perde-ac', id: e.pointerId, bas: p, hedef: acilacak };
        } else {
            return false;
        }
        return true;
    };

    Yuzey.prototype.surdur = function (e) {
        var a = this.aktif;
        if (!a || a.id !== e.pointerId) return;
        var yeni = this._noktalar(e);
        if (a.tur === 'cizgi') {
            var n = a.oge.noktalar;
            yeni.forEach(function (q) {
                var son = n[n.length - 1];
                var d = Math.hypot(q[0] - son[0], q[1] - son[1]);
                if (d > 0.4 * a.oge.gen / 4) {
                    n.push(q);
                    a.uzunluk += d;
                }
            });
            a.oge.el.setAttribute('d', yolVerisi(n));
        } else if (a.tur === 'silgi') {
            var self = this;
            yeni.forEach(function (q) { self._sil(q[0], q[1]); });
        } else if (a.tur === 'perde') {
            var q = yeni[yeni.length - 1];
            var x = Math.min(a.bas.x, q[0]), y = Math.min(a.bas.y, q[1]);
            var w = Math.abs(q[0] - a.bas.x), h = Math.abs(q[1] - a.bas.y);
            if (!a.onizleme) {
                a.onizleme = el('rect', { 'class': 'ek-perde-onizleme' });
                this.katman.appendChild(a.onizleme);
            }
            a.onizleme.setAttribute('x', x);
            a.onizleme.setAttribute('y', y);
            a.onizleme.setAttribute('width', w);
            a.onizleme.setAttribute('height', h);
            a.son = { x: x, y: y, w: w, h: h };
        }
    };

    Yuzey.prototype._sil = function (x, y) {
        var r = SILGI_PX * this.ayar.ekranBirim();
        for (var i = this.ogeler.length - 1; i >= 0; i--) {
            var o = this.ogeler[i];
            if (o.tur !== 'cizgi') continue;
            var n = o.noktalar, sinir = r + o.gen / 2, vurdu = false;
            if (n.length === 1) vurdu = Math.hypot(x - n[0][0], y - n[0][1]) <= sinir;
            for (var j = 1; j < n.length && !vurdu; j++) {
                if (noktaDoğruUzaklik(x, y, n[j - 1], n[j]) <= sinir) vurdu = true;
            }
            if (vurdu) {
                this._cikar(o);
                this.aktif.silinen.push(o);
            }
        }
    };

    Yuzey.prototype.bitir = function (e) {
        var a = this.aktif;
        if (!a || (e && a.id !== e.pointerId)) return;
        this.aktif = null;
        var esik = 10 * this.ayar.ekranBirim();
        if (a.tur === 'cizgi') {
            a.oge.el.parentNode.removeChild(a.oge.el);
            this._ekle(a.oge);
            this._kaydet({ tur: 'ekle', ogeler: [a.oge] });
        } else if (a.tur === 'silgi') {
            if (a.silinen.length) this._kaydet({ tur: 'sil', ogeler: a.silinen });
        } else if (a.tur === 'perde') {
            if (a.onizleme && a.onizleme.parentNode) a.onizleme.parentNode.removeChild(a.onizleme);
            if (a.son && a.son.w > esik && a.son.h > esik) {
                var perde = this.perdeOlustur(a.son.x, a.son.y, a.son.w, a.son.h);
                this._ekle(perde);
                this._kaydet({ tur: 'ekle', ogeler: [perde] });
            } else if (a.hedef) {
                this._perdeAc(a.hedef);
            }
        } else if (a.tur === 'perde-ac') {
            this._perdeAc(a.hedef);
        }
    };

    Yuzey.prototype._perdeAc = function (perde) {
        this._cikar(perde);
        if (perde.ozel === 'siklar') {
            this._degisti();
            return;
        }
        this._kaydet({ tur: 'sil', ogeler: [perde] });
    };

    /* İkinci parmak geldi: yeni başlamış çizgi yanlışlıkla çizilmiştir, sil.
     * Uzun bir çizgiyse olduğu gibi bırak. */
    Yuzey.prototype.iptal = function () {
        var a = this.aktif;
        if (!a) return;
        var px = a.uzunluk / Math.max(this.ayar.ekranBirim(), 1e-6);
        if (a.tur === 'cizgi' && (Date.now() - a.t0 < IPTAL_SURESI || px < IPTAL_UZUNLUK_PX)) {
            if (a.oge.el.parentNode) a.oge.el.parentNode.removeChild(a.oge.el);
            this.aktif = null;
            return;
        }
        if (a.tur === 'perde') {
            if (a.onizleme && a.onizleme.parentNode) a.onizleme.parentNode.removeChild(a.onizleme);
            this.aktif = null;
            return;
        }
        if (a.tur === 'perde-ac') {
            this.aktif = null;
            return;
        }
        this.bitir(null);
    };

    Yuzey.prototype.geriAl = function () {
        var islem = this.gecmis.pop();
        if (!islem) return;
        var self = this;
        if (islem.tur === 'ekle') islem.ogeler.forEach(function (o) { self._cikar(o); });
        else islem.ogeler.forEach(function (o) { self._ekle(o); });
        this.ileri.push(islem);
        this._degisti();
    };

    Yuzey.prototype.ileriAl = function () {
        var islem = this.ileri.pop();
        if (!islem) return;
        var self = this;
        if (islem.tur === 'ekle') islem.ogeler.forEach(function (o) { self._ekle(o); });
        else islem.ogeler.forEach(function (o) { self._cikar(o); });
        this.gecmis.push(islem);
        this._degisti();
    };

    /* Tümünü temizle — tek adımda geri alınabilir. */
    Yuzey.prototype.temizle = function () {
        var silinecek = this.ogeler.filter(function (o) { return o.ozel !== 'siklar'; });
        if (!silinecek.length) return;
        var self = this;
        silinecek.forEach(function (o) { self._cikar(o); });
        this._kaydet({ tur: 'temizle', ogeler: silinecek });
    };

    /* Soru değişirken: bu sorunun durumunu bellekte al, yüzeyi boşalt. */
    Yuzey.prototype.disaAl = function () {
        if (this.aktif) this.iptal();
        var durum = { ogeler: this.ogeler, gecmis: this.gecmis, ileri: this.ileri };
        this.ogeler.forEach(function (o) { if (o.el.parentNode) o.el.parentNode.removeChild(o.el); });
        this.ogeler = [];
        this.gecmis = [];
        this.ileri = [];
        return durum;
    };

    Yuzey.prototype.iceAl = function (durum) {
        this.disaAl();
        if (!durum) { this._degisti(); return; }
        var self = this;
        durum.ogeler.forEach(function (o) { self._ekle(o); });
        this.gecmis = durum.gecmis;
        this.ileri = durum.ileri;
        this._degisti();
    };

    Yuzey.prototype.sifirla = function () {
        this.aktif = null;
        this.disaAl();
        while (this.katman.firstChild) this.katman.removeChild(this.katman.firstChild);
        this._degisti();
    };

    /* —— Araç çubuğu ve oturumlar ———————————————————————————————————————— */
    var okuyucu = document.getElementById('okuyucu');
    var cubuk = document.getElementById('araclar');
    if (!okuyucu || !cubuk) return;
    var kalemAyar = document.getElementById('kalemAyar');
    var cozumAyar = document.getElementById('cozumAyar');
    var onayKutusu = document.getElementById('onayKutusu');
    var onayMetni = document.getElementById('onayMetni');
    var kalemNokta = document.getElementById('kalemRenkNokta');
    var kitapSvg = document.getElementById('kitapCizim');
    var kitapKap = document.getElementById('kitap');
    var kitapBtn = document.getElementById('kitapCizimBtn');
    var soruSvg = document.getElementById('soruCizim');
    var SG = window.EKitapSoru;

    var durum = { arac: 'kalem', renk: 'mavi', kalinlik: 'orta' };
    var mod = null; // 'soru' | 'kitap'
    var yuzey = null;
    var kalemGoruldu = false; // cihaz kalem ucu destekliyor: kalem çizer, parmak kaydırır
    var kalemBasili = false;

    function aracDugmeleri() { return cubuk.querySelectorAll('[data-arac]'); }

    function cubuguGuncelle() {
        Array.prototype.forEach.call(aracDugmeleri(), function (b) {
            b.setAttribute('aria-pressed', b.getAttribute('data-arac') === durum.arac ? 'true' : 'false');
        });
        if (kalemNokta) kalemNokta.style.background = RENKLER[durum.renk];
        Array.prototype.forEach.call(kalemAyar.querySelectorAll('[data-renk]'), function (b) {
            b.setAttribute('aria-pressed', b.getAttribute('data-renk') === durum.renk ? 'true' : 'false');
        });
        Array.prototype.forEach.call(kalemAyar.querySelectorAll('[data-kalinlik]'), function (b) {
            b.setAttribute('aria-pressed', b.getAttribute('data-kalinlik') === durum.kalinlik ? 'true' : 'false');
        });
        var geri = cubuk.querySelector('[data-eylem="geri"]');
        var ileri = cubuk.querySelector('[data-eylem="ileri"]');
        var temizle = cubuk.querySelector('[data-eylem="temizle"]');
        geri.disabled = !yuzey || !yuzey.gecmis.length;
        ileri.disabled = !yuzey || !yuzey.ileri.length;
        temizle.disabled = !yuzey || !yuzey.ogeler.some(function (o) { return o.ozel !== 'siklar'; });
        var sik = cubuk.querySelector('[data-eylem="siklar"]');
        sik.setAttribute('aria-pressed', siklarGizliMi() ? 'true' : 'false');
        okuyucu.classList.toggle('ek-arac-el', durum.arac === 'el');
        okuyucu.setAttribute('data-cizim-araci', mod ? durum.arac : '');
    }

    function acilirlariKapat() {
        kalemAyar.hidden = true;
        cozumAyar.hidden = true;
    }

    function acilirAc(kutu, dugme) {
        var acik = !kutu.hidden;
        acilirlariKapat();
        if (acik) return;
        var r = dugme.getBoundingClientRect();
        var cr = cubuk.getBoundingClientRect();
        kutu.hidden = false;
        kutu.style.left = (cr.right + 12) + 'px';
        var ust = Math.max(12, Math.min(r.top, window.innerHeight - kutu.offsetHeight - 12));
        kutu.style.top = ust + 'px';
    }

    var bildiriZamani = null;
    function bildir(metin) {
        var b = document.getElementById('cizimBildiri');
        if (!b) {
            b = document.createElement('p');
            b.id = 'cizimBildiri';
            b.className = 'ek-cizim-bildiri';
            b.setAttribute('role', 'status');
            document.body.appendChild(b);
        }
        b.textContent = metin;
        b.classList.add('ek-gorunur');
        clearTimeout(bildiriZamani);
        bildiriZamani = setTimeout(function () { b.classList.remove('ek-gorunur'); }, 3800);
    }

    var onayDevam = null;
    function onayIste(metin, devam) {
        onayMetni.textContent = metin;
        onayDevam = devam;
        onayKutusu.hidden = false;
        document.getElementById('onayVazgec').focus({ preventScroll: true });
    }
    function onayKapat(tamam) {
        onayKutusu.hidden = true;
        var devam = onayDevam;
        onayDevam = null;
        if (tamam && devam) devam();
    }
    document.getElementById('onayVazgec').addEventListener('click', function () { onayKapat(false); });
    document.getElementById('onayTamam').addEventListener('click', function () { onayKapat(true); });
    onayKutusu.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { e.stopPropagation(); onayKapat(false); }
    });

    // —— Ortak işaretçi kuralları (avuç içi / kalem ucu) ——————————————————
    function avucMu(e) {
        // Kalem ucu tahtaya değerken gelen dokunmalar avuç içidir.
        return e.pointerType === 'touch' && kalemBasili;
    }

    // Soru görünümünde kâğıdın (ve çözüm alanının) dışındaki dokunuş çizmez; kaydırır.
    function kagittaMi(e) {
        if (mod !== 'soru') return true;
        var r = soruSvg.getBoundingClientRect();
        var pay = 28;
        return e.clientX >= r.left - pay && e.clientX <= r.right + pay &&
            e.clientY >= r.top - pay && e.clientY <= r.bottom + pay;
    }

    function cizimeBasla(e) {
        if (!yuzey) return false;
        if (!kagittaMi(e)) {
            acilirlariKapat();
            return false;
        }
        if (e.pointerType === 'pen') {
            kalemGoruldu = true;
            kalemBasili = true;
        }
        var arac = durum.arac;
        // Kalem ucu olan tahtada parmak çizmez, kaydırır (perdeye dokunarak açma hariç).
        if (e.pointerType === 'touch' && kalemGoruldu && arac !== 'el') arac = 'el';
        acilirlariKapat();
        return yuzey.basla(e, arac, durum);
    }

    function cizimiBitir(e) {
        if (e && e.pointerType === 'pen') kalemBasili = false;
        if (yuzey) yuzey.bitir(e);
    }

    // —— Soru görünümü —————————————————————————————————————————————————
    var soruYuzey = null;
    var oturum = {}; // soru indeksi → { durum, ekAlan, siklar }
    var siklarGizli = false;

    function siklarGizliMi() {
        return mod === 'soru' && soruYuzey && soruYuzey.ogeler.some(function (o) { return o.ozel === 'siklar'; });
    }

    if (SG && soruSvg) {
        soruYuzey = new Yuzey(soruSvg, {
            nokta: function (cx, cy) { return SG.kagitNoktasi(cx, cy); },
            ekranBirim: function () {
                var r = soruSvg.getBoundingClientRect();
                return r.width ? SG.olcu.w / r.width : 1;
            },
            sigdirBirim: function () { return 1 / (SG.olcu.olcek || 1); },
            degisti: cubuguGuncelle
        });

        SG.cizimBagla({
            basla: cizimeBasla,
            surdur: function (e) { if (yuzey) yuzey.surdur(e); },
            bitir: cizimiBitir,
            iptal: function () { if (yuzey) yuzey.iptal(); },
            avucMu: avucMu,
            ciziyorMu: function () { return durum.arac !== 'el'; }
        });

        SG.kok.addEventListener('ek-soru-acildi', function () {
            if (mod === 'kitap') kitapModunuKapat(true);
            mod = 'soru';
            yuzey = soruYuzey;
            oturum = {};
            cubuk.classList.add('ek-mod-soru');
            cubuk.classList.remove('ek-mod-kitap');
            cubuk.hidden = false;
            cubuguGuncelle();
        });

        SG.kok.addEventListener('ek-soru-degisecek', function (e) {
            var d = e.detail;
            if (d.onceki >= 0) {
                oturum[d.onceki] = { durum: soruYuzey.disaAl(), ekAlan: SG.ekAlan() };
            }
            var kayit = oturum[d.simdi];
            SG.ekAlanAyarla(kayit ? kayit.ekAlan : { alt: 0, sag: 0 }, true);
        });

        SG.kok.addEventListener('ek-soru-degisti', function (e) {
            var kayit = oturum[e.detail.simdi];
            soruYuzey.iceAl(kayit ? kayit.durum : null);
            delete oturum[e.detail.simdi];
            cubuguGuncelle();
        });

        SG.kok.addEventListener('ek-soru-kapandi', function () {
            soruYuzey.sifirla();
            oturum = {};
            acilirlariKapat();
            if (mod === 'soru') {
                mod = null;
                yuzey = null;
                cubuk.hidden = true;
            }
            cubuguGuncelle();
        });

        SG.kapatmaOnayiAyarla(function (devam) {
            var cizimVar = soruYuzey.cizgiVarMi() || Object.keys(oturum).some(function (k) {
                return oturum[k].durum.ogeler.some(function (o) { return o.tur === 'cizgi'; });
            });
            if (!cizimVar) return true;
            onayIste('Çizimler silinecek. Soru görünümü kapatılsın mı?', devam);
            return false;
        });
    }

    function siklariDegistir() {
        if (mod !== 'soru' || !soruYuzey) return;
        var mevcut = soruYuzey.ogeler.filter(function (o) { return o.ozel === 'siklar'; })[0];
        if (mevcut) {
            soruYuzey._cikar(mevcut);
            cubuguGuncelle();
            return;
        }
        var k = SG.sikKutusu();
        if (!k) {
            durum.arac = 'perde';
            cubuguGuncelle();
            bildir('Bu soruda şıklar otomatik bulunamadı. Örtmek istediğiniz bölgeyi perde aracıyla sürükleyerek seçin.');
            return;
        }
        var perde = soruYuzey.perdeOlustur(k.x, k.y, k.w, k.h, 'siklar');
        soruYuzey._ekle(perde);
        cubuguGuncelle();
    }

    function cozumAlani(yon) {
        if (mod !== 'soru') return;
        var ek = SG.ekAlan();
        if (yon === 'alt') ek.alt = Math.min(ek.alt + 0.6, 2.4);
        else if (yon === 'sag') ek.sag = Math.min(ek.sag + 0.6, 1.8);
        else ek = { alt: 0, sag: 0 };
        SG.ekAlanAyarla(ek);
    }

    // —— Kitap görünümünde çizim modu ————————————————————————————————
    var kitapYuzey = null;
    var VB_GEN = 1000;
    var kitapIsaretciler = {};

    function kitapSvgYerlestir() {
        if (!kitapSvg || kitapSvg.hasAttribute('hidden')) return;
        var w = kitapKap.offsetWidth || 1;
        var h = kitapKap.offsetHeight || 1;
        kitapSvg.style.left = kitapKap.offsetLeft + 'px';
        kitapSvg.style.top = kitapKap.offsetTop + 'px';
        kitapSvg.style.width = w + 'px';
        kitapSvg.style.height = h + 'px';
        kitapSvg.setAttribute('viewBox', '0 0 ' + VB_GEN + ' ' + (VB_GEN * h / w));
    }

    function kitapNoktasi(cx, cy) {
        var r = kitapSvg.getBoundingClientRect();
        var vb = kitapSvg.viewBox.baseVal;
        return { x: (cx - r.left) / r.width * vb.width, y: (cy - r.top) / r.height * vb.height };
    }

    if (kitapSvg) {
        kitapYuzey = new Yuzey(kitapSvg, {
            nokta: kitapNoktasi,
            ekranBirim: function () {
                var r = kitapSvg.getBoundingClientRect();
                return r.width ? VB_GEN / r.width : 1;
            },
            sigdirBirim: function () { return VB_GEN / (kitapSvg.clientWidth || kitapKap.offsetWidth || 1); },
            degisti: cubuguGuncelle
        });

        kitapSvg.addEventListener('pointerdown', function (e) {
            if (mod !== 'kitap') return;
            if (e.pointerType === 'mouse' && e.button !== 0) return;
            if (avucMu(e)) { e.preventDefault(); return; }
            kitapIsaretciler[e.pointerId] = true;
            e.preventDefault();
            e.stopPropagation();
            if (Object.keys(kitapIsaretciler).length >= 2) {
                kitapYuzey.iptal(); // iki parmak: yakınlaştırma (okuyucu yapar), çizgi değil
                return;
            }
            if (cizimeBasla(e)) {
                try { kitapSvg.setPointerCapture(e.pointerId); } catch (h) { /* yok say */ }
            }
        });
        kitapSvg.addEventListener('pointermove', function (e) {
            if (mod !== 'kitap' || !kitapIsaretciler[e.pointerId]) return;
            if (Object.keys(kitapIsaretciler).length >= 2) return;
            kitapYuzey.surdur(e);
        });
        var kitapBitti = function (e) {
            if (!kitapIsaretciler[e.pointerId]) return;
            delete kitapIsaretciler[e.pointerId];
            cizimiBitir(e);
        };
        kitapSvg.addEventListener('pointerup', kitapBitti);
        kitapSvg.addEventListener('pointercancel', kitapBitti);
        // Sayfa çevirme motoru bu yüzeyden gelen olayları görmesin.
        ['mousedown', 'touchstart', 'click', 'dblclick'].forEach(function (tur) {
            kitapSvg.addEventListener(tur, function (e) {
                if (mod === 'kitap' && durum.arac !== 'el') e.stopPropagation();
            });
        });
        window.addEventListener('resize', function () { setTimeout(kitapSvgYerlestir, 260); });
        document.addEventListener('ek-kitap-kuruldu', kitapSvgYerlestir);
    }

    function kitapModunuAc() {
        if (!kitapYuzey || mod === 'soru') return;
        mod = 'kitap';
        yuzey = kitapYuzey;
        kitapSvg.removeAttribute('hidden'); // SVG öğelerinde .hidden özelliği yoktur
        kitapSvgYerlestir();
        okuyucu.classList.add('ek-kitap-ciziyor');
        kitapBtn.setAttribute('aria-pressed', 'true');
        cubuk.classList.add('ek-mod-kitap');
        cubuk.classList.remove('ek-mod-soru');
        cubuk.hidden = false;
        if (durum.arac === 'el') durum.arac = 'kalem';
        cubuguGuncelle();
        bildir('Çizim modu açık: sayfa çevirme kilitli. Bitirince “Bitti”ye dokunun.');
    }

    function kitapModunuKapat(zorla) {
        if (mod !== 'kitap') return;
        if (!zorla && kitapYuzey.cizgiVarMi()) {
            onayIste('Kitap üzerindeki çizimler silinecek. Çizim modu kapatılsın mı?', function () {
                kitapModunuKapat(true);
            });
            return;
        }
        kitapYuzey.sifirla();
        kitapIsaretciler = {};
        kitapSvg.setAttribute('hidden', '');
        okuyucu.classList.remove('ek-kitap-ciziyor');
        kitapBtn.setAttribute('aria-pressed', 'false');
        mod = null;
        yuzey = null;
        cubuk.hidden = true;
        acilirlariKapat();
        cubuguGuncelle();
    }

    if (kitapBtn) {
        kitapBtn.addEventListener('click', function () {
            if (mod === 'kitap') kitapModunuKapat(false); else kitapModunuAc();
        });
    }

    // —— Araç çubuğu olayları ———————————————————————————————————————————
    cubuk.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b || b.disabled) return;
        var arac = b.getAttribute('data-arac');
        if (arac) {
            if (arac === 'kalem' && durum.arac === 'kalem') {
                acilirAc(kalemAyar, b);
            } else {
                acilirlariKapat();
                durum.arac = arac;
            }
            cubuguGuncelle();
            return;
        }
        var eylem = b.getAttribute('data-eylem');
        if (eylem !== 'cozum') acilirlariKapat();
        if (eylem === 'geri' && yuzey) yuzey.geriAl();
        else if (eylem === 'ileri' && yuzey) yuzey.ileriAl();
        else if (eylem === 'temizle' && yuzey) yuzey.temizle();
        else if (eylem === 'siklar') siklariDegistir();
        else if (eylem === 'cozum') acilirAc(cozumAyar, b);
        else if (eylem === 'bitti') kitapModunuKapat(false);
        cubuguGuncelle();
    });

    kalemAyar.addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) return;
        if (b.hasAttribute('data-renk')) durum.renk = b.getAttribute('data-renk');
        if (b.hasAttribute('data-kalinlik')) durum.kalinlik = b.getAttribute('data-kalinlik');
        durum.arac = 'kalem';
        cubuguGuncelle();
    });

    cozumAyar.addEventListener('click', function (e) {
        var b = e.target.closest('button[data-cozum]');
        if (!b) return;
        cozumAlani(b.getAttribute('data-cozum'));
        acilirlariKapat();
    });

    document.addEventListener('pointerdown', function (e) {
        if (kalemAyar.hidden && cozumAyar.hidden) return;
        if (e.target.closest('#kalemAyar, #cozumAyar, #araclar')) return;
        acilirlariKapat();
    }, true);

    document.addEventListener('keydown', function (e) {
        if (!mod || !onayKutusu.hidden) return;
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
        var ctrl = e.ctrlKey || e.metaKey;
        var tus = e.key.toLowerCase();
        var islendi = true;
        if (ctrl && tus === 'z' && !e.shiftKey) yuzey.geriAl();
        else if (ctrl && (tus === 'y' || (tus === 'z' && e.shiftKey))) yuzey.ileriAl();
        else if (!ctrl && tus === 'p') durum.arac = 'kalem';
        else if (!ctrl && tus === 'e') durum.arac = 'silgi';
        else if (!ctrl && tus === 'h') durum.arac = 'el';
        else if (e.key === 'Escape' && mod === 'kitap') kitapModunuKapat(false);
        else islendi = false;
        if (islendi) {
            e.preventDefault();
            e.stopImmediatePropagation();
            cubuguGuncelle();
        }
    }, true);

    window.EKitapCizim = {
        kitapModu: function () { return mod === 'kitap'; },
        ciziyorMu: function () { return !!mod && durum.arac !== 'el'; },
        kitapIptal: function () { if (mod === 'kitap' && kitapYuzey) kitapYuzey.iptal(); },
        // Testler ve hata ayıklama için (yalnızca okuma)
        _durum: function () {
            return {
                mod: mod,
                arac: durum.arac,
                ogeSayisi: yuzey ? yuzey.ogeler.length : 0,
                gecmis: yuzey ? yuzey.gecmis.length : 0,
                bekleyenSorular: Object.keys(oturum).length
            };
        }
    };
    cubuguGuncelle();
})();
