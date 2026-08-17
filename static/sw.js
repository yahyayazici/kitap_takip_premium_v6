/* Çinili Saray Proje — minimal service worker (ana ekrana ekle / yükle) */

const SW_VERSION = "csp-pwa-11";

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

    let url;
    try {
        url = new URL(req.url);
    } catch (e) {
        return;
    }

    const path = url.pathname.toLowerCase();
    const format = (url.searchParams.get("format") || "").toLowerCase();
    // PDF / Excel indirmelerine dokunma — Chrome attachment'ı SW üzerinden yutuyor
    if (
        path.includes("pdf") ||
        path.includes("excel") ||
        path.includes("ek-indir") ||
        format === "pdf" ||
        format === "xlsx" ||
        format === "xls"
    ) {
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
