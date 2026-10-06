/* E-Kitap — tam ekran soru görünümü.
 *
 * Kitaptaki büyüteç rozetine dokunulunca soru kitabın üstünde açılır ve en-boy
 * oranı korunarak ekrana sığdırılır. Sorular arasında sayfa sınırına takılmadan
 * (bölümler dahil) kitap sırasıyla gezilir. Kitap arkada olduğu gibi kalır;
 * kapatınca aynı sayfa ve konuma dönülür.
 *
 * Görseller: sunucunun ürettiği yüksek çözünürlüklü soru kırpıntısı; yoksa
 * sayfa görselinden CSS ile kırpılır.
 *
 * Yakınlaştırma Pointer Events ile yapılır: iki parmak (çimdik) yakınlaştırır,
 * tek parmak/fare yakınlaştırılmışken kaydırır; yakınlaştırılmamışken yatay
 * kaydırma önceki/sonraki soruya geçer. Kalem araçları (2. aşama) bu katmana
 * bağlanır: içerik koordinatları kâğıt birimindedir, yakınlaştırmadan bağımsızdır.
 */
(function () {
    'use strict';

    var veri = JSON.parse(document.getElementById('ekitapVeri').textContent);
    var kok = document.getElementById('soruGorunum');
    if (!kok) return;
    var sahne = document.getElementById('soruSahne');
    var katman = document.getElementById('soruKatman');
    var kagit = document.getElementById('soruKagit');
    var baslik = document.getElementById('soruBaslik');
    var altBaslik = document.getElementById('soruAlt');
    var oncekiBtn = document.getElementById('soruOnceki');
    var sonrakiBtn = document.getElementById('soruSonraki');
    var kapatBtn = document.getElementById('soruKapat');
    var zoomOran = document.getElementById('soruZoomSifirla');

    var MIN_ZOOM = 1;
    var MAX_ZOOM = 6;
    var ADIM = 1.35;
    var PARCA_ARASI = 0.012; // devam eden alanlar arası boşluk (kâğıt genişliği oranı)

    // Kitaptaki tüm sorular, kitap sırasıyla (bölüm → okuma sırası).
    var sorular = [];
    veri.forEach(function (bolum, b) {
        var testler = {};
        (bolum.sorular || []).forEach(function (s) { testler[s.t] = true; });
        var cokTestli = Object.keys(testler).length > 1;
        (bolum.sorular || []).forEach(function (s) {
            sorular.push({ b: b, soru: s, cokTestli: cokTestli });
        });
    });

    var aktif = -1;
    var acik = false;
    var donusOdagi = null;
    var olcu = { w: 1, h: 1, olcek: 1 }; // kâğıt birimi ve ekrana sığdırma ölçeği
    var z = { s: 1, x: 0, y: 0 };

    function sinirla(d, a, b) { return Math.max(a, Math.min(b, d)); }

    // —— Görsel kaynakları —————————————————————————————————————————————————
    function sayfaBilgisi(b, s) {
        return veri[b].sayfalar[s] || { w: 1000, h: 1414, src: '' };
    }

    function parcalar(kayit) {
        return kayit.soru.alanlar.map(function (a) {
            var sayfa = sayfaBilgisi(kayit.b, a.s);
            var k = a.k;
            return {
                src: a.src,
                sayfa: sayfa,
                k: k,
                w: (k[2] - k[0]) * sayfa.w,
                h: (k[3] - k[1]) * sayfa.h
            };
        });
    }

    function onYukle(indeks) {
        var kayit = sorular[indeks];
        if (!kayit) return;
        parcalar(kayit).forEach(function (p) {
            var img = new Image();
            img.decoding = 'async';
            img.src = p.src || p.sayfa.src;
        });
    }

    // —— Çizim ————————————————————————————————————————————————————————————
    function kagidiKur(kayit) {
        var ps = parcalar(kayit);
        var genislik = 1;
        ps.forEach(function (p) { genislik = Math.max(genislik, p.w); });
        var bosluk = genislik * PARCA_ARASI;
        var yukseklik = 0;
        ps.forEach(function (p, i) { yukseklik += p.h + (i ? bosluk : 0); });
        olcu.w = genislik;
        olcu.h = Math.max(yukseklik, 1);

        kagit.innerHTML = '';
        var y = 0;
        ps.forEach(function (p, i) {
            if (i) y += bosluk;
            var parca = document.createElement('div');
            parca.className = 'ek-soru-parca' + (i ? ' ek-soru-devam' : '');
            parca.style.left = '0';
            parca.style.top = (y / olcu.h * 100) + '%';
            parca.style.width = (p.w / olcu.w * 100) + '%';
            parca.style.height = (p.h / olcu.h * 100) + '%';
            var img = document.createElement('img');
            img.alt = i ? 'Sorunun devamı' : 'Soru ' + kayit.soru.no;
            img.draggable = false;
            img.decoding = 'async';
            if (p.src) {
                img.src = p.src;
                img.className = 'ek-soru-kirpinti';
            } else {
                // Sunucu kırpıntısı yoksa sayfa görselinden kırp.
                img.src = p.sayfa.src;
                img.className = 'ek-soru-sayfadan';
                img.style.width = (p.sayfa.w / p.w * 100) + '%';
                img.style.left = (-p.k[0] * p.sayfa.w / p.w * 100) + '%';
                img.style.top = (-p.k[1] * p.sayfa.h / p.h * 100) + '%';
            }
            parca.appendChild(img);
            kagit.appendChild(parca);
            y += p.h;
        });
        sigdir();
    }

    function sigdir() {
        if (!acik) return;
        var stil = getComputedStyle(sahne);
        var W = sahne.clientWidth - parseFloat(stil.paddingLeft) - parseFloat(stil.paddingRight);
        var H = sahne.clientHeight - parseFloat(stil.paddingTop) - parseFloat(stil.paddingBottom);
        olcu.olcek = Math.max(0.05, Math.min(W / olcu.w, H / olcu.h));
        kagit.style.width = Math.floor(olcu.w * olcu.olcek) + 'px';
        kagit.style.height = Math.floor(olcu.h * olcu.olcek) + 'px';
        zoomSifirla();
        kok.dispatchEvent(new CustomEvent('ek-soru-olcu'));
    }

    function etiketleriGuncelle(kayit) {
        var bolum = veri[kayit.b];
        baslik.textContent = kayit.soru.no + '. soru';
        var parcalarMetin = [];
        if (veri.length > 1) parcalarMetin.push(bolum.ad);
        if (kayit.cokTestli) parcalarMetin.push(kayit.soru.t + '. test');
        parcalarMetin.push((aktif + 1) + ' / ' + sorular.length);
        altBaslik.textContent = parcalarMetin.join(' · ');
        oncekiBtn.disabled = aktif <= 0;
        sonrakiBtn.disabled = aktif >= sorular.length - 1;
    }

    function goster(indeks) {
        if (indeks < 0 || indeks >= sorular.length) return;
        var onceki = aktif;
        aktif = indeks;
        var kayit = sorular[indeks];
        kagidiKur(kayit);
        etiketleriGuncelle(kayit);
        onYukle(indeks + 1);
        onYukle(indeks - 1);
        onYukle(indeks + 2);
        kok.dispatchEvent(new CustomEvent('ek-soru-degisti', { detail: { onceki: onceki, simdi: indeks } }));
    }

    // —— Dış arayüz ———————————————————————————————————————————————————————
    function ac(indeks, odak) {
        if (!sorular[indeks]) return;
        donusOdagi = odak || document.activeElement;
        if (!acik) {
            acik = true;
            kok.hidden = false;
            document.body.classList.add('ek-soru-acik');
            kok.dispatchEvent(new CustomEvent('ek-soru-acildi'));
        }
        goster(indeks);
        kapatBtn.focus({ preventScroll: true });
    }

    var kapatmaOnayi = null; // 2. aşama: çizim varsa onay sorar (true → kapat)

    function kapat() {
        if (!acik) return;
        if (kapatmaOnayi && !kapatmaOnayi()) return;
        acik = false;
        kok.hidden = true;
        document.body.classList.remove('ek-soru-acik');
        kagit.innerHTML = '';
        aktif = -1;
        kok.dispatchEvent(new CustomEvent('ek-soru-kapandi'));
        if (donusOdagi && document.contains(donusOdagi)) {
            try { donusOdagi.focus({ preventScroll: true }); } catch (e) { /* yok say */ }
        }
    }

    function sonraki() { if (aktif < sorular.length - 1) goster(aktif + 1); }
    function onceki() { if (aktif > 0) goster(aktif - 1); }

    function indeksBul(bolumIndeksi, soruId) {
        for (var i = 0; i < sorular.length; i++) {
            if (sorular[i].b === bolumIndeksi && sorular[i].soru.id === soruId) return i;
        }
        return -1;
    }

    // —— Yakınlaştırma ————————————————————————————————————————————————————
    function sinirlariUygula() {
        var W = sahne.clientWidth;
        var H = sahne.clientHeight;
        z.x = sinirla(z.x, W - W * z.s, 0);
        z.y = sinirla(z.y, H - H * z.s, 0);
    }

    function zoomCiz() {
        katman.style.transform = 'translate(' + z.x + 'px,' + z.y + 'px) scale(' + z.s + ')';
        kok.classList.toggle('ek-yakin', z.s > 1.001);
        zoomOran.textContent = '%' + Math.round(z.s * 100);
    }

    function zoomAyarla(yeniS, px, py) {
        yeniS = sinirla(yeniS, MIN_ZOOM, MAX_ZOOM);
        if (px === undefined) {
            px = sahne.clientWidth / 2;
            py = sahne.clientHeight / 2;
        }
        z.x = px - (px - z.x) * (yeniS / z.s);
        z.y = py - (py - z.y) * (yeniS / z.s);
        z.s = yeniS;
        if (z.s <= 1.001) { z.s = 1; z.x = 0; z.y = 0; }
        sinirlariUygula();
        zoomCiz();
    }

    function zoomSifirla() {
        z.s = 1; z.x = 0; z.y = 0;
        zoomCiz();
    }

    function yerel(e) {
        var r = sahne.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    /* Ekran noktasını kâğıt birimine çevirir (çizim katmanı için). */
    function kagitNoktasi(clientX, clientY) {
        var r = kagit.getBoundingClientRect();
        return {
            x: (clientX - r.left) / r.width * olcu.w,
            y: (clientY - r.top) / r.height * olcu.h
        };
    }

    // İşaretçi takibi. Dış modül (çizim) bir işaretçiyi "sahiplenirse" burada
    // kaydırma/çimdik için kullanılmaz.
    var isaretciler = {};
    var jest = null;
    var sonDokunus = { t: 0, x: 0, y: 0 };
    var sahiplenici = null; // function(e) → true ise işaretçi çizime gider

    function aktifIsaretciler() {
        return Object.keys(isaretciler).map(function (k) { return isaretciler[k]; });
    }

    function cimdikBaslat() {
        var p = aktifIsaretciler();
        var a = p[0], b = p[1];
        var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        jest = {
            tur: 'cimdik',
            mesafe: Math.hypot(a.x - b.x, a.y - b.y) || 1,
            s: z.s,
            icerik: { x: (mx - z.x) / z.s, y: (my - z.y) / z.s }
        };
    }

    sahne.addEventListener('pointerdown', function (e) {
        if (!acik) return;
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        if (sahiplenici && sahiplenici(e, 'down')) return;
        var p = yerel(e);
        isaretciler[e.pointerId] = { x: p.x, y: p.y, bx: p.x, by: p.y, t: Date.now(), tur: e.pointerType };
        try { sahne.setPointerCapture(e.pointerId); } catch (h) { /* yok say */ }
        var sayi = aktifIsaretciler().length;
        if (sayi >= 2) {
            cimdikBaslat();
        } else {
            jest = { tur: 'kaydir', bx: p.x, by: p.y, x: z.x, y: z.y, t: Date.now() };
            if (e.pointerType !== 'mouse') {
                var simdi = Date.now();
                var cift = simdi - sonDokunus.t < 320 && Math.hypot(p.x - sonDokunus.x, p.y - sonDokunus.y) < 40;
                sonDokunus = { t: cift ? 0 : simdi, x: p.x, y: p.y };
                if (cift) {
                    if (z.s > 1.001) zoomSifirla(); else zoomAyarla(2.5, p.x, p.y);
                    jest = null;
                }
            }
        }
        e.preventDefault();
    });

    sahne.addEventListener('pointermove', function (e) {
        if (sahiplenici && sahiplenici(e, 'move')) return;
        var kayit = isaretciler[e.pointerId];
        if (!kayit) return;
        var p = yerel(e);
        kayit.x = p.x;
        kayit.y = p.y;
        if (!jest) return;
        if (jest.tur === 'cimdik') {
            var ps = aktifIsaretciler();
            if (ps.length < 2) return;
            var a = ps[0], b = ps[1];
            var yeniS = sinirla(jest.s * (Math.hypot(a.x - b.x, a.y - b.y) || 1) / jest.mesafe, MIN_ZOOM, MAX_ZOOM);
            var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
            z.s = yeniS;
            z.x = mx - jest.icerik.x * yeniS;
            z.y = my - jest.icerik.y * yeniS;
            if (z.s <= 1.001) z.s = 1;
            sinirlariUygula();
            zoomCiz();
        } else if (jest.tur === 'kaydir' && z.s > 1.001) {
            z.x = jest.x + (p.x - jest.bx);
            z.y = jest.y + (p.y - jest.by);
            sinirlariUygula();
            zoomCiz();
        }
    });

    function isaretciBitti(e) {
        if (sahiplenici && sahiplenici(e, 'up')) return;
        var kayit = isaretciler[e.pointerId];
        if (!kayit) return;
        delete isaretciler[e.pointerId];
        var kalan = aktifIsaretciler();
        if (jest && jest.tur === 'kaydir' && z.s <= 1.001 && e.type === 'pointerup' && kalan.length === 0) {
            // Yakınlaştırılmamışken hızlı yatay kaydırma → sorular arasında geçiş
            var dx = kayit.x - kayit.bx;
            var dy = kayit.y - kayit.by;
            var sure = Date.now() - kayit.t;
            if (Math.abs(dx) > 90 && Math.abs(dx) > Math.abs(dy) * 1.6 && sure < 700) {
                if (dx < 0) sonraki(); else onceki();
            }
        }
        if (kalan.length === 1) {
            jest = { tur: 'kaydir', bx: kalan[0].x, by: kalan[0].y, x: z.x, y: z.y, t: Date.now() };
            kalan[0].bx = kalan[0].x; kalan[0].by = kalan[0].y; kalan[0].t = Date.now();
        } else if (kalan.length === 0) {
            jest = null;
            if (z.s <= 1.001) zoomSifirla();
        }
    }
    sahne.addEventListener('pointerup', isaretciBitti);
    sahne.addEventListener('pointercancel', isaretciBitti);

    sahne.addEventListener('dblclick', function (e) {
        if (sahiplenici && sahiplenici(e, 'dblclick')) return;
        var p = yerel(e);
        if (z.s > 1.001) zoomSifirla(); else zoomAyarla(2.5, p.x, p.y);
    });
    sahne.addEventListener('wheel', function (e) {
        var p = yerel(e);
        zoomAyarla(z.s * (e.deltaY < 0 ? 1.15 : 1 / 1.15), p.x, p.y);
        if (e.cancelable) e.preventDefault();
    }, { passive: false });

    // —— Olaylar ——————————————————————————————————————————————————————————
    oncekiBtn.addEventListener('click', onceki);
    sonrakiBtn.addEventListener('click', sonraki);
    kapatBtn.addEventListener('click', kapat);
    document.getElementById('soruZoomCok').addEventListener('click', function () { zoomAyarla(z.s * ADIM); });
    document.getElementById('soruZoomAz').addEventListener('click', function () { zoomAyarla(z.s / ADIM); });
    zoomOran.addEventListener('click', zoomSifirla);

    document.addEventListener('keydown', function (e) {
        if (!acik) return;
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
        var tus = e.key;
        var islendi = true;
        if (tus === 'Escape') kapat();
        else if (tus === 'ArrowRight' || tus === 'PageDown' || (tus === ' ' && e.target === document.body)) sonraki();
        else if (tus === 'ArrowLeft' || tus === 'PageUp') onceki();
        else if (tus === '+' || tus === '=') zoomAyarla(z.s * ADIM);
        else if (tus === '-') zoomAyarla(z.s / ADIM);
        else if (tus === '0') zoomSifirla();
        else islendi = false;
        if (islendi) {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);

    var zamanlayici = null;
    window.addEventListener('resize', function () {
        clearTimeout(zamanlayici);
        zamanlayici = setTimeout(sigdir, 120);
    });

    window.EKitapSoru = {
        ac: ac,
        kapat: kapat,
        acikMi: function () { return acik; },
        indeksBul: indeksBul,
        sorular: sorular,
        aktif: function () { return aktif; },
        kok: kok,
        sahne: sahne,
        kagit: kagit,
        olcu: olcu,
        kagitNoktasi: kagitNoktasi,
        zoom: z,
        sahiplen: function (fn) { sahiplenici = fn; },
        kapatmaOnayiAyarla: function (fn) { kapatmaOnayi = fn; },
        sonraki: sonraki,
        onceki: onceki
    };
})();
