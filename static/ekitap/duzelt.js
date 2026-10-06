/* E-Kitap yönetimi — soru alanlarını düzeltme ekranı.
 *
 * Kutular sayfa üzerinde gösterilir; seçilir, taşınır, köşelerden
 * boyutlandırılır, sürükleyerek çizilir (yeni soru ya da seçili soruya ek
 * alan), silinir. Soru numarası, test ve okuma sırası düzenlenir. Değişiklikler
 * geri/ileri alınabilir ve "Kaydet" ile sunucuya gönderilir; kaydedilen sorular
 * onaylı olur ve otomatik tespit yeniden çalışınca korunur.
 */
(function () {
    'use strict';

    var veri = JSON.parse(document.getElementById('duzeltVeri').textContent);
    var ayar = document.getElementById('duzeltAyar');
    var KAYDET_URL = ayar.getAttribute('data-kaydet');
    var CSRF = ayar.querySelector('input[name=csrfmiddlewaretoken]').value;

    var $ = function (id) { return document.getElementById(id); };
    var tuval = $('duzeltTuval');
    var kagit = $('duzeltKagit');
    var gorsel = $('duzeltGorsel');
    var kutular = $('duzeltKutular');
    var sayfaListesi = $('sayfaListesi');
    var kaydetBtn = $('kaydet');
    var geriBtn = $('geriAl');
    var ileriBtn = $('ileriAl');
    var durumEt = $('kayitDurumu');

    var MIN = 0.012;
    var yeniSayac = 0;

    // —— Durum ——————————————————————————————————————————————————————————
    // Her soruya yerel anahtar verilir: kayıtlıysa id, yeniyse "yeni-N".
    function iceAktar(v) {
        return {
            sorular: v.sorular.map(function (s) {
                return {
                    anahtar: String(s.id), id: s.id, test_no: s.test_no, no: s.no, guven: s.guven,
                    elle: s.elle, onayli: s.onayli, inceleme: s.inceleme,
                    alanlar: s.alanlar.map(function (a) { return { sayfa: a.sayfa, k: a.k.slice() }; })
                };
            }),
            degisen: {},
            silinen: [],
            onaylanan: {},
            siraDegisti: false
        };
    }

    var d = iceAktar(veri);
    var gecmis = [];
    var ileri = [];
    var aktifSayfa = 0;
    var secili = null; // { anahtar, alan }
    var mod = 'sec';
    var kaydediliyor = false;

    function kopya(o) { return JSON.parse(JSON.stringify(o)); }

    function kirli() {
        return Object.keys(d.degisen).length > 0 || d.silinen.length > 0 ||
            Object.keys(d.onaylanan).length > 0 || d.siraDegisti;
    }

    function anlikGoruntu() {
        gecmis.push(kopya({ d: d, secili: secili }));
        if (gecmis.length > 200) gecmis.shift();
        ileri = [];
    }

    function geriAl() {
        if (!gecmis.length) return;
        ileri.push(kopya({ d: d, secili: secili }));
        var g = gecmis.pop();
        d = g.d; secili = g.secili;
        ciz();
    }

    function ileriAl() {
        if (!ileri.length) return;
        gecmis.push(kopya({ d: d, secili: secili }));
        var g = ileri.pop();
        d = g.d; secili = g.secili;
        ciz();
    }

    function soruBul(anahtar) {
        for (var i = 0; i < d.sorular.length; i++) if (d.sorular[i].anahtar === anahtar) return d.sorular[i];
        return null;
    }

    function degisti(soru) {
        d.degisen[soru.anahtar] = true;
        soru.elle = true;
        soru.onayli = true;
        soru.inceleme = false;
    }

    function cokTestli() {
        var t = {};
        d.sorular.forEach(function (s) { t[s.test_no] = true; });
        return Object.keys(t).length > 1;
    }

    function etiket(s) {
        return (cokTestli() ? 'T' + s.test_no + ' · ' : '') + s.no;
    }

    function konumAnahtari(sayfa, k) {
        return [sayfa, k[0] > 0.5 ? 1 : 0, k[1]];
    }

    function konumKiyas(a, b) {
        for (var i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
        return 0;
    }

    // —— Çizim ——————————————————————————————————————————————————————————
    function sayfaKontrolMu(s) {
        if (d.onaylanan[s.sira]) return false;
        return s.kontrol || d.sorular.some(function (q) {
            return q.inceleme && q.alanlar.some(function (a) { return a.sayfa === s.sira; });
        });
    }

    function sayfaListesiCiz() {
        var kontrol = veri.sayfalar.filter(sayfaKontrolMu);
        var html = '';
        function oge(s) {
            var adet = d.sorular.filter(function (q) {
                return q.alanlar.some(function (a) { return a.sayfa === s.sira; });
            }).length;
            return '<button type="button" class="ek-duzelt-kucuk' + (s.sira === aktifSayfa ? ' ek-aktif' : '') +
                (sayfaKontrolMu(s) ? ' ek-kontrol' : '') + (d.onaylanan[s.sira] ? ' ek-onaylandi' : '') +
                '" data-sayfa="' + s.sira + '"><img src="' + s.kucuk + '" alt="" loading="lazy">' +
                '<span>Sayfa ' + (s.sira + 1) + ' · ' + adet + ' soru</span></button>';
        }
        if (kontrol.length) {
            html += '<p class="ek-duzelt-grup">Kontrol bekleyen · ' + kontrol.length + '</p>';
            html += kontrol.map(oge).join('');
            html += '<p class="ek-duzelt-grup">Tüm sayfalar</p>';
        }
        html += veri.sayfalar.map(oge).join('');
        sayfaListesi.innerHTML = html;
    }

    function kagidiBoyutla() {
        var s = veri.sayfalar[aktifSayfa];
        if (!s) return;
        var oran = s.w && s.h ? s.w / s.h : 0.707;
        var W = tuval.clientWidth - 32;
        var H = tuval.clientHeight - 32;
        var h = Math.min(H, W / oran);
        kagit.style.width = Math.floor(h * oran) + 'px';
        kagit.style.height = Math.floor(h) + 'px';
    }

    function kutulariCiz() {
        var html = '';
        d.sorular.forEach(function (q) {
            q.alanlar.forEach(function (a, i) {
                if (a.sayfa !== aktifSayfa) return;
                var sinif = 'ek-kutu';
                if (q.inceleme) sinif += ' ek-kutu-incele';
                else if (q.elle || q.onayli) sinif += ' ek-kutu-elle';
                else if (q.guven < 0.75) sinif += ' ek-kutu-dusuk';
                var sec = secili && secili.anahtar === q.anahtar;
                if (sec) sinif += ' ek-kutu-secili';
                if (sec && secili.alan === i) sinif += ' ek-kutu-aktif';
                html += '<div class="' + sinif + '" data-soru="' + q.anahtar + '" data-alan="' + i + '" style="left:' +
                    (a.k[0] * 100) + '%;top:' + (a.k[1] * 100) + '%;width:' + ((a.k[2] - a.k[0]) * 100) +
                    '%;height:' + ((a.k[3] - a.k[1]) * 100) + '%"><span class="ek-kutu-etiket">' + etiket(q) +
                    (q.alanlar.length > 1 ? ' <small>' + (i + 1) + '/' + q.alanlar.length + '</small>' : '') + '</span>' +
                    (sec && secili.alan === i
                        ? '<i class="ek-tutamac" data-tutamac="nw"></i><i class="ek-tutamac" data-tutamac="ne"></i>' +
                          '<i class="ek-tutamac" data-tutamac="sw"></i><i class="ek-tutamac" data-tutamac="se"></i>'
                        : '') +
                    '</div>';
            });
        });
        kutular.innerHTML = html;
    }

    function sayfaSorulari() {
        return d.sorular.filter(function (q) {
            return q.alanlar.some(function (a) { return a.sayfa === aktifSayfa; });
        });
    }

    function panelCiz() {
        var liste = sayfaSorulari();
        $('sayfaSorulari').innerHTML = liste.map(function (q) {
            var sira = d.sorular.indexOf(q) + 1;
            return '<li><button type="button" class="ek-duzelt-soru' +
                (secili && secili.anahtar === q.anahtar ? ' ek-aktif' : '') + '" data-soru="' + q.anahtar + '">' +
                '<strong>' + etiket(q) + '</strong><span>sıra ' + sira +
                (q.inceleme ? ' · inceleyin' : q.elle ? ' · elle' : (q.guven < 0.75 ? ' · düşük güven' : '')) +
                '</span></button></li>';
        }).join('');
        $('sayfaSorulariBos').hidden = liste.length > 0;

        var q = secili && soruBul(secili.anahtar);
        $('seciliKart').hidden = !q;
        if (q) {
            if (document.activeElement !== $('seciliTest')) $('seciliTest').value = q.test_no;
            if (document.activeElement !== $('seciliNo')) $('seciliNo').value = q.no;
            $('seciliBilgi').textContent = (q.elle ? 'Elle düzeltilmiş' : 'Otomatik · güven %' + Math.round(q.guven * 100)) +
                ' · okuma sırası ' + (d.sorular.indexOf(q) + 1) + ' / ' + d.sorular.length;
            $('seciliAlanlar').innerHTML = q.alanlar.map(function (a, i) {
                return '<li><button type="button" class="ek-dugme ek-dugme-metin ek-dugme-kucuk" data-git="' + a.sayfa + '" data-alan="' + i + '">Alan ' +
                    (i + 1) + ' · sayfa ' + (a.sayfa + 1) + '</button>' +
                    '<button type="button" class="ek-dugme ek-dugme-metin ek-dugme-kucuk ek-dugme-tehlike" data-alan-sil="' + i + '">Sil</button></li>';
            }).join('');
            var idx = d.sorular.indexOf(q);
            $('siraYukari').disabled = idx <= 0;
            $('siraAsagi').disabled = idx >= d.sorular.length - 1;
        }
    }

    function ustCiz() {
        var s = veri.sayfalar[aktifSayfa];
        $('sayfaEtiketi').textContent = 'Sayfa ' + (aktifSayfa + 1) + ' / ' + veri.sayfalar.length;
        $('oncekiSayfa').disabled = aktifSayfa <= 0;
        $('sonrakiSayfa').disabled = aktifSayfa >= veri.sayfalar.length - 1;
        var notlar = [];
        if (s && s.not && !d.onaylanan[s.sira]) notlar.push(s.not);
        if (s && !s.metinli) notlar.push('Taranmış sayfa: sorular elle işaretlenmeli.');
        $('sayfaNotu').hidden = !notlar.length;
        $('sayfaNotu').textContent = notlar.join(' · ');
        var onayli = s && d.onaylanan[s.sira];
        $('sayfaOnayla').textContent = onayli ? 'Onaylanacak ✓' : 'Sayfayı onayla';
        $('sayfaOnayla').classList.toggle('ek-onaylandi', !!onayli);
        Array.prototype.forEach.call(document.querySelectorAll('[data-mod]'), function (b) {
            b.setAttribute('aria-pressed', b.getAttribute('data-mod') === mod ? 'true' : 'false');
        });
        document.querySelector('[data-mod="alan"]').disabled = !secili;
        tuval.setAttribute('data-mod', mod);
        geriBtn.disabled = !gecmis.length;
        ileriBtn.disabled = !ileri.length;
        kaydetBtn.disabled = !kirli() || kaydediliyor;
        durumEt.textContent = kaydediliyor ? 'Kaydediliyor…' : (kirli() ? 'Kaydedilmemiş değişiklik var' : 'Kaydedildi');
        durumEt.classList.toggle('ek-kirli', kirli());
    }

    function ciz() {
        if (secili && !soruBul(secili.anahtar)) secili = null;
        if (mod === 'alan' && !secili) mod = 'sec';
        var s = veri.sayfalar[aktifSayfa];
        if (s && gorsel.getAttribute('src') !== s.src) gorsel.src = s.src;
        sayfaListesiCiz();
        kutulariCiz();
        panelCiz();
        ustCiz();
        kagidiBoyutla(); // sayfa notu göründükten sonra: kalan alana sığdır
    }

    function sayfayaGit(i) {
        aktifSayfa = Math.max(0, Math.min(veri.sayfalar.length - 1, i));
        ciz();
        var akt = sayfaListesi.querySelector('.ek-aktif');
        if (akt) akt.scrollIntoView({ block: 'nearest' });
    }

    // —— Kutu etkileşimi ————————————————————————————————————————————————
    var surukle = null;

    function nokta(e) {
        var r = kagit.getBoundingClientRect();
        return {
            x: Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
            y: Math.max(0, Math.min(1, (e.clientY - r.top) / r.height))
        };
    }

    tuval.addEventListener('pointerdown', function (e) {
        if (e.button !== 0 && e.pointerType === 'mouse') return;
        var p = nokta(e);
        var tutamac = e.target.closest('.ek-tutamac');
        var kutu = e.target.closest('.ek-kutu');
        if (mod === 'sec' && kutu) {
            var q = soruBul(kutu.getAttribute('data-soru'));
            var ai = parseInt(kutu.getAttribute('data-alan'), 10);
            secili = { anahtar: q.anahtar, alan: ai };
            surukle = {
                tur: tutamac ? 'boyut' : 'tasi', kose: tutamac ? tutamac.getAttribute('data-tutamac') : '',
                soru: q, alan: ai, bas: p, ilk: q.alanlar[ai].k.slice(), kayitli: false
            };
            ciz();
        } else if ((mod === 'yeni') || (mod === 'alan' && secili)) {
            surukle = { tur: 'ciz', bas: p, son: p };
            var on = document.createElement('div');
            on.className = 'ek-kutu ek-kutu-onizleme';
            kutular.appendChild(on);
            surukle.el = on;
        } else if (mod === 'sec') {
            secili = null;
            ciz();
            return;
        } else {
            return;
        }
        try { tuval.setPointerCapture(e.pointerId); } catch (h) { /* yok say */ }
        e.preventDefault();
    });

    tuval.addEventListener('pointermove', function (e) {
        if (!surukle) return;
        var p = nokta(e);
        if (surukle.tur === 'ciz') {
            surukle.son = p;
            var x0 = Math.min(surukle.bas.x, p.x), y0 = Math.min(surukle.bas.y, p.y);
            surukle.el.style.left = (x0 * 100) + '%';
            surukle.el.style.top = (y0 * 100) + '%';
            surukle.el.style.width = (Math.abs(p.x - surukle.bas.x) * 100) + '%';
            surukle.el.style.height = (Math.abs(p.y - surukle.bas.y) * 100) + '%';
            return;
        }
        var dx = p.x - surukle.bas.x, dy = p.y - surukle.bas.y;
        if (!surukle.kayitli) {
            if (Math.abs(dx) < 0.002 && Math.abs(dy) < 0.002) return;
            anlikGoruntu();
            surukle.kayitli = true;
        }
        var k = surukle.ilk.slice();
        if (surukle.tur === 'tasi') {
            var w = k[2] - k[0], h = k[3] - k[1];
            k[0] = Math.max(0, Math.min(1 - w, k[0] + dx));
            k[1] = Math.max(0, Math.min(1 - h, k[1] + dy));
            k[2] = k[0] + w;
            k[3] = k[1] + h;
        } else {
            if (surukle.kose.indexOf('w') >= 0) k[0] = Math.min(k[2] - MIN, Math.max(0, k[0] + dx));
            if (surukle.kose.indexOf('e') >= 0) k[2] = Math.max(k[0] + MIN, Math.min(1, k[2] + dx));
            if (surukle.kose.indexOf('n') >= 0) k[1] = Math.min(k[3] - MIN, Math.max(0, k[1] + dy));
            if (surukle.kose.indexOf('s') >= 0) k[3] = Math.max(k[1] + MIN, Math.min(1, k[3] + dy));
        }
        surukle.soru.alanlar[surukle.alan].k = k.map(function (v) { return Math.round(v * 10000) / 10000; });
        degisti(surukle.soru);
        kutulariCiz();
    });

    function surukleBitti() {
        if (!surukle) return;
        var s = surukle;
        surukle = null;
        if (s.tur === 'ciz') {
            if (s.el.parentNode) s.el.parentNode.removeChild(s.el);
            var k = [Math.min(s.bas.x, s.son.x), Math.min(s.bas.y, s.son.y), Math.max(s.bas.x, s.son.x), Math.max(s.bas.y, s.son.y)]
                .map(function (v) { return Math.round(v * 10000) / 10000; });
            if (k[2] - k[0] < MIN || k[3] - k[1] < MIN) return;
            anlikGoruntu();
            if (mod === 'alan' && secili) {
                var q = soruBul(secili.anahtar);
                q.alanlar.push({ sayfa: aktifSayfa, k: k });
                degisti(q);
                secili = { anahtar: q.anahtar, alan: q.alanlar.length - 1 };
                mod = 'sec';
            } else {
                yeniSoru(k);
            }
        }
        ciz();
    }
    tuval.addEventListener('pointerup', surukleBitti);
    tuval.addEventListener('pointercancel', surukleBitti);

    function yeniSoru(k) {
        var konum = konumAnahtari(aktifSayfa, k);
        var indeks = d.sorular.length;
        for (var i = 0; i < d.sorular.length; i++) {
            var a = d.sorular[i].alanlar[0];
            if (a && konumKiyas(konumAnahtari(a.sayfa, a.k), konum) > 0) { indeks = i; break; }
        }
        var onceki = d.sorular[indeks - 1];
        var q = {
            anahtar: 'yeni-' + (++yeniSayac), id: null,
            test_no: onceki ? onceki.test_no : 1, no: onceki ? onceki.no + 1 : 1, guven: 1,
            elle: true, onayli: true, inceleme: false, alanlar: [{ sayfa: aktifSayfa, k: k }]
        };
        d.sorular.splice(indeks, 0, q);
        d.degisen[q.anahtar] = true;
        if (indeks !== d.sorular.length - 1) d.siraDegisti = true;
        secili = { anahtar: q.anahtar, alan: 0 };
        mod = 'sec';
        setTimeout(function () { $('seciliNo').focus(); $('seciliNo').select(); }, 0);
    }

    function alanSil(q, i) {
        anlikGoruntu();
        q.alanlar.splice(i, 1);
        if (!q.alanlar.length) {
            soruyuKaldir(q);
        } else {
            degisti(q);
            secili = { anahtar: q.anahtar, alan: Math.min(i, q.alanlar.length - 1) };
        }
        ciz();
    }

    function soruyuKaldir(q) {
        d.sorular.splice(d.sorular.indexOf(q), 1);
        delete d.degisen[q.anahtar];
        if (q.id) d.silinen.push(q.id);
        secili = null;
    }

    function siraTasi(yon) {
        var q = secili && soruBul(secili.anahtar);
        if (!q) return;
        var i = d.sorular.indexOf(q), j = i + yon;
        if (j < 0 || j >= d.sorular.length) return;
        anlikGoruntu();
        d.sorular[i] = d.sorular[j];
        d.sorular[j] = q;
        d.siraDegisti = true;
        ciz();
    }

    // —— Önizleme (öğretmenin göreceği) —————————————————————————————————
    function onizle() {
        var q = secili && soruBul(secili.anahtar);
        if (!q) return;
        var parcalar = q.alanlar.map(function (a) {
            var s = veri.sayfalar[a.sayfa];
            return { s: s, k: a.k, w: (a.k[2] - a.k[0]) * s.w, h: (a.k[3] - a.k[1]) * s.h };
        });
        var W = Math.max.apply(null, parcalar.map(function (p) { return p.w; }));
        var bosluk = W * 0.012;
        var H = parcalar.reduce(function (t, p, i) { return t + p.h + (i ? bosluk : 0); }, 0);
        var kap = $('onizlemeKagit');
        var sahne = kap.parentNode.parentNode;
        $('onizleme').hidden = false;
        var olcek = Math.min((sahne.clientWidth - 80) / W, (sahne.clientHeight - 160) / H);
        kap.style.width = (W * olcek) + 'px';
        kap.style.height = (H * olcek) + 'px';
        var y = 0;
        kap.innerHTML = parcalar.map(function (p, i) {
            if (i) y += bosluk;
            var ust = y;
            y += p.h;
            return '<div class="ek-soru-parca' + (i ? ' ek-soru-devam' : '') + '" style="left:0;top:' + (ust / H * 100) +
                '%;width:' + (p.w / W * 100) + '%;height:' + (p.h / H * 100) + '%"><img class="ek-soru-sayfadan" alt="" src="' +
                p.s.src + '" style="width:' + (p.s.w / p.w * 100) + '%;left:' + (-p.k[0] * p.s.w / p.w * 100) + '%;top:' +
                (-p.k[1] * p.s.h / p.h * 100) + '%"></div>';
        }).join('');
        $('onizlemeBaslik').textContent = q.no + '. soru';
        $('onizlemeKapat').focus();
    }

    // —— Kaydet ——————————————————————————————————————————————————————————
    function kaydet() {
        if (!kirli() || kaydediliyor) return;
        var yuk = {
            sorular: d.sorular.filter(function (q) { return d.degisen[q.anahtar]; }).map(function (q) {
                return {
                    id: q.id, gecici: q.id ? undefined : q.anahtar.replace('yeni-', ''),
                    test_no: q.test_no, no: q.no, alanlar: q.alanlar
                };
            }),
            silinen: d.silinen,
            onaylanan_sayfalar: Object.keys(d.onaylanan).map(Number)
        };
        if (d.siraDegisti) yuk.sira = d.sorular.map(function (q) { return q.id || q.anahtar; });
        kaydediliyor = true;
        ustCiz();
        var istek = new XMLHttpRequest();
        istek.open('POST', KAYDET_URL);
        istek.setRequestHeader('Content-Type', 'application/json');
        istek.setRequestHeader('X-CSRFToken', CSRF);
        istek.onload = function () {
            kaydediliyor = false;
            var cevap = null;
            try { cevap = JSON.parse(istek.responseText); } catch (h) { /* yok */ }
            if (istek.status === 200 && cevap && cevap.tamam) {
                var seciliId = secili ? (soruBul(secili.anahtar) || {}).id : null;
                veri = cevap.veri;
                d = iceAktar(veri);
                gecmis = [];
                ileri = [];
                secili = seciliId && soruBul(String(seciliId)) ? { anahtar: String(seciliId), alan: 0 } : null;
                ciz();
                durumEt.textContent = 'Kaydedildi ✓';
            } else {
                ustCiz();
                durumEt.textContent = (cevap && cevap.hata) || 'Kaydedilemedi. Bağlantıyı kontrol edin.';
                durumEt.classList.add('ek-hata');
            }
        };
        istek.onerror = function () {
            kaydediliyor = false;
            ustCiz();
            durumEt.textContent = 'Kaydedilemedi. Bağlantıyı kontrol edin.';
            durumEt.classList.add('ek-hata');
        };
        durumEt.classList.remove('ek-hata');
        istek.send(JSON.stringify(yuk));
    }

    // —— Olaylar ————————————————————————————————————————————————————————
    sayfaListesi.addEventListener('click', function (e) {
        var b = e.target.closest('[data-sayfa]');
        if (b) sayfayaGit(parseInt(b.getAttribute('data-sayfa'), 10));
    });
    $('oncekiSayfa').addEventListener('click', function () { sayfayaGit(aktifSayfa - 1); });
    $('sonrakiSayfa').addEventListener('click', function () { sayfayaGit(aktifSayfa + 1); });
    Array.prototype.forEach.call(document.querySelectorAll('[data-mod]'), function (b) {
        b.addEventListener('click', function () { mod = b.getAttribute('data-mod'); ciz(); });
    });
    $('sayfaOnayla').addEventListener('click', function () {
        anlikGoruntu();
        if (d.onaylanan[aktifSayfa]) delete d.onaylanan[aktifSayfa]; else d.onaylanan[aktifSayfa] = true;
        ciz();
    });
    $('sayfaSorulari').addEventListener('click', function (e) {
        var b = e.target.closest('[data-soru]');
        if (!b) return;
        var q = soruBul(b.getAttribute('data-soru'));
        var ai = 0;
        q.alanlar.forEach(function (a, i) { if (a.sayfa === aktifSayfa && ai === 0) ai = i; });
        secili = { anahtar: q.anahtar, alan: ai };
        ciz();
    });
    $('seciliAlanlar').addEventListener('click', function (e) {
        var q = secili && soruBul(secili.anahtar);
        if (!q) return;
        var git = e.target.closest('[data-git]');
        var sil = e.target.closest('[data-alan-sil]');
        if (git) {
            secili.alan = parseInt(git.getAttribute('data-alan'), 10);
            sayfayaGit(parseInt(git.getAttribute('data-git'), 10));
        } else if (sil) {
            alanSil(q, parseInt(sil.getAttribute('data-alan-sil'), 10));
        }
    });
    function numaraAlani(alan, ad, en_cok) {
        $(alan).addEventListener('change', function () {
            var q = secili && soruBul(secili.anahtar);
            var v = parseInt(this.value, 10);
            if (!q || !(v >= 1 && v <= en_cok)) { panelCiz(); return; }
            if (q[ad] === v) return;
            anlikGoruntu();
            q[ad] = v;
            degisti(q);
            ciz();
        });
    }
    numaraAlani('seciliTest', 'test_no', 99);
    numaraAlani('seciliNo', 'no', 999);
    $('siraYukari').addEventListener('click', function () { siraTasi(-1); });
    $('siraAsagi').addEventListener('click', function () { siraTasi(1); });
    $('soruSil').addEventListener('click', function () {
        var q = secili && soruBul(secili.anahtar);
        if (!q) return;
        anlikGoruntu();
        soruyuKaldir(q);
        ciz();
    });
    $('onizle').addEventListener('click', onizle);
    $('onizlemeKapat').addEventListener('click', function () { $('onizleme').hidden = true; });
    geriBtn.addEventListener('click', geriAl);
    ileriBtn.addEventListener('click', ileriAl);
    kaydetBtn.addEventListener('click', kaydet);

    document.addEventListener('keydown', function (e) {
        if (!$('onizleme').hidden) {
            if (e.key === 'Escape') $('onizleme').hidden = true;
            return;
        }
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
        var ctrl = e.ctrlKey || e.metaKey;
        var tus = e.key.toLowerCase();
        var q = secili && soruBul(secili.anahtar);
        if (ctrl && tus === 'z' && !e.shiftKey) { geriAl(); e.preventDefault(); }
        else if (ctrl && (tus === 'y' || (tus === 'z' && e.shiftKey))) { ileriAl(); e.preventDefault(); }
        else if (ctrl && tus === 's') { kaydet(); e.preventDefault(); }
        else if ((e.key === 'Delete' || e.key === 'Backspace') && q) { alanSil(q, secili.alan); e.preventDefault(); }
        else if (!ctrl && tus === 's') { mod = 'sec'; ciz(); }
        else if (!ctrl && tus === 'n') { mod = 'yeni'; ciz(); }
        else if (!ctrl && tus === 'a' && secili) { mod = 'alan'; ciz(); }
        else if (e.key === 'PageDown') { sayfayaGit(aktifSayfa + 1); e.preventDefault(); }
        else if (e.key === 'PageUp') { sayfayaGit(aktifSayfa - 1); e.preventDefault(); }
        else if (q && e.key.indexOf('Arrow') === 0 && q.alanlar[secili.alan]) {
            var adim = e.shiftKey ? 0.01 : 0.002;
            var dx = e.key === 'ArrowLeft' ? -adim : e.key === 'ArrowRight' ? adim : 0;
            var dy = e.key === 'ArrowUp' ? -adim : e.key === 'ArrowDown' ? adim : 0;
            var k = q.alanlar[secili.alan].k;
            if (k[0] + dx < 0 || k[2] + dx > 1 || k[1] + dy < 0 || k[3] + dy > 1) return;
            anlikGoruntu();
            q.alanlar[secili.alan].k = [k[0] + dx, k[1] + dy, k[2] + dx, k[3] + dy].map(function (v) {
                return Math.round(v * 10000) / 10000;
            });
            degisti(q);
            ciz();
            e.preventDefault();
        }
    });

    window.addEventListener('beforeunload', function (e) {
        if (kirli()) { e.preventDefault(); e.returnValue = ''; }
    });
    window.addEventListener('resize', function () { kagidiBoyutla(); });

    // Şüpheli sayfalar öncelikli: ilk kontrol bekleyen sayfadan başla.
    var ilkKontrol = veri.sayfalar.filter(sayfaKontrolMu)[0];
    aktifSayfa = ilkKontrol ? ilkKontrol.sira : 0;
    ciz();
    window.EKitapDuzelt = { durum: function () { return d; } };
})();
