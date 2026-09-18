/* ============================================================
   Çinili Saray — Görüntüleyici Service Worker
   ------------------------------------------------------------
   Amaç: internet kesildiğinde televizyonun boş ya da hata
   ekranı göstermemesi. Son yayının HTML/CSS/JS kabuğu ve
   medya dosyaları önbellekte tutulur.

   Strateji:
     · Kabuk (HTML/CSS/JS): önce önbellek, arkada tazele
     · Medya (görsel/video/PDF sayfası): önce önbellek
     · API: yalnız ağ — bayat yayın damgası asla oynatılmaz

   Bu dosya /sw.js olarak kök kapsamda servis edilir; sürüm ve
   kabuk listesi sunucu tarafından başa eklenir (bkz.
   takip/ekran_viewer_views.py).
   ============================================================ */
'use strict';

var SURUM = self.EKRAN_SURUM || 'ekran-v1';
// Görüntüleyicinin kökü: alt alan adında "/", ana sitede "/tv/".
var TEMEL = self.EKRAN_TEMEL || '/';
var KABUK_ONBELLEK = SURUM + '-kabuk';
var MEDYA_ONBELLEK = SURUM + '-medya';
var KABUK = self.EKRAN_KABUK || [TEMEL];

// Televizyonda sınırsız disk yok; en eski medya kayıtları atılır.
var MEDYA_SINIRI = 220;

self.addEventListener('install', function (olay) {
    olay.waitUntil(
        caches.open(KABUK_ONBELLEK)
            .then(function (onbellek) { return onbellek.addAll(KABUK); })
            .catch(function () { /* biri indirilemezse kurulum yine de sürsün */ })
            .then(function () { return self.skipWaiting(); })
    );
});

self.addEventListener('activate', function (olay) {
    olay.waitUntil(
        caches.keys().then(function (adlar) {
            return Promise.all(adlar.map(function (ad) {
                if (ad.indexOf(SURUM) !== 0) { return caches.delete(ad); }
                return null;
            }));
        }).then(function () { return self.clients.claim(); })
    );
});

function medyaMi(istek) {
    // Ekran medyası kendi kalıcı diskinde, /ekran-medya/ altında durur.
    var yol = new URL(istek.url).pathname;
    return yol.indexOf('/ekran-medya/') === 0
        || yol.indexOf('/media/') === 0
        || yol.indexOf('/static/ekran/') === 0;
}

function apiMi(istek) {
    return new URL(istek.url).pathname.indexOf(TEMEL + 'api/') === 0;
}

function onbellegiBudama(adi, sinir) {
    return caches.open(adi).then(function (onbellek) {
        return onbellek.keys().then(function (anahtarlar) {
            if (anahtarlar.length <= sinir) { return null; }
            return Promise.all(
                anahtarlar.slice(0, anahtarlar.length - sinir).map(function (a) {
                    return onbellek.delete(a);
                })
            );
        });
    });
}

self.addEventListener('fetch', function (olay) {
    var istek = olay.request;
    if (istek.method !== 'GET') { return; }

    // API yanıtları asla önbellekten verilmez — bayat yayın oynatılmamalı.
    if (apiMi(istek)) { return; }

    if (medyaMi(istek)) {
        olay.respondWith(
            caches.match(istek).then(function (yanit) {
                if (yanit) { return yanit; }
                return fetch(istek).then(function (ag) {
                    if (ag && ag.status === 200) {
                        var kopya = ag.clone();
                        caches.open(MEDYA_ONBELLEK).then(function (onbellek) {
                            onbellek.put(istek, kopya);
                            onbellegiBudama(MEDYA_ONBELLEK, MEDYA_SINIRI);
                        });
                    }
                    return ag;
                });
            })
        );
        return;
    }

    // Kabuk: önbellekten hemen ver, arkada tazele.
    olay.respondWith(
        caches.match(istek).then(function (onbellekYaniti) {
            var agSozu = fetch(istek).then(function (ag) {
                if (ag && ag.status === 200) {
                    var kopya = ag.clone();
                    caches.open(KABUK_ONBELLEK).then(function (onbellek) {
                        onbellek.put(istek, kopya);
                    });
                }
                return ag;
            }).catch(function () {
                return onbellekYaniti || caches.match(TEMEL);
            });
            return onbellekYaniti || agSozu;
        })
    );
});

// Görüntüleyici yeni yayın alınca gelecek sahnelerin dosyalarını önden indirtir.
self.addEventListener('message', function (olay) {
    var veri = olay.data || {};
    if (veri.tur !== 'varliklari-onbellege' || !Array.isArray(veri.adresler)) { return; }

    olay.waitUntil(
        caches.open(MEDYA_ONBELLEK).then(function (onbellek) {
            return Promise.all(veri.adresler.slice(0, MEDYA_SINIRI).map(function (adres) {
                return onbellek.match(adres).then(function (mevcut) {
                    if (mevcut) { return null; }
                    return fetch(adres, { cache: 'no-store' }).then(function (yanit) {
                        if (yanit && yanit.status === 200) { return onbellek.put(adres, yanit); }
                        return null;
                    }).catch(function () { return null; });
                });
            }));
        }).then(function () { return onbellegiBudama(MEDYA_ONBELLEK, MEDYA_SINIRI); })
    );
});
