(function () {
    "use strict";

    function csrfToken() {
        var scoped = document.querySelector(
            "[data-sb-siparis] [name=csrfmiddlewaretoken], [data-sb-satis] [name=csrfmiddlewaretoken], [data-sb-borc] [name=csrfmiddlewaretoken]"
        );
        if (scoped && scoped.value) return scoped.value;
        var el = document.querySelector("[name=csrfmiddlewaretoken]");
        if (el && el.value) return el.value;
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                Accept: "application/json",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(body || {}),
        }).then(function (res) {
            return res.text().then(function (text) {
                var data = {};
                try {
                    data = text ? JSON.parse(text) : {};
                } catch (err) {
                    throw new Error("Kayıt alınamadı. Sayfayı yenileyip tekrar deneyin.");
                }
                if (!res.ok || !data.ok) {
                    throw new Error(data.hata || "İşlem başarısız.");
                }
                return data;
            });
        });
    }

    function applyOzet(root, ozet) {
        if (!ozet) return;
        var map = {
            toplam_siparis_adedi: String(ozet.toplam_siparis_adedi),
            satisi_yapilan: String(ozet.satisi_yapilan),
            bekleyen: String(ozet.bekleyen),
            pesin_tahsil: ozet.pesin_tahsil + " ₺",
            borca_yazilan: ozet.borca_yazilan + " ₺",
        };
        Object.keys(map).forEach(function (key) {
            var node = root.querySelector('[data-ozet="' + key + '"]');
            if (node) node.textContent = map[key];
        });
    }

    function parseAdet(raw) {
        if (raw === "" || raw === null || typeof raw === "undefined") return 0;
        var n = parseInt(String(raw), 10);
        if (isNaN(n) || n < 0) return 0;
        if (n > 20) return 20;
        return n;
    }

    function siparisHatasiGoster(root, message) {
        var box = root.querySelector("[data-sb-error]");
        if (!box) {
            box = document.createElement("p");
            box.className = "sb-inline-error";
            box.setAttribute("data-sb-error", "");
            box.setAttribute("role", "alert");
            var banner = root.querySelector(".sb-menu-banner");
            if (banner && banner.parentNode) {
                banner.parentNode.insertBefore(box, banner.nextSibling);
            } else {
                root.insertBefore(box, root.firstChild);
            }
        }
        box.textContent = message;
        box.removeAttribute("hidden");
        box.hidden = false;
        window.clearTimeout(siparisHatasiGoster._t);
        siparisHatasiGoster._t = window.setTimeout(function () {
            box.hidden = true;
        }, 7000);
    }

    function initSiparis(root) {
        var api = root.getAttribute("data-api");
        var tarih = root.getAttribute("data-tarih");
        var busy = new Set();
        var timers = {};
        var pending = {};

        function restore(row, input) {
            if (!input) return;
            var saved = row.getAttribute("data-saved");
            input.value = saved === null || saved === "" ? "" : saved;
        }

        function kaydet(row, adet, input) {
            var talebeId = row.getAttribute("data-talebe");
            if (!talebeId) return;
            if (busy.has(talebeId)) {
                pending[talebeId] = adet;
                return;
            }
            busy.add(talebeId);
            row.classList.add("is-busy");
            postJson(api, { tarih: tarih, talebe_id: Number(talebeId), adet: adet })
                .then(function () {
                    row.setAttribute("data-saved", String(adet));
                    if (input && adet === 0) input.value = "";
                    else if (input) input.value = String(adet);
                    var box = root.querySelector("[data-sb-error]");
                    if (box) {
                        box.hidden = true;
                        box.setAttribute("hidden", "");
                    }
                })
                .catch(function (err) {
                    delete pending[talebeId];
                    restore(row, input);
                    siparisHatasiGoster(root, err.message);
                })
                .finally(function () {
                    busy.delete(talebeId);
                    row.classList.remove("is-busy");
                    if (!Object.prototype.hasOwnProperty.call(pending, talebeId)) return;
                    var next = pending[talebeId];
                    delete pending[talebeId];
                    var saved = row.getAttribute("data-saved");
                    if (saved !== null && saved !== "" && String(next) === saved) return;
                    if (next === 0 && (saved === null || saved === "")) return;
                    kaydet(row, next, input);
                });
        }

        function fromInput(input, opts) {
            opts = opts || {};
            var row = input.closest("tr");
            if (!row || row.getAttribute("data-teslim") === "1") return;
            var adet = parseAdet(input.value);
            var prev = row.getAttribute("data-saved");
            var hadPrev = prev !== null && prev !== "";
            if (adet === 0 && !hadPrev) return;
            if (hadPrev && String(adet) === prev) return;
            if (!opts.commit && adet === 0) return;
            kaydet(row, adet, input);
        }

        function applyNameFilter() {
            var search = root.querySelector("[data-sb-name]");
            var q = search ? (search.value || "").trim().toLowerCase() : "";
            root.querySelectorAll("[data-talebe]").forEach(function (row) {
                var name = row.getAttribute("data-name") || "";
                row.hidden = !!(q && name.indexOf(q) === -1);
            });
            root.querySelectorAll("[data-sb-grup]").forEach(function (grup) {
                grup.hidden = !grup.querySelector("[data-talebe]:not([hidden])");
            });
        }

        root.addEventListener("click", function (ev) {
            var cell = ev.target.closest(".sb-qty-cell");
            if (!cell) return;
            var row = cell.closest("tr[data-teslim='1']");
            if (!row) return;
            siparisHatasiGoster(root, "Teslim edilmiş sipariş değiştirilemez. Önce satışı geri alın.");
        });

        root.addEventListener("change", function (ev) {
            var input = ev.target.closest(".sb-adet-input");
            if (!input) return;
            var row = input.closest("tr");
            var key = row && row.getAttribute("data-talebe");
            if (key) window.clearTimeout(timers[key]);
            fromInput(input, { commit: true });
        });

        root.addEventListener("input", function (ev) {
            if (ev.target.closest("[data-sb-name]")) {
                applyNameFilter();
                return;
            }
            var input = ev.target.closest(".sb-adet-input");
            if (!input) return;
            var row = input.closest("tr");
            var key = row && row.getAttribute("data-talebe");
            if (!key) return;
            window.clearTimeout(timers[key]);
            timers[key] = window.setTimeout(function () {
                fromInput(input, { commit: false });
            }, 350);
        });

        root.addEventListener("blur", function (ev) {
            var input = ev.target.closest && ev.target.closest(".sb-adet-input");
            if (!input) return;
            var row = input.closest("tr");
            var key = row && row.getAttribute("data-talebe");
            if (key) window.clearTimeout(timers[key]);
            fromInput(input, { commit: true });
        }, true);
    }

    function paintRow(tr, s, canSatis) {
        tr.className = s.teslim_edildi ? "is-sold" : "";
        tr.setAttribute("data-id", s.id);
        tr.setAttribute("data-teslim", s.teslim_edildi ? "1" : "0");
        tr.setAttribute("data-odeme", s.odeme_turu);
        tr.setAttribute("data-borc", s.borc_acik ? "1" : "0");
        tr.setAttribute("data-etut", String(s.etut_id || 0));
        tr.setAttribute("data-ad", (s.talebe || "").toLowerCase());
        tr.setAttribute("data-sinif", (s.sinif || "").toLowerCase());
        var meta = "";
        if (s.teslim_edildi) {
            meta = '<small class="sb-meta">' + (s.teslim_saati || "") + (s.teslim_eden ? " · " + s.teslim_eden : "") + "</small>";
        }
        var disabledPay = !canSatis || s.borc_kapatildi ? " disabled" : "";
        var disabledTick = !canSatis ? " disabled" : "";
        var borcOn = s.odeme_turu === "borc";
        tr.innerHTML =
            "<td><strong>" + s.talebe + "</strong>" + meta + "</td>" +
            "<td>" + s.etut + "<br><small>" + s.sinif + "</small></td>" +
            "<td>" + s.adet + "</td>" +
            '<td class="sb-tutar">' + s.tutar_etiket + "</td>" +
            '<td class="sb-borc-cell"><button type="button" class="sb-pay-btn' + (borcOn ? " is-on" : "") + '" data-pay="borc" aria-pressed="' + (borcOn ? "true" : "false") + '"' + disabledPay + ">Borç</button></td>" +
            '<td class="sb-tick-col"><button type="button" class="sb-tick' + (s.teslim_edildi ? " is-done" : "") + '" data-tick' + disabledTick + ' aria-pressed="' + (s.teslim_edildi ? "true" : "false") + '" aria-label="Teslim / satış"><span class="sb-tick-icon" aria-hidden="true"></span></button></td>';
    }

    function initSatis(root) {
        var pollUrl = root.getAttribute("data-poll");
        var teslimUrl = root.getAttribute("data-teslim-api") || root.getAttribute("data-teslim");
        var odemeUrl = root.getAttribute("data-odeme-api") || root.getAttribute("data-odeme");
        var tarih = root.getAttribute("data-tarih");
        var canSatis = root.getAttribute("data-satis") === "1";
        var tbody = root.querySelector("[data-sb-rows]");
        var busy = new Set();
        var filter = "tumu";
        var q = "";
        var etut = "";

        function applyFilters() {
            if (!tbody) return;
            tbody.querySelectorAll("tr[data-id]").forEach(function (tr) {
                var teslim = tr.getAttribute("data-teslim") === "1";
                var borc = tr.getAttribute("data-borc") === "1";
                var ad = tr.getAttribute("data-ad") || "";
                var sinif = tr.getAttribute("data-sinif") || "";
                var et = tr.getAttribute("data-etut") || "";
                var ok = true;
                if (filter === "bekleyen") ok = !teslim;
                if (filter === "satilan") ok = teslim;
                if (filter === "borclu") ok = borc;
                if (q && ad.indexOf(q) === -1 && sinif.indexOf(q) === -1) ok = false;
                if (etut && et !== etut) ok = false;
                tr.hidden = !ok;
            });
        }

        function hydrate(payload) {
            if (!payload || !tbody) return;
            applyOzet(root, payload.ozet);
            var existing = {};
            tbody.querySelectorAll("tr[data-id]").forEach(function (tr) {
                existing[tr.getAttribute("data-id")] = tr;
            });
            var empty = tbody.querySelector("[data-empty]");
            (payload.siparisler || []).forEach(function (s) {
                var tr = existing[s.id];
                if (!tr) {
                    tr = document.createElement("tr");
                    tbody.appendChild(tr);
                }
                if (!busy.has(String(s.id))) {
                    paintRow(tr, s, canSatis);
                }
                delete existing[s.id];
            });
            Object.keys(existing).forEach(function (id) {
                if (!busy.has(id)) existing[id].remove();
            });
            if (empty) empty.remove();
            if (!(payload.siparisler || []).length && !tbody.querySelector("tr[data-id]")) {
                tbody.innerHTML = '<tr data-empty><td colspan="6">Henüz sipariş yok.</td></tr>';
            }
            applyFilters();
        }

        function refresh() {
            var sep = pollUrl.indexOf("?") >= 0 ? "&" : "?";
            return fetch(pollUrl + sep + "tarih=" + encodeURIComponent(tarih), {
                headers: { "X-Requested-With": "XMLHttpRequest" },
            })
                .then(function (res) { return res.json(); })
                .then(hydrate)
                .catch(function () {});
        }

        root.addEventListener("click", function (ev) {
            var chip = ev.target.closest("[data-filter]");
            if (chip) {
                filter = chip.getAttribute("data-filter");
                root.querySelectorAll("[data-filter]").forEach(function (c) {
                    c.classList.toggle("is-on", c === chip);
                });
                applyFilters();
                return;
            }

            var pay = ev.target.closest("[data-pay], .sb-borc-cell");
            var tick = ev.target.closest("[data-tick]");
            var row = ev.target.closest("tr[data-id]");
            if (!row || !canSatis) return;
            var id = row.getAttribute("data-id");
            if (busy.has(id)) return;

            if (pay) {
                ev.preventDefault();
                var btn = row.querySelector("[data-pay]");
                if (!btn || btn.disabled) return;
                if (!odemeUrl || odemeUrl === "pesin" || odemeUrl === "borc") {
                    window.alert("Ödeme adresi bulunamadı. Sayfayı yenileyin.");
                    return;
                }
                busy.add(id);
                var nextPay = row.getAttribute("data-odeme") === "borc" ? "pesin" : "borc";
                row.setAttribute("data-odeme", nextPay);
                btn.classList.toggle("is-on", nextPay === "borc");
                btn.setAttribute("aria-pressed", nextPay === "borc" ? "true" : "false");
                postJson(odemeUrl, { siparis_id: Number(id), odeme_turu: nextPay })
                    .then(function (data) {
                        applyOzet(root, data.ozet);
                        if (data.siparis) paintRow(row, data.siparis, canSatis);
                    })
                    .catch(function (err) {
                        window.alert(err.message);
                        refresh();
                    })
                    .finally(function () {
                        busy.delete(id);
                        applyFilters();
                    });
                return;
            }

            if (tick) {
                var teslim = row.getAttribute("data-teslim") === "1";
                if (teslim && !window.confirm("Teslim / satışı geri alalım mı?")) return;
                busy.add(id);
                tick.classList.add("is-busy");
                postJson(teslimUrl, { siparis_id: Number(id), undo: teslim ? "1" : "0" })
                    .then(function (data) {
                        applyOzet(root, data.ozet);
                        if (data.siparis) paintRow(row, data.siparis, canSatis);
                    })
                    .catch(function (err) {
                        window.alert(err.message);
                    })
                    .finally(function () {
                        busy.delete(id);
                        applyFilters();
                    });
            }
        });

        var search = root.querySelector("[data-sb-search]");
        if (search) {
            search.addEventListener("input", function () {
                q = (search.value || "").trim().toLowerCase();
                applyFilters();
            });
        }
        var etutSel = root.querySelector("[data-sb-etut]");
        if (etutSel) {
            etutSel.addEventListener("change", function () {
                etut = etutSel.value || "";
                applyFilters();
            });
        }

        window.setInterval(refresh, 6000);
    }

    function initBorc(root) {
        var kapatUrl = root.getAttribute("data-kapat");
        root.addEventListener("click", function (ev) {
            var btn = ev.target.closest("[data-kapat]");
            if (!btn) return;
            var row = btn.closest("tr[data-id]");
            if (!row) return;
            if (!window.confirm("Bu borcu tahsil edildi olarak kapatalım mı?")) return;
            btn.disabled = true;
            postJson(kapatUrl, { siparis_id: Number(row.getAttribute("data-id")) })
                .then(function () {
                    row.remove();
                })
                .catch(function (err) {
                    window.alert(err.message);
                    btn.disabled = false;
                });
        });
    }

    document.querySelectorAll("[data-sb-date]").forEach(function (input) {
        input.addEventListener("change", function () {
            var url = new URL(window.location.href);
            url.searchParams.set("tarih", input.value);
            window.location.href = url.toString();
        });
    });

    var siparis = document.querySelector("[data-sb-siparis]");
    if (siparis) initSiparis(siparis);
    var satis = document.querySelector("[data-sb-satis]");
    if (satis) initSatis(satis);
    var borc = document.querySelector("[data-sb-borc]");
    if (borc) initBorc(borc);
})();
