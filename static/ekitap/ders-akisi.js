/* E-Kitap — ders akışı: öğretmen kitaptan soru seçip sıralar, derste sırayla açar.
 *
 * Sunucuda yalnızca akışın adı, soru kimlikleri ve sıraları saklanır. Çözüm ve
 * çizimler akışa girmez (bkz. cizim.js).
 */
(function () {
    'use strict';

    var panel = document.getElementById('akisPaneli');
    var SG = window.EKitapSoru;
    if (!panel || !SG) return;

    var $ = function (id) { return document.getElementById(id); };
    var ayar = $('akisAyar');
    var KAYDET_URL = ayar.getAttribute('data-kaydet');
    var SIL_URL = ayar.getAttribute('data-sil'); // .../akis/0/sil/
    var CSRF = ayar.querySelector('input[name=csrfmiddlewaretoken]').value;
    var btn = $('dersAkisiBtn');
    var okuyucu = $('okuyucu');

    var akislar = JSON.parse($('ekitapAkislar').textContent);
    var duzenlenen = null; // { id|null, ad, sorular: [soruId] }
    var veri = JSON.parse(document.getElementById('ekitapVeri').textContent);

    // soru kimliği → { bolum, soru, indeks (kitap sırası) }
    var soruHaritasi = {};
    SG.sorular.forEach(function (k, i) { soruHaritasi[k.soru.id] = { b: k.b, soru: k.soru, indeks: i }; });

    function soruEtiketi(id) {
        var k = soruHaritasi[id];
        if (!k) return 'Soru';
        var parca = [];
        if (veri.length > 1) parca.push(veri[k.b].ad);
        var testler = {};
        (veri[k.b].sorular || []).forEach(function (s) { testler[s.t] = true; });
        if (Object.keys(testler).length > 1) parca.push(k.soru.t + '. test');
        parca.push(k.soru.no + '. soru');
        return parca.join(' · ');
    }

    function kacis(m) {
        return String(m).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    // —— Görünüm ——————————————————————————————————————————————————————
    function listeCiz() {
        var gecerli = akislar.map(function (a) {
            return { a: a, sorular: a.sorular.filter(function (id) { return soruHaritasi[id]; }) };
        });
        $('akisListesi').innerHTML = gecerli.map(function (g) {
            return '<li class="ek-akis-oge"><div class="ek-akis-oge-bilgi"><strong>' + kacis(g.a.ad) + '</strong><span>' +
                g.sorular.length + ' soru</span></div><div class="ek-akis-oge-eylem">' +
                '<button type="button" class="ek-soru-dugme ek-soru-kapat ek-akis-baslat" data-baslat="' + g.a.id + '"' +
                (g.sorular.length ? '' : ' disabled') + '>Başlat</button>' +
                '<button type="button" class="ek-akis-kucuk" data-duzenle="' + g.a.id + '">Düzenle</button>' +
                '<button type="button" class="ek-akis-kucuk ek-akis-tehlike" data-sil="' + g.a.id + '">Sil</button></div></li>';
        }).join('');
        $('akisBos').hidden = akislar.length > 0;
    }

    function secilenCiz() {
        var s = duzenlenen.sorular;
        $('akisSecilen').innerHTML = s.length ? s.map(function (id, i) {
            return '<li><span class="ek-akis-no">' + (i + 1) + '</span><span class="ek-akis-ad-metin">' + kacis(soruEtiketi(id)) +
                '</span><button type="button" class="ek-akis-kucuk" data-yukari="' + i + '" aria-label="Yukarı"' + (i ? '' : ' disabled') + '>↑</button>' +
                '<button type="button" class="ek-akis-kucuk" data-asagi="' + i + '" aria-label="Aşağı"' + (i < s.length - 1 ? '' : ' disabled') + '>↓</button>' +
                '<button type="button" class="ek-akis-kucuk ek-akis-tehlike" data-cikar="' + i + '" aria-label="Çıkar">×</button></li>';
        }).join('') : '<li class="ek-akis-bos-satir">Henüz soru seçilmedi.</li>';
        rozetleriIsaretle();
    }

    function rozetleriIsaretle() {
        var sira = {};
        if (duzenlenen) duzenlenen.sorular.forEach(function (id, i) { sira[id] = i + 1; });
        Array.prototype.forEach.call(document.querySelectorAll('.ek-buyutec'), function (r) {
            var n = sira[r.getAttribute('data-soru')];
            r.classList.toggle('ek-akista', !!n);
            if (n) r.setAttribute('data-akis-sira', String(n)); else r.removeAttribute('data-akis-sira');
        });
    }

    function hata(metin) {
        $('akisHata').hidden = !metin;
        $('akisHata').textContent = metin || '';
    }

    function goster(duzen) {
        $('akisListeGorunumu').hidden = duzen;
        $('akisDuzenGorunumu').hidden = !duzen;
        $('akisBaslik').textContent = duzen ? (duzenlenen.id ? 'Ders akışını düzenle' : 'Yeni ders akışı') : 'Ders akışları';
        okuyucu.classList.toggle('ek-akis-seciyor', duzen);
        hata('');
        if (duzen) secilenCiz(); else { rozetleriIsaretle(); listeCiz(); }
    }

    function panelAc() {
        panel.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        goster(!!duzenlenen);
    }

    function panelKapat() {
        duzenlenen = null;
        panel.hidden = true;
        btn.setAttribute('aria-expanded', 'false');
        okuyucu.classList.remove('ek-akis-seciyor');
        rozetleriIsaretle();
    }

    function duzenle(akis) {
        duzenlenen = {
            id: akis ? akis.id : null,
            ad: akis ? akis.ad : '',
            sorular: akis ? akis.sorular.filter(function (id) { return soruHaritasi[id]; }) : []
        };
        $('akisAd').value = duzenlenen.ad;
        goster(true);
        if (!akis) $('akisAd').focus();
    }

    // —— Sunucu ———————————————————————————————————————————————————————
    function gonder(url, govde, tamam) {
        var istek = new XMLHttpRequest();
        istek.open('POST', url);
        istek.setRequestHeader('Content-Type', 'application/json');
        istek.setRequestHeader('X-CSRFToken', CSRF);
        istek.onload = function () {
            var cevap = null;
            try { cevap = JSON.parse(istek.responseText); } catch (h) { /* yok */ }
            if (istek.status === 200 && cevap && cevap.tamam) {
                akislar = cevap.akislar;
                tamam(cevap);
            } else if (istek.status === 403) {
                hata('Oturum süresi doldu. Sayfayı yenileyip PIN girin.');
            } else {
                hata((cevap && cevap.hata) || 'Kaydedilemedi. Bağlantıyı kontrol edin.');
            }
        };
        istek.onerror = function () { hata('Kaydedilemedi. Bağlantıyı kontrol edin.'); };
        istek.send(govde ? JSON.stringify(govde) : '{}');
    }

    function kaydet() {
        duzenlenen.ad = $('akisAd').value.trim();
        if (!duzenlenen.ad) { hata('Ders akışına bir ad verin.'); $('akisAd').focus(); return; }
        if (!duzenlenen.sorular.length) { hata('Kitaptaki büyüteçlere dokunarak en az bir soru seçin.'); return; }
        gonder(KAYDET_URL, { id: duzenlenen.id, ad: duzenlenen.ad, sorular: duzenlenen.sorular }, function () {
            duzenlenen = null;
            goster(false);
        });
    }

    function sil(id) {
        var akis = akislar.filter(function (a) { return a.id === id; })[0];
        if (!akis || !window.confirm('“' + akis.ad + '” ders akışı silinsin mi?')) return;
        gonder(SIL_URL.replace('/0/sil/', '/' + id + '/sil/'), null, function () { listeCiz(); });
    }

    function baslat(id) {
        var akis = akislar.filter(function (a) { return a.id === id; })[0];
        if (!akis) return;
        var indeksler = akis.sorular.filter(function (s) { return soruHaritasi[s]; })
            .map(function (s) { return soruHaritasi[s].indeks; });
        if (!indeksler.length) return;
        panelKapat();
        SG.listeAc(indeksler, akis.ad, btn);
    }

    // —— Olaylar ——————————————————————————————————————————————————————
    btn.addEventListener('click', function () {
        if (panel.hidden) panelAc(); else if (!duzenlenen) panelKapat();
        else panel.querySelector('#akisAd').focus();
    });
    $('akisKapat').addEventListener('click', panelKapat);
    $('akisYeni').addEventListener('click', function () { duzenle(null); });
    $('akisVazgec').addEventListener('click', function () { duzenlenen = null; goster(false); });
    $('akisKaydet').addEventListener('click', kaydet);
    $('akisListesi').addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b) return;
        if (b.hasAttribute('data-baslat')) baslat(parseInt(b.getAttribute('data-baslat'), 10));
        else if (b.hasAttribute('data-duzenle')) {
            var id = parseInt(b.getAttribute('data-duzenle'), 10);
            duzenle(akislar.filter(function (a) { return a.id === id; })[0]);
        } else if (b.hasAttribute('data-sil')) sil(parseInt(b.getAttribute('data-sil'), 10));
    });
    $('akisSecilen').addEventListener('click', function (e) {
        var b = e.target.closest('button');
        if (!b || !duzenlenen) return;
        var s = duzenlenen.sorular;
        var i;
        if (b.hasAttribute('data-yukari')) { i = +b.getAttribute('data-yukari'); s.splice(i - 1, 0, s.splice(i, 1)[0]); }
        else if (b.hasAttribute('data-asagi')) { i = +b.getAttribute('data-asagi'); s.splice(i + 1, 0, s.splice(i, 1)[0]); }
        else if (b.hasAttribute('data-cikar')) { s.splice(+b.getAttribute('data-cikar'), 1); }
        secilenCiz();
    });
    $('akisAd').addEventListener('keydown', function (e) {
        e.stopPropagation(); // kitap kısayolları (boşluk, oklar) yazarken çalışmasın
        if (e.key === 'Enter') kaydet();
    });
    // Kitap yeniden kurulunca (boyut/sekme) rozetler yeniden oluşur.
    document.addEventListener('ek-kitap-kuruldu', rozetleriIsaretle);

    window.EKitapAkis = {
        seciyor: function () { return !!duzenlenen && !panel.hidden; },
        degistir: function (soruId) {
            if (!duzenlenen || !soruHaritasi[soruId]) return;
            var i = duzenlenen.sorular.indexOf(soruId);
            if (i >= 0) duzenlenen.sorular.splice(i, 1); else duzenlenen.sorular.push(soruId);
            hata('');
            secilenCiz();
        }
    };
    listeCiz();
})();
