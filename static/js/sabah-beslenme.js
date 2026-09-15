(function () {
    "use strict";

    function csrfToken() {
        var el = document.querySelector("[name=csrfmiddlewaretoken]");
        return el ? el.value : "";
    }

    function postJson(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(body || {}),
        }).then(function (res) {
            return res.json().then(function (data) {
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

    function initSiparis(root) {
        var api = root.getAttribute("data-api");
        var tarih = root.getAttribute("data-tarih");
        var busy = new Set();
        var timers = {};
        var pending = {};

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
                })
                .catch(function (err) {
                    window.alert(err.message);
                })
                .finally(function () {
                    busy.delete(talebeId);
                    row.classList.remove("is-busy");
                    if (Object.prototype.hasOwnProperty.call(pending, talebeId)) {
                        var next = pending[talebeId];
                        delete pending[talebeId];
                        kaydet(row, next, input);
                    }
                });
        }

        function fromInput(input) {
            var row = input.closest("tr");
            if (!row) return;
            var adet = parseAdet(input.value);
            var prev = row.getAttribute("data-saved");
            if (adet === 0 && (prev === null || prev === "")) return;
            if (prev !== null && prev !== "" && String(adet) === prev) return;
            kaydet(row, adet, input);
        }

        root.addEventListener("change", function (ev) {
            var input = ev.target.closest(".sb-adet-input");
            if (!input) return;
            fromInput(input);
        });

        root.addEventListener("input", function (ev) {
            var input = ev.target.closest(".sb-adet-input");
            if (!input) return;
            var row = input.closest("tr");
            var key = row && row.getAttribute("data-talebe");
            if (!key) return;
            window.clearTimeout(timers[key]);
            timers[key] = window.setTimeout(function () {
                fromInput(input);
            }, 350);
        });

        root.addEventListener("blur", function (ev) {
            var input = ev.target.closest && ev.target.closest(".sb-adet-input");
            if (!input) return;
            var row = input.closest("tr");
            var key = row && row.getAttribute("data-talebe");
            if (key) window.clearTimeout(timers[key]);
            fromInput(input);
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
        tr.innerHTML =
            "<td><strong>" + s.talebe + "</strong>" + meta + "</td>" +
            "<td>" + s.etut + "<br><small>" + s.sinif + "</small></td>" +
            "<td>" + s.adet + "</td>" +
            '<td class="sb-tutar">' + s.tutar_etiket + "</td>" +
            "<td><div class=\"sb-pay\" role=\"group\" aria-label=\"Ödeme\">" +
            '<button type="button" class="sb-pay-btn' + (s.odeme_turu === "pesin" ? " is-on" : "") + '" data-pay="pesin"' + disabledPay + ">Peşin</button>" +
            '<button type="button" class="sb-pay-btn' + (s.odeme_turu === "borc" ? " is-on" : "") + '" data-pay="borc"' + disabledPay + ">Borç</button>" +
            "</div></td>" +
            '<td class="sb-tick-col"><button type="button" class="sb-tick' + (s.teslim_edildi ? " is-done" : "") + '" data-tick' + disabledTick + ' aria-pressed="' + (s.teslim_edildi ? "true" : "false") + '" aria-label="Teslim / satış"><span class="sb-tick-icon" aria-hidden="true"></span></button></td>';
    }

    function initSatis(root) {
        var pollUrl = root.getAttribute("data-poll");
        var teslimTpl = root.getAttribute("data-teslim-tpl");
        var odemeTpl = root.getAttribute("data-odeme-tpl");
        var tarih = root.getAttribute("data-tarih");
        var canSatis = root.getAttribute("data-satis") === "1";
        var tbody = root.querySelector("[data-sb-rows]");
        var busy = new Set();
        var filter = "tumu";
        var q = "";
        var etut = "";

        function urlFor(tpl, id) {
            return tpl.replace("/0/", "/" + id + "/");
        }

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
            var tick = ev.target.closest("[data-tick]");
            var pay = ev.target.closest("[data-pay]");
            var chip = ev.target.closest("[data-filter]");
            if (chip) {
                filter = chip.getAttribute("data-filter");
                root.querySelectorAll("[data-filter]").forEach(function (c) {
                    c.classList.toggle("is-on", c === chip);
                });
                applyFilters();
                return;
            }
            var row = ev.target.closest("tr[data-id]");
            if (!row || !canSatis) return;
            var id = row.getAttribute("data-id");
            if (busy.has(id)) return;

            if (tick) {
                var teslim = row.getAttribute("data-teslim") === "1";
                if (teslim && !window.confirm("Teslim / satışı geri alalım mı?")) return;
                busy.add(id);
                tick.classList.add("is-busy");
                postJson(urlFor(teslimTpl, id), { undo: teslim ? "1" : "0" })
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
                return;
            }

            if (pay) {
                busy.add(id);
                postJson(urlFor(odemeTpl, id), { odeme_turu: pay.getAttribute("data-pay") })
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
        var tpl = root.getAttribute("data-kapat-tpl");
        root.addEventListener("click", function (ev) {
            var btn = ev.target.closest("[data-kapat]");
            if (!btn) return;
            var row = btn.closest("tr[data-id]");
            if (!row) return;
            if (!window.confirm("Bu borcu tahsil edildi olarak kapatalım mı?")) return;
            btn.disabled = true;
            postJson(tpl.replace("/0/", "/" + row.getAttribute("data-id") + "/"), {})
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
