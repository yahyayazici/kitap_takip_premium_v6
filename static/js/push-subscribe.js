(function () {
    "use strict";

    if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        return;
    }

    var root = document.querySelector("[data-push-root]");
    if (!root) {
        return;
    }
    var vapidKey = root.getAttribute("data-vapid-key") || "";
    var subscribeUrl = root.getAttribute("data-subscribe-url") || "";
    var csrfToken = root.getAttribute("data-csrf") || "";
    if (!vapidKey || !subscribeUrl) {
        return;
    }

    function urlBase64ToUint8Array(base64String) {
        var padding = "=".repeat((4 - (base64String.length % 4)) % 4);
        var base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
        var rawData = window.atob(base64);
        var outputArray = new Uint8Array(rawData.length);
        for (var i = 0; i < rawData.length; i++) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify(body),
        });
    }

    function subscribe() {
        return navigator.serviceWorker.ready.then(function (registration) {
            return registration.pushManager
                .subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: urlBase64ToUint8Array(vapidKey),
                })
                .then(function (subscription) {
                    return postJson(subscribeUrl, subscription.toJSON());
                });
        });
    }

    function refreshButtons() {
        var permission = window.Notification.permission;
        root.querySelectorAll("[data-push-enable]").forEach(function (btn) {
            btn.hidden = permission === "granted";
        });
        root.querySelectorAll("[data-push-blocked]").forEach(function (btn) {
            btn.hidden = permission !== "denied";
        });
    }

    root.querySelectorAll("[data-push-enable]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            btn.disabled = true;
            window.Notification.requestPermission()
                .then(function (permission) {
                    if (permission === "granted") {
                        return subscribe();
                    }
                })
                .catch(function () {})
                .then(function () {
                    btn.disabled = false;
                    refreshButtons();
                });
        });
    });

    refreshButtons();

    if (window.Notification.permission === "granted") {
        navigator.serviceWorker.ready.then(function (registration) {
            registration.pushManager.getSubscription().then(function (existing) {
                if (!existing) {
                    subscribe();
                }
            });
        });
    }
})();
