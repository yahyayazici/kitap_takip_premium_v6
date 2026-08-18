/* Çinili Saray Proje — PWA SW: statik dosyaları cache'ler, HTML'i bekletmez */

const SW_VERSION = "csp-pwa-14";
const STATIC_CACHE = SW_VERSION + "-static";

self.addEventListener("install", function () {
    self.skipWaiting();
});

self.addEventListener("activate", function (event) {
    event.waitUntil(
        caches.keys().then(function (keys) {
            return Promise.all(
                keys.map(function (key) {
                    if (key !== STATIC_CACHE) {
                        return caches.delete(key);
                    }
                })
            );
        }).then(function () {
            return self.clients.claim();
        })
    );
});

self.addEventListener("fetch", function (event) {
    var request = event.request;
    if (request.method !== "GET") {
        return;
    }
    var url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }
    if (url.pathname.indexOf("/static/") !== 0) {
        return;
    }
    event.respondWith(
        caches.open(STATIC_CACHE).then(function (cache) {
            return cache.match(request).then(function (cached) {
                if (cached) {
                    return cached;
                }
                return fetch(request).then(function (response) {
                    if (response && response.ok) {
                        cache.put(request, response.clone());
                    }
                    return response;
                });
            });
        })
    );
});
