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

self.addEventListener("push", function (event) {
    var data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (err) {
        data = { title: "Bildirim", body: event.data ? event.data.text() : "" };
    }
    var title = data.title || "Çinili Saray Proje";
    var options = {
        body: data.body || "",
        icon: "/pwa/icon-192.png",
        badge: "/pwa/icon-192.png",
        data: { url: data.url || "/panel/" },
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
    event.notification.close();
    var url = (event.notification.data && event.notification.data.url) || "/panel/";
    event.waitUntil(
        self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clientList) {
            for (var i = 0; i < clientList.length; i++) {
                var client = clientList[i];
                if (client.url.indexOf(self.location.origin) === 0 && "focus" in client) {
                    client.navigate(url);
                    return client.focus();
                }
            }
            if (self.clients.openWindow) {
                return self.clients.openWindow(url);
            }
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
