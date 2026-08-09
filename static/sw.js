/* Çinili Saray Proje — minimal service worker (ana ekrana ekle / yükle) */

const SW_VERSION = "csp-pwa-5";

self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
    event.respondWith(fetch(event.request));
});
