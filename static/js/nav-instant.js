(function () {
    "use strict";

    var seen = Object.create(null);
    var skipPath = /(?:^|\/)(?:logout|cikis)(?:\/|$)|(?:\.pdf$|\/pdf(?:\/|$)|download|export|xlsx|docx|zip)/i;

    function prefetchUrl(url) {
        if (!url || seen[url]) {
            return;
        }
        seen[url] = 1;
        var link = document.createElement("link");
        link.rel = "prefetch";
        link.href = url;
        link.as = "document";
        document.head.appendChild(link);
    }

    function hrefFromAnchor(anchor) {
        if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) {
            return "";
        }
        if ((anchor.getAttribute("hx-boost") || "") === "false") {
            return "";
        }
        var raw = anchor.getAttribute("href");
        if (!raw || raw.charAt(0) === "#" || raw.indexOf("javascript:") === 0 || raw.indexOf("mailto:") === 0) {
            return "";
        }
        var method = (anchor.getAttribute("data-method") || "get").toLowerCase();
        if (method !== "get") {
            return "";
        }
        try {
            var parsed = new URL(raw, window.location.href);
            if (parsed.origin !== window.location.origin) {
                return "";
            }
            if (parsed.pathname === window.location.pathname && parsed.search === window.location.search) {
                return "";
            }
            if (skipPath.test(parsed.pathname)) {
                return "";
            }
            return parsed.href;
        } catch (err) {
            return "";
        }
    }

    function fromEvent(event) {
        var node = event.target;
        if (!node || !node.closest) {
            return;
        }
        prefetchUrl(hrefFromAnchor(node.closest("a[href]")));
    }

    document.addEventListener("pointerover", fromEvent, { passive: true });
    document.addEventListener("touchstart", fromEvent, { capture: true, passive: true });
    document.addEventListener("focusin", fromEvent, { passive: true });
})();
