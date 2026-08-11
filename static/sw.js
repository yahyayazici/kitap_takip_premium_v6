/* Çinili Saray Proje — minimal service worker (ana ekrana ekle / yükle) */

const SW_VERSION = "csp-pwa-10";

self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
    const req = event.request;
    if (req.method !== "GET") {
        return;
    }
    event.respondWith(
        fetch(req).catch(function () {
            if (req.mode === "navigate") {
                return fetch("/pwa/baslat/");
            }
            throw new Error("offline");
        })
    );
});
