/* Çinili Saray Proje — PWA kurulum SW (isteklere girmez) */

const SW_VERSION = "csp-pwa-12";

self.addEventListener("install", function () {
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.map(function (key) {
                    return caches.delete(key);
                })
            );
        })
    );
});

/* Fetch dinleyicisi PWA için gerekli; respondWith yok = tarayıcı native gider.
   Eski SW her GET'i sarıp mobil beyaz ekran / takılma yapıyordu. */
self.addEventListener("fetch", function () {});
