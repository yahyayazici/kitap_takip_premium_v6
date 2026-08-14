(function () {
    "use strict";

    var cfg = window.OLCME_ZIMMET || {};
    var konuUrl = cfg.konuUrl || "";
    var kazanimUrl = cfg.kazanimUrl || "";
    var sinif = cfg.sinif || "7";
    var brans = cfg.brans || "";

    function debounce(fn, ms) {
        var t;
        return function () {
            var args = arguments;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(null, args); }, ms);
        };
    }

    function closeAll(except) {
        document.querySelectorAll(".olcme-ac-list.is-open").forEach(function (el) {
            if (el !== except) {
                el.classList.remove("is-open");
            }
        });
    }

    function bindKonu(input) {
        var wrap = input.closest(".olcme-ac-wrap");
        if (!wrap) return;
        var list = wrap.querySelector(".olcme-ac-list");
        var hidden = wrap.querySelector('input[type="hidden"][name="konu_id"]')
            || wrap.querySelector('input[type="hidden"][name="toplu_konu_id"]');
        if (!list || !hidden) return;

        var fetchOneri = debounce(function () {
            var q = input.value.trim();
            if (q.length < 2) {
                list.innerHTML = "";
                list.classList.remove("is-open");
                return;
            }
            var url = konuUrl + "?sinif=" + encodeURIComponent(sinif)
                + "&brans=" + encodeURIComponent(brans)
                + "&q=" + encodeURIComponent(q);
            fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    list.innerHTML = "";
                    (data.oneriler || []).forEach(function (o) {
                        var btn = document.createElement("button");
                        btn.type = "button";
                        btn.className = "olcme-ac-item";
                        btn.textContent = o.konu_ad + (o.brans_etiket ? " · " + o.brans_etiket : "");
                        btn.dataset.id = o.id;
                        btn.dataset.label = o.konu_ad;
                        btn.addEventListener("click", function () {
                            hidden.value = o.id;
                            input.value = o.konu_ad;
                            list.classList.remove("is-open");
                            var kWrap = wrap.closest("tr, .olcme-soru-card");
                            if (kWrap) {
                                var kInput = kWrap.querySelector(".olcme-kazanim-ac");
                                if (kInput) {
                                    kInput.dataset.konuId = o.id;
                                    kInput.value = "";
                                    var kHidden = kWrap.querySelector('input[name="kazanim_id"]');
                                    if (kHidden) kHidden.value = "";
                                }
                            }
                        });
                        list.appendChild(btn);
                    });
                    list.classList.toggle("is-open", list.children.length > 0);
                })
                .catch(function () {
                    list.classList.remove("is-open");
                });
        }, 280);

        input.addEventListener("input", fetchOneri);
        input.addEventListener("focus", fetchOneri);
        input.addEventListener("blur", function () {
            setTimeout(function () { list.classList.remove("is-open"); }, 180);
        });
    }

    function bindKazanim(input) {
        var wrap = input.closest(".olcme-ac-wrap");
        if (!wrap) return;
        var list = wrap.querySelector(".olcme-ac-list");
        var hidden = wrap.querySelector('input[type="hidden"][name="kazanim_id"]');
        if (!list || !hidden) return;

        var fetchOneri = debounce(function () {
            var konuId = input.dataset.konuId
                || wrap.closest("tr, .olcme-soru-card")?.querySelector('input[name="konu_id"]')?.value;
            if (!konuId) return;
            var q = input.value.trim();
            var url = kazanimUrl + "?konu_id=" + encodeURIComponent(konuId)
                + "&q=" + encodeURIComponent(q);
            fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    list.innerHTML = "";
                    (data.oneriler || []).forEach(function (o) {
                        var btn = document.createElement("button");
                        btn.type = "button";
                        btn.className = "olcme-ac-item";
                        btn.textContent = o.kazanim_ad;
                        btn.addEventListener("click", function () {
                            hidden.value = o.id;
                            input.value = o.kazanim_ad;
                            list.classList.remove("is-open");
                        });
                        list.appendChild(btn);
                    });
                    list.classList.toggle("is-open", list.children.length > 0);
                });
        }, 280);

        input.addEventListener("input", fetchOneri);
        input.addEventListener("focus", fetchOneri);
        input.addEventListener("blur", function () {
            setTimeout(function () { list.classList.remove("is-open"); }, 180);
        });
    }

    document.addEventListener("click", function (e) {
        if (!e.target.closest(".olcme-ac-wrap")) closeAll(null);
    });

    document.querySelectorAll(".olcme-konu-ac").forEach(bindKonu);
    document.querySelectorAll(".olcme-kazanim-ac").forEach(bindKazanim);
})();
