/**
 * Panel kabuğu yerinde kalır; menü linki ve form aynı belgede içerik değiştirir.
 * Üzerine gelince sayfa belleğe alınır, tıklanınca hazırsa hemen basılır.
 */
(function () {
    "use strict";

    if (!document.body || !document.body.dataset.csShell) {
        return;
    }

    var SKIP = /(?:^|\/)(?:logout|cikis)(?:\/|$)|(?:\.pdf$|\/pdf(?:\/|$)|download|export|\.xlsx|\.docx|\.zip|\/excel(?:\/|$))/i;
    var cache = new Map();
    var pending = new Map();
    var scriptCache = new Map();
    var navToken = 0;
    var applyChain = Promise.resolve();
    var pageListeners = new AbortController();
    var shimDepth = 0;
    var origDocAdd = null;
    var origWinAdd = null;

    var bar = document.createElement("div");
    bar.className = "cs-instant-bar";
    bar.setAttribute("aria-hidden", "true");
    document.body.appendChild(bar);

    if (!history.state || !history.state.cs) {
        history.replaceState({ cs: 1, y: window.scrollY }, "");
    }

    function stripHash(url) {
        var parsed = new URL(url, window.location.href);
        parsed.hash = "";
        return parsed.href;
    }

    function skipUrl(url) {
        try {
            var parsed = new URL(url, window.location.href);
            if (parsed.origin !== window.location.origin) {
                return true;
            }
            if (SKIP.test(parsed.pathname)) {
                return true;
            }
            var query = parsed.search.toLowerCase();
            if (query.indexOf("format=pdf") !== -1 || query.indexOf("export=") !== -1) {
                return true;
            }
            return false;
        } catch (err) {
            return true;
        }
    }

    function isYonetimPath(pathname) {
        return pathname === "/yonetim" || pathname.indexOf("/yonetim/") === 0;
    }

    function crossesYonetim(url) {
        try {
            var parsed = new URL(url, window.location.href);
            return isYonetimPath(parsed.pathname) !== isYonetimPath(window.location.pathname);
        } catch (err) {
            return true;
        }
    }

    function hrefFromAnchor(anchor) {
        if (!anchor || anchor.hasAttribute("download") || anchor.hasAttribute("data-cs-full")) {
            return "";
        }
        if (anchor.target && anchor.target !== "_self") {
            return "";
        }
        if ((anchor.getAttribute("hx-boost") || "") === "false") {
            return "";
        }
        var raw = anchor.getAttribute("href");
        if (!raw || raw.charAt(0) === "#" || raw.indexOf("javascript:") === 0 || raw.indexOf("mailto:") === 0 || raw.indexOf("tel:") === 0) {
            return "";
        }
        try {
            var parsed = new URL(raw, window.location.href);
            if (skipUrl(parsed.href) || crossesYonetim(parsed.href)) {
                return "";
            }
            if (parsed.pathname === window.location.pathname && parsed.search === window.location.search) {
                return "";
            }
            return parsed.href;
        } catch (err) {
            return "";
        }
    }

    function cachePut(url, html) {
        if (!url || !html || html.length > 1500000) {
            return;
        }
        var key = stripHash(url);
        if (cache.has(key)) {
            cache.delete(key);
        }
        cache.set(key, html);
        while (cache.size > 8) {
            var oldest = cache.keys().next().value;
            cache.delete(oldest);
        }
    }

    function getHtml(url, opts) {
        var key = stripHash(url);
        if (cache.has(key)) {
            return Promise.resolve({ html: cache.get(key), finalUrl: key, url: key, ok: true });
        }
        if (pending.has(key)) {
            return pending.get(key);
        }
        var ctrl = new AbortController();
        var timer = window.setTimeout(function () {
            ctrl.abort();
        }, 30000);
        var init = {
            credentials: "same-origin",
            headers: { Accept: "text/html" },
            signal: ctrl.signal,
        };
        if (opts && opts.priority) {
            init.priority = opts.priority;
        }
        var job = fetch(key, init).then(function (res) {
            var type = res.headers.get("content-type") || "";
            var finalUrl = stripHash(res.url || key);
            if (type.indexOf("text/html") === -1) {
                return { html: "", finalUrl: finalUrl, url: key, binary: true, ok: res.ok };
            }
            return res.text().then(function (html) {
                if (res.ok) {
                    cachePut(key, html);
                    cachePut(finalUrl, html);
                }
                return { html: html, finalUrl: finalUrl, url: key, ok: res.ok, binary: false };
            });
        }).catch(function (err) {
            return { html: "", url: key, finalUrl: key, error: err };
        }).finally(function () {
            window.clearTimeout(timer);
            pending.delete(key);
        });
        pending.set(key, job);
        return job;
    }

    function prefetch(url) {
        if (!url) {
            return;
        }
        if (navigator.connection && navigator.connection.saveData) {
            return;
        }
        var key = stripHash(url);
        if (cache.has(key) || pending.has(key) || pending.size >= 2) {
            return;
        }
        getHtml(key);
    }

    function armBar() {
        document.documentElement.classList.add("cs-nav-on");
        bar.classList.remove("is-done");
        bar.classList.add("is-on");
        var page = document.getElementById("cs-page");
        if (page) {
            page.classList.add("cs-page-waiting");
            page.setAttribute("aria-busy", "true");
        }
    }

    function finishBar(token) {
        if (token !== navToken) {
            return;
        }
        document.documentElement.classList.remove("cs-nav-on");
        bar.classList.remove("is-on");
        bar.classList.add("is-done");
        var page = document.getElementById("cs-page");
        if (page) {
            page.classList.remove("cs-page-waiting");
            page.removeAttribute("aria-busy");
        }
        window.setTimeout(function () {
            bar.classList.remove("is-done");
        }, 180);
    }

    function showFail(message) {
        var box = document.getElementById("cs-messages");
        if (!box) {
            return;
        }
        box.replaceChildren();
        var wrap = document.createElement("div");
        wrap.className = "yonetim-messages";
        var note = document.createElement("div");
        note.className = "yonetim-message";
        note.textContent = message;
        wrap.appendChild(note);
        box.appendChild(wrap);
    }

    function normalizePath(path) {
        if (!path) {
            return "/";
        }
        if (path.length > 1 && !path.endsWith("/")) {
            return path + "/";
        }
        return path;
    }

    function updateActiveNav() {
        var current = normalizePath(window.location.pathname);
        var search = window.location.search;
        var links = document.querySelectorAll(
            ".v3-nav-link[href], .v3-nav-dropdown-link[href], #ogretmen-nav a[href], #talebe-nav a[href], #veli-nav a[href]"
        );
        var best = null;
        var bestScore = -1;
        links.forEach(function (link) {
            link.classList.remove("active");
        });
        document.querySelectorAll(".v3-nav-dropdown.is-section-active").forEach(function (drop) {
            drop.classList.remove("is-section-active");
        });
        links.forEach(function (link) {
            try {
                var parsed = new URL(link.href, window.location.origin);
                var path = normalizePath(parsed.pathname);
                var score = -1;
                if (path === current && parsed.search === search) {
                    score = 10000 + path.length;
                } else if (path === current) {
                    score = 5000 + path.length;
                } else if (path !== "/" && current.indexOf(path) === 0) {
                    score = path.length;
                }
                if (score > bestScore) {
                    bestScore = score;
                    best = link;
                }
            } catch (err) {
                /* geçersiz href */
            }
        });
        if (!best) {
            return;
        }
        best.classList.add("active");
        var drop = best.closest(".v3-nav-dropdown");
        if (drop) {
            drop.classList.add("is-section-active");
        }
    }

    function closeNav() {
        if (typeof window.csCloseMobileNav === "function") {
            window.csCloseMobileNav();
            return;
        }
        document.querySelectorAll(".v3-nav-dropdown.open, .v3-nav.open, .cs-v6-nav.open").forEach(function (el) {
            el.classList.remove("open");
        });
        document.body.classList.remove("v3-nav-menu-open", "v3-mobile-nav-open");
    }

    function mergeAssets(doc, baseUrl) {
        var have = Object.create(null);
        document.querySelectorAll("link[rel~='stylesheet']").forEach(function (link) {
            if (link.href) {
                have[link.href] = true;
            }
        });
        var styleHave = Object.create(null);
        document.head.querySelectorAll("style").forEach(function (style) {
            styleHave[style.textContent] = true;
        });
        doc.querySelectorAll("link[rel~='stylesheet']").forEach(function (link) {
            var raw = link.getAttribute("href");
            if (!raw) {
                return;
            }
            var abs;
            try {
                abs = new URL(raw, baseUrl).href;
            } catch (err) {
                return;
            }
            if (have[abs]) {
                return;
            }
            var el = document.createElement("link");
            el.rel = "stylesheet";
            el.href = abs;
            if (link.media) {
                el.media = link.media;
            }
            el.setAttribute("data-cs-dyn", "1");
            document.head.appendChild(el);
            have[abs] = true;
        });
        doc.head.querySelectorAll("style").forEach(function (style) {
            var text = style.textContent || "";
            if (!text || styleHave[text]) {
                return;
            }
            var el = document.createElement("style");
            el.textContent = text;
            el.setAttribute("data-cs-dyn", "1");
            document.head.appendChild(el);
            styleHave[text] = true;
        });
    }

    function describeScripts(root) {
        if (!root) {
            return [];
        }
        return Array.prototype.map.call(root.querySelectorAll("script"), function (script) {
            return {
                type: (script.getAttribute("type") || "").trim().toLowerCase(),
                src: script.getAttribute("src") || "",
                code: script.getAttribute("src") ? "" : (script.textContent || ""),
            };
        });
    }

    function runnable(type) {
        return !type || type === "text/javascript" || type === "application/javascript" || type === "text/ecmascript";
    }

    function withSignal(opts) {
        if (opts && typeof opts === "object" && opts.signal) {
            return opts;
        }
        var base = typeof opts === "boolean" ? { capture: opts } : Object.assign({}, opts || {});
        base.signal = pageListeners.signal;
        return base;
    }

    function docShim(type, fn, opts) {
        if (type === "DOMContentLoaded" || type === "load") {
            try {
                fn.call(document, { type: type });
            } catch (err) {
                console.error(err);
            }
            return;
        }
        return origDocAdd.call(document, type, fn, withSignal(opts));
    }

    function winShim(type, fn, opts) {
        if (type === "DOMContentLoaded" || type === "load") {
            try {
                fn.call(window, { type: type });
            } catch (err) {
                console.error(err);
            }
            return;
        }
        return origWinAdd.call(window, type, fn, withSignal(opts));
    }

    function installShim() {
        if (shimDepth === 0) {
            origDocAdd = document.addEventListener;
            origWinAdd = window.addEventListener;
            document.addEventListener = docShim;
            window.addEventListener = winShim;
        }
        shimDepth += 1;
    }

    function restoreShim() {
        shimDepth -= 1;
        if (shimDepth <= 0) {
            shimDepth = 0;
            if (origDocAdd) {
                document.addEventListener = origDocAdd;
            }
            if (origWinAdd) {
                window.addEventListener = origWinAdd;
            }
        }
    }

    function invoke(code, scriptEl) {
        if (!code || !code.trim()) {
            return;
        }
        var restoreCurrent = null;
        try {
            Object.defineProperty(document, "currentScript", {
                configurable: true,
                get: function () {
                    return scriptEl || null;
                },
            });
            restoreCurrent = function () {
                delete document.currentScript;
            };
        } catch (err) {
            restoreCurrent = null;
        }
        installShim();
        try {
            (new Function(code))();
        } catch (err) {
            console.error(err);
        } finally {
            restoreShim();
            if (restoreCurrent) {
                restoreCurrent();
            }
        }
    }

    function fetchScript(src) {
        var abs = new URL(src, window.location.href).href;
        if (scriptCache.has(abs)) {
            return Promise.resolve(scriptCache.get(abs));
        }
        return fetch(abs, { credentials: "same-origin" }).then(function (res) {
            if (!res.ok) {
                throw new Error(abs);
            }
            return res.text();
        }).then(function (text) {
            scriptCache.set(abs, text);
            return text;
        });
    }

    async function runList(descriptors, liveScripts, token) {
        for (var i = 0; i < descriptors.length; i += 1) {
            if (token !== navToken) {
                return;
            }
            var item = descriptors[i];
            if (!runnable(item.type)) {
                continue;
            }
            var el = liveScripts && liveScripts[i] ? liveScripts[i] : null;
            try {
                if (item.src) {
                    var code = await fetchScript(item.src);
                    if (token !== navToken) {
                        return;
                    }
                    invoke(code, el);
                } else {
                    invoke(item.code, el);
                }
            } catch (err) {
                console.error(err);
            }
        }
    }

    function filenameFrom(header) {
        var star = /filename\*=UTF-8''([^;]+)/i.exec(header || "");
        if (star) {
            try {
                return decodeURIComponent(star[1]);
            } catch (err) {
                return star[1];
            }
        }
        var plain = /filename="?([^";]+)"?/i.exec(header || "");
        return plain ? plain[1] : "indirilen-dosya";
    }

    async function downloadBlob(res) {
        var blob = await res.blob();
        var link = document.createElement("a");
        var obj = URL.createObjectURL(blob);
        link.href = obj;
        link.download = filenameFrom(res.headers.get("content-disposition"));
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(function () {
            URL.revokeObjectURL(obj);
        }, 1500);
    }

    async function applyPayload(payload, token, opts) {
        if (token !== navToken) {
            return "stale";
        }
        opts = opts || {};
        var dest = payload.finalUrl || payload.url;
        if (payload.error || payload.binary || !payload.html) {
            finishBar(token);
            if (payload.binary && dest) {
                window.location.href = dest;
                return "leave";
            }
            if (!opts.fromForm && dest) {
                window.location.href = dest;
                return "leave";
            }
            showFail("Sayfa açılamadı. Bağlantıyı kontrol edip tekrar deneyin.");
            return "fail";
        }

        var doc = new DOMParser().parseFromString(payload.html, "text/html");
        var newBody = doc.body;
        var shell = newBody && newBody.getAttribute("data-cs-shell");
        var nextPage = doc.getElementById("cs-page");
        var curPage = document.getElementById("cs-page");
        if (!newBody || shell !== document.body.getAttribute("data-cs-shell") || !nextPage || !curPage) {
            finishBar(token);
            var redirected = stripHash(payload.finalUrl || "") !== stripHash(payload.url || "");
            if (dest && (!opts.fromForm || redirected)) {
                document.documentElement.classList.remove("cs-nav-on");
                window.location.assign(dest);
                return "leave";
            }
            showFail("Kayıt tamamlanamadı. Sayfayı yenileyip tekrar deneyin.");
            return "fail";
        }
        if (token !== navToken) {
            return "stale";
        }

        var pageScripts = describeScripts(nextPage);
        var boot = doc.getElementById("cs-page-boot");
        var bootScripts = describeScripts(boot);
        var writes = pageScripts.concat(bootScripts).some(function (item) {
            return item.code && item.code.indexOf("document.write") !== -1;
        });
        if (writes) {
            finishBar(token);
            window.location.href = dest;
            return "leave";
        }

        var same = stripHash(dest) === stripHash(window.location.href);
        if (opts.push !== false) {
            if (!same) {
                history.replaceState({ cs: 1, y: window.scrollY }, "");
                history.pushState({ cs: 1, y: 0 }, "", dest);
            } else {
                history.replaceState({ cs: 1, y: 0 }, "", dest);
            }
        }

        mergeAssets(doc, dest);
        document.body.className = newBody.className;
        var title = doc.querySelector("title");
        if (title && title.textContent) {
            document.title = title.textContent;
        }

        var nextMsg = doc.getElementById("cs-messages");
        var curMsg = document.getElementById("cs-messages");
        if (nextMsg && curMsg) {
            curMsg.replaceWith(document.importNode(nextMsg, true));
        }

        var clone = document.importNode(nextPage, true);
        clone.querySelectorAll("script").forEach(function (script) {
            script.type = "text/plain";
        });
        curPage.replaceWith(clone);

        pageListeners.abort();
        pageListeners = new AbortController();

        await runList(pageScripts, clone.querySelectorAll("script"), token);
        if (token !== navToken) {
            return "stale";
        }
        await runList(bootScripts, [], token);
        if (token !== navToken) {
            return "stale";
        }

        closeNav();
        updateActiveNav();

        var hash = "";
        try {
            hash = new URL(dest, window.location.href).hash;
        } catch (err) {
            hash = "";
        }
        if (opts.fromForm && document.querySelector(".errorlist")) {
            document.querySelector(".errorlist").scrollIntoView({ block: "center" });
        } else if (hash.length > 1) {
            var anchor = document.getElementById(decodeURIComponent(hash.slice(1)));
            if (anchor) {
                anchor.scrollIntoView();
            } else {
                window.scrollTo(0, opts.scrollY || 0);
            }
        } else {
            window.scrollTo(0, opts.scrollY || 0);
        }

        document.dispatchEvent(new CustomEvent("cs:page"));
        finishBar(token);
        return "swap";
    }

    function go(url, opts) {
        opts = opts || {};
        var token = ++navToken;
        var key = stripHash(url);
        armBar();
        if (cache.has(key)) {
            applyPayload({ html: cache.get(key), finalUrl: key, url: key, ok: true }, token, opts);
            return;
        }
        applyChain = applyChain.then(function () {
            if (token !== navToken) {
                return;
            }
            return getHtml(url).then(function (payload) {
                return applyPayload(payload, token, opts);
            });
        }).catch(function (err) {
            console.error(err);
            finishBar(token);
            if (token === navToken) {
                window.location.href = url;
            }
        });
    }

    var warmGen = 0;

    function scheduleWarm() {
        if (navigator.connection && navigator.connection.saveData) {
            return;
        }
        var gen = ++warmGen;
        window.setTimeout(function () {
            if (gen !== warmGen || document.hidden) {
                return;
            }
            var urls = [];
            var seen = Object.create(null);
            function addUrl(anchor) {
                if (!anchor || urls.length >= 4) {
                    return;
                }
                var url = hrefFromAnchor(anchor);
                if (!url || seen[url] || cache.has(stripHash(url))) {
                    return;
                }
                seen[url] = 1;
                urls.push(url);
            }
            document.querySelectorAll("#cs-page a[href]").forEach(function (anchor) {
                var box = anchor.getBoundingClientRect();
                if (box.width < 8 || box.height < 8) {
                    return;
                }
                addUrl(anchor);
            });
            document.querySelectorAll(
                ".v3-nav-link[href], .v3-nav-dropdown-link[href], #ogretmen-nav a[href], #talebe-nav a[href], #veli-nav a[href]"
            ).forEach(addUrl);
            var index = 0;
            function next() {
                if (gen !== warmGen || index >= urls.length || document.hidden) {
                    return;
                }
                var url = urls[index];
                index += 1;
                getHtml(url, { priority: "low" }).finally(function () {
                    window.setTimeout(next, 240);
                });
            }
            next();
        }, 500);
    }

    function armSubmitter(el) {
        if (!el) {
            return function () {};
        }
        var row = el.closest("tr");
        var isInput = el.tagName === "INPUT";
        var plain = isInput ? (el.value || "") : (el.children.length ? "" : (el.textContent || "").trim());
        var prev = null;
        el.classList.add("is-saving");
        el.setAttribute("aria-busy", "true");
        if (row) {
            row.classList.add("is-saving");
        }
        if (plain && plain.length <= 48) {
            prev = plain;
            if (isInput) {
                el.value = "Kaydediliyor…";
            } else {
                el.textContent = "Kaydediliyor…";
            }
        }
        el.disabled = true;
        return function () {
            el.disabled = false;
            el.classList.remove("is-saving");
            el.removeAttribute("aria-busy");
            if (row) {
                row.classList.remove("is-saving");
            }
            if (prev != null) {
                if (isInput) {
                    el.value = prev;
                } else {
                    el.textContent = prev;
                }
            }
        };
    }

    function formMethod(form, submitter) {
        var method = (submitter && submitter.getAttribute("formmethod")) || form.getAttribute("method") || "get";
        return String(method).toLowerCase();
    }

    function formActionUrl(form, submitter) {
        var raw = (submitter && submitter.getAttribute("formaction")) || form.getAttribute("action") || window.location.href;
        try {
            var parsed = new URL(raw, window.location.href);
            parsed.hash = "";
            if (skipUrl(parsed.href)) {
                return null;
            }
            return parsed;
        } catch (err) {
            return null;
        }
    }

    function queryFromForm(form, submitter) {
        var data = new FormData(form);
        if (submitter && submitter.name) {
            data.append(submitter.name, submitter.value);
        }
        var params = new URLSearchParams();
        data.forEach(function (value, key) {
            if (typeof value === "string") {
                params.append(key, value);
            }
        });
        return params.toString();
    }

    function postForm(form, submitter, actionUrl) {
        var token = ++navToken;
        var data = new FormData(form);
        if (submitter && submitter.name) {
            data.append(submitter.name, submitter.value);
        }
        form.dataset.csBusy = "1";
        var restore = armSubmitter(submitter);
        armBar();
        var headers = { Accept: "text/html" };
        var csrf = data.get("csrfmiddlewaretoken");
        if (typeof csrf === "string" && csrf) {
            headers["X-CSRFToken"] = csrf;
        }
        applyChain = applyChain.then(function () {
            return fetch(actionUrl.href, {
                method: "POST",
                body: data,
                credentials: "same-origin",
                headers: headers,
                redirect: "follow",
            }).then(async function (res) {
                var type = res.headers.get("content-type") || "";
                if (type.indexOf("text/html") === -1) {
                    await downloadBlob(res);
                    restore();
                    delete form.dataset.csBusy;
                    finishBar(token);
                    return;
                }
                var html = await res.text();
                var finalUrl = stripHash(res.url || actionUrl.href);
                if (res.ok) {
                    cachePut(finalUrl, html);
                }
                return applyPayload({
                    html: html,
                    finalUrl: finalUrl,
                    url: actionUrl.href,
                    ok: res.ok,
                }, token, { push: true, scrollY: 0, fromForm: true }).then(function (status) {
                    if (status !== "swap") {
                        restore();
                        delete form.dataset.csBusy;
                    }
                });
            }).catch(function () {
                restore();
                delete form.dataset.csBusy;
                finishBar(token);
                showFail("Bağlantı kurulamadı. Kayıt gitmemiş olabilir.");
            });
        });
    }

    document.addEventListener("pointerover", function (event) {
        var node = event.target;
        if (!node || !node.closest) {
            return;
        }
        prefetch(hrefFromAnchor(node.closest("a[href]")));
    }, { passive: true });

    document.addEventListener("pointerdown", function (event) {
        var node = event.target;
        if (!node || !node.closest) {
            return;
        }
        prefetch(hrefFromAnchor(node.closest("a[href]")));
    }, true);

    document.addEventListener("focusin", function (event) {
        var node = event.target;
        if (!node || !node.closest) {
            return;
        }
        prefetch(hrefFromAnchor(node.closest("a[href]")));
    });

    document.addEventListener("click", function (event) {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
        }
        var link = event.target && event.target.closest ? event.target.closest("a[href]") : null;
        var url = hrefFromAnchor(link);
        if (!url) {
            return;
        }
        event.preventDefault();
        go(url, { push: true, scrollY: 0 });
    });

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || form.tagName !== "FORM" || event.defaultPrevented) {
            return;
        }
        if (form.dataset.csBusy === "1") {
            event.preventDefault();
            return;
        }
        if (form.hasAttribute("data-cs-full")) {
            return;
        }
        if ((form.getAttribute("hx-boost") || "") === "false") {
            return;
        }
        if (form.target && form.target !== "_self") {
            return;
        }
        var submitter = event.submitter || null;
        if (submitter) {
            var target = submitter.getAttribute("formtarget");
            if (target && target !== "_self") {
                return;
            }
        }
        var actionUrl = formActionUrl(form, submitter);
        if (!actionUrl) {
            return;
        }
        var method = formMethod(form, submitter);
        if (method === "dialog") {
            return;
        }
        event.preventDefault();
        if (method === "get") {
            actionUrl.search = queryFromForm(form, submitter);
            go(actionUrl.href, { push: true, scrollY: 0 });
            return;
        }
        postForm(form, submitter, actionUrl);
    });

    window.addEventListener("popstate", function (event) {
        if (crossesYonetim(window.location.href)) {
            window.location.reload();
            return;
        }
        var y = event.state && typeof event.state.y === "number" ? event.state.y : 0;
        go(window.location.href, { push: false, scrollY: y });
    });

    document.addEventListener("cs:page", scheduleWarm);
    scheduleWarm();
})();
