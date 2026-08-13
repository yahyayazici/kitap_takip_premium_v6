(function () {
    "use strict";

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }
    function qsa(sel, root) {
        return Array.prototype.slice.call((root || document).querySelectorAll(sel));
    }

    function csrfToken(root) {
        return root.getAttribute("data-csrf");
    }

    function postForm(url, data, root) {
        var body = new URLSearchParams();
        Object.keys(data).forEach(function (k) {
            if (data[k] !== undefined && data[k] !== null) body.append(k, data[k]);
        });
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrfToken(root),
            },
            body: body.toString(),
            credentials: "same-origin",
        }).then(function (r) {
            return r.json();
        });
    }

    function updateOzet(root, ozet) {
        if (!ozet) return;
        var map = {
            "data-ozet-talebe": ozet.talebe_sayisi,
            "data-ozet-atanan": ozet.atanan,
            "data-ozet-atanmamis": ozet.atanmamis,
            "data-ozet-arac": ozet.arac_sayisi,
            "data-ozet-kapasite": ozet.toplam_kapasite,
        };
        Object.keys(map).forEach(function (attr) {
            var el = root.querySelector("[" + attr + "]");
            if (el) el.textContent = map[attr];
        });
        var olustu = qs("[data-za-kapasite-olustu]", root);
        if (olustu && ozet.kapasite_olustu_mesaj) {
            olustu.textContent = ozet.kapasite_olustu_mesaj;
            olustu.classList.toggle("is-muted", !ozet.arac_sayisi);
        }
        var mesaj = qs("[data-za-kapasite-mesaj]", root);
        if (mesaj && ozet.kapasite_mesaj) {
            mesaj.textContent = ozet.kapasite_mesaj;
            mesaj.classList.remove("is-warn", "is-ok", "is-muted");
            if (!ozet.kapasite_yeterli) {
                mesaj.classList.add("is-warn");
            } else if (ozet.atanmamis === 0) {
                mesaj.classList.add("is-ok");
            } else {
                mesaj.classList.add("is-muted");
            }
        }
    }

    function renderAtanmamis(root, list) {
        var box = qs("[data-za-atanmamis]", root);
        if (!box) return;
        if (!list || !list.length) {
            box.innerHTML = '<p class="za-empty">Tüm talebeler atandı veya liste boş.</p>';
            return;
        }
        box.innerHTML = list
            .map(function (t) {
                return (
                    '<div class="za-chip za-chip--talebe" draggable="true" data-tur="talebe" data-id="' +
                    t.id +
                    '"><strong>' +
                    escapeHtml(t.ad) +
                    '</strong><span>' +
                    escapeHtml(t.sinif) +
                    '</span><button type="button" class="za-chip-assign" data-za-mobil-ata>Araca Ata</button></div>'
                );
            })
            .join("");
        bindDraggables(root);
        bindMobilAta(root);
    }

    function renderAracGrid(root, kartlar) {
        var grid = qs("[data-za-arac-grid]", root);
        if (!grid || !kartlar) return;
        var planId = root.getAttribute("data-plan-id");
        var silYetki = root.getAttribute("data-arac-sil-yetki") === "1";
        grid.innerHTML = kartlar
            .map(function (k) {
                var etutHtml = (k.etut_hocalari || [])
                    .map(function (h) {
                        return (
                            '<div class="za-rozet za-rozet--etut" draggable="true" data-tur="etut_hocasi" data-id="' +
                            h.id +
                            '"><div class="za-rozet-main"><strong>' +
                            escapeHtml(h.ad) +
                            '</strong><span>Etüt Mesulü</span></div><button type="button" class="za-tool-btn za-tool-btn--remove" data-za-cikar data-tur="etut_hocasi" data-id="' +
                            h.id +
                            '" title="Çıkar" aria-label="Çıkar">×</button></div>'
                        );
                    })
                    .join("");
                var talebeHtml = (k.talebeler || [])
                    .map(function (t) {
                        return (
                            '<div class="za-chip za-chip--talebe za-chip--in-arac" draggable="true" data-tur="talebe" data-id="' +
                            t.id +
                            '"><div class="za-chip-main"><strong>' +
                            escapeHtml(t.ad) +
                            '</strong></div><div class="za-chip-tools"><button type="button" class="za-tool-btn za-tool-btn--pin" data-za-sabitle data-id="' +
                            t.id +
                            '" title="Sabitle" aria-label="Sabitle">Sabitle</button><button type="button" class="za-tool-btn za-tool-btn--remove" data-za-cikar data-tur="talebe" data-id="' +
                            t.id +
                            '" title="Çıkar" aria-label="Çıkar">×</button></div></div>'
                        );
                    })
                    .join("");
                return (
                    '<article class="za-arac-kart' +
                    (k.dolu_mu ? " is-full" : "") +
                    '" data-arac-id="' +
                    k.id +
                    '" data-droppable="1"><header class="za-arac-kart-head"><div><h3>' +
                    escapeHtml(k.surucu_ad.toUpperCase()) +
                    '</h3><p class="za-arac-kapasite"><span data-dolu>' +
                    k.dolu +
                    "</span> / <span data-toplam>" +
                    k.kapasite +
                    "</span> Talebe" +
                    (k.dolu_mu ? '<em class="za-full-badge">DOLU</em>' : "") +
                    '</p><p class="za-arac-meta">Aracı bulan: ' +
                    escapeHtml(k.ekleyen) +
                    '</p></div><div class="za-arac-kart-actions">' +
                    '<a href="/ziyaret-arac/' +
                    planId +
                    "/pdf/arac/" +
                    k.id +
                    '/" class="za-kart-action-btn" target="_blank" rel="noopener">PDF</a>' +
                    '<button type="button" class="za-kart-action-btn" data-za-arac-duzenle data-id="' +
                    k.id +
                    '" data-ad="' +
                    escapeHtml(k.surucu_ad) +
                    '" data-kapasite="' +
                    k.kapasite +
                    '" title="Düzenle" aria-label="Düzenle">Düzenle</button>' +
                    (silYetki
                        ? '<button type="button" class="za-kart-action-btn za-kart-action-btn--danger" data-za-arac-sil data-id="' +
                          k.id +
                          '" data-ad="' +
                          escapeHtml(k.surucu_ad) +
                          '" title="Aracı sil" aria-label="Aracı sil">Sil</button>'
                        : "") +
                    "</div></header><div class=\"za-arac-body\" data-arac-body>" +
                    etutHtml +
                    talebeHtml +
                    "</div></article>"
                );
            })
            .join("");
        bindDraggables(root);
        bindDropZones(root);
        bindCikar(root);
        bindSabitle(root);
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function applyResponse(root, data) {
        if (!data.ok) {
            alert(data.mesaj || "İşlem başarısız.");
            return;
        }
        updateOzet(root, data.ozet);
        if (data.arac_kartlari) renderAracGrid(root, data.arac_kartlari);
        if (data.atanmamis) renderAtanmamis(root, data.atanmamis);
        if (data.mesaj && data.mesaj.indexOf("dağıt") !== -1) {
            /* sessiz */
        }
    }

    function ata(root, tur, id, aracId, override) {
        var payload = { tur: tur, arac_id: aracId };
        if (tur === "talebe") payload.talebe_id = id;
        if (tur === "etut_hocasi") payload.etut_hocasi_id = id;
        if (override) payload.override = "1";
        return postForm(root.getAttribute("data-api-ata"), payload, root).then(function (data) {
            if (!data.ok && tur === "talebe") {
                if (confirm((data.mesaj || "Kapasite dolu") + " Yine de ata?")) {
                    payload.override = "1";
                    return postForm(root.getAttribute("data-api-ata"), payload, root);
                }
            }
            return data;
        });
    }

    function cikar(root, tur, id) {
        var payload = { tur: tur };
        if (tur === "talebe") payload.talebe_id = id;
        if (tur === "etut_hocasi") payload.etut_hocasi_id = id;
        return postForm(root.getAttribute("data-api-cikar"), payload, root);
    }

    var dragPayload = null;

    function bindDraggables(root) {
        qsa("[draggable=true]", root).forEach(function (el) {
            el.addEventListener("dragstart", function (e) {
                dragPayload = {
                    tur: el.getAttribute("data-tur"),
                    id: el.getAttribute("data-id"),
                };
                e.dataTransfer.effectAllowed = "move";
            });
            el.addEventListener("dragend", function () {
                dragPayload = null;
            });
        });
    }

    function bindDropZones(root) {
        qsa("[data-droppable]", root).forEach(function (zone) {
            zone.addEventListener("dragover", function (e) {
                e.preventDefault();
                zone.classList.add("is-drop-target");
            });
            zone.addEventListener("dragleave", function () {
                zone.classList.remove("is-drop-target");
            });
            zone.addEventListener("drop", function (e) {
                e.preventDefault();
                zone.classList.remove("is-drop-target");
                if (!dragPayload) return;
                var aracId = zone.getAttribute("data-arac-id");
                ata(root, dragPayload.tur, dragPayload.id, aracId, false).then(function (data) {
                    applyResponse(root, data);
                });
            });
        });
    }

    function bindCikar(root) {
        root.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-za-cikar]");
            if (!btn) return;
            e.preventDefault();
            cikar(root, btn.getAttribute("data-tur"), btn.getAttribute("data-id")).then(function (data) {
                applyResponse(root, data);
            });
        });
    }

    function bindSabitle(root) {
        root.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-za-sabitle]");
            if (!btn) return;
            e.preventDefault();
            var talebeId = btn.getAttribute("data-id");
            var kart = btn.closest("[data-arac-id]");
            var aracId = kart ? kart.getAttribute("data-arac-id") : "";
            postForm(root.getAttribute("data-api-sabitle"), {
                talebe_id: talebeId,
                sabit: "1",
                arac_id: aracId,
            }, root).then(function (data) {
                if (data.ok) btn.textContent = "✓";
            });
        });
    }

    function bindMobilAta(root) {
        var modal = document.getElementById("za-mobil-modal");
        var select = document.getElementById("za-mobil-arac-select");
        var onay = document.getElementById("za-mobil-onayla");
        var pendingId = null;

        root.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-za-mobil-ata]");
            if (!btn) return;
            var chip = btn.closest("[data-id]");
            pendingId = chip.getAttribute("data-id");
            if (!select) return;
            select.innerHTML = "";
            qsa("[data-arac-id]", root).forEach(function (kart) {
                var opt = document.createElement("option");
                opt.value = kart.getAttribute("data-arac-id");
                opt.textContent = qs("h3", kart).textContent;
                select.appendChild(opt);
            });
            if (modal) modal.hidden = false;
        });

        qsa("[data-za-modal-kapat]").forEach(function (el) {
            el.addEventListener("click", function () {
                if (modal) modal.hidden = true;
            });
        });

        if (onay) {
            onay.addEventListener("click", function () {
                if (!pendingId || !select) return;
                ata(root, "talebe", pendingId, select.value, false).then(function (data) {
                    applyResponse(root, data);
                    if (modal) modal.hidden = true;
                });
            });
        }
    }

    function bindAracDuzenle(root) {
        root.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-za-arac-duzenle]");
            if (!btn) return;
            e.preventDefault();
            var aracId = btn.getAttribute("data-id");
            var ad = btn.getAttribute("data-ad") || "";
            var kap = btn.getAttribute("data-kapasite") || "4";
            var yeniAd = prompt("Araç sahibi / sürücü adı:", ad);
            if (yeniAd === null) return;
            yeniAd = yeniAd.trim();
            if (!yeniAd) return;
            var yeniKap = prompt("Talebe kapasitesi:", kap);
            if (yeniKap === null) return;
            if (!yeniKap || parseInt(yeniKap, 10) < 1) {
                alert("Geçerli bir kapasite girin.");
                return;
            }
            postForm(
                "/ziyaret-arac/" + root.getAttribute("data-plan-id") + "/api/arac/",
                {
                    arac_id: aracId,
                    surucu_ad: yeniAd,
                    kapasite: yeniKap,
                },
                root
            ).then(function (data) {
                applyResponse(root, data);
            });
        });
    }

    function bindAracSil(root) {
        root.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-za-arac-sil]");
            if (!btn) return;
            e.preventDefault();
            var aracId = btn.getAttribute("data-id");
            var ad = btn.getAttribute("data-ad") || "Bu araç";
            if (!confirm(ad + " aracını silmek istiyor musunuz?\nAraçtaki talebeler atanmamış listesine döner.")) {
                return;
            }
            postForm(
                "/ziyaret-arac/" +
                    root.getAttribute("data-plan-id") +
                    "/api/arac/" +
                    aracId +
                    "/sil/",
                {},
                root
            ).then(function (data) {
                applyResponse(root, data);
            });
        });
    }

    function init() {
        var root = qs("[data-za-planlama]");
        if (!root) return;

        bindDraggables(root);
        bindDropZones(root);
        bindCikar(root);
        bindSabitle(root);
        bindMobilAta(root);
        bindAracDuzenle(root);
        bindAracSil(root);

        var otomatik = qs("[data-za-otomatik]", root);
        if (otomatik) {
            otomatik.addEventListener("click", function () {
                postForm(root.getAttribute("data-api-otomatik"), {}, root).then(function (data) {
                    applyResponse(root, data);
                });
            });
        }

        var yeniden = qs("[data-za-yeniden-dagit]", root);
        if (yeniden) {
            yeniden.addEventListener("click", function () {
                if (!confirm("Sabitlemediğiniz talebeler yeniden dağıtılacak. Devam?")) return;
                postForm(root.getAttribute("data-api-otomatik"), { yeniden: "1" }, root).then(function (data) {
                    applyResponse(root, data);
                });
            });
        }

        var geriAl = qs("[data-za-geri-al]", root);
        if (geriAl) {
            geriAl.addEventListener("click", function () {
                postForm(root.getAttribute("data-api-geri-al"), {}, root).then(function (data) {
                    applyResponse(root, data);
                });
            });
        }

        var aracEkle = qs("[data-za-arac-ekle]", root);
        if (aracEkle) {
            aracEkle.addEventListener("click", function () {
                var ad = prompt("Araç sahibi / sürücü adı:");
                if (!ad) return;
                var kap = prompt("Talebe kapasitesi:", "4");
                if (!kap) return;
                postForm("/ziyaret-arac/" + root.getAttribute("data-plan-id") + "/api/arac/", {
                    surucu_ad: ad,
                    kapasite: kap,
                }, root).then(function (data) {
                    applyResponse(root, data);
                });
            });
        }

        var arama = qs("[data-za-talebe-ara]", root);
        var aramaSonuc = qs("[data-za-arama-sonuc]", root);
        if (arama && aramaSonuc) {
            var timer;
            arama.addEventListener("input", function () {
                clearTimeout(timer);
                timer = setTimeout(function () {
                    var url = arama.getAttribute("data-url") + "?q=" + encodeURIComponent(arama.value);
                    fetch(url, { credentials: "same-origin" })
                        .then(function (r) { return r.json(); })
                        .then(function (data) {
                            if (!data.ok || !data.talebeler) {
                                aramaSonuc.innerHTML = "";
                                return;
                            }
                            aramaSonuc.innerHTML = data.talebeler
                                .map(function (t) {
                                    if (t.listed) {
                                        return (
                                            '<div class="za-arama-item">' +
                                            escapeHtml(t.ad) +
                                            " <em>(listed)</em></div>"
                                        );
                                    }
                                    return (
                                        '<div class="za-arama-item"><span>' +
                                        escapeHtml(t.ad) +
                                        " · " +
                                        escapeHtml(t.sinif) +
                                        '</span><button type="button" class="za-link-sm" data-za-tek-ekle data-id="' +
                                        t.id +
                                        '">Ekle</button></div>'
                                    );
                                })
                                .join("");
                        });
                }, 280);
            });
            aramaSonuc.addEventListener("click", function (e) {
                var btn = e.target.closest("[data-za-tek-ekle]");
                if (!btn) return;
                var form = document.createElement("form");
                form.method = "POST";
                form.action =
                    "/ziyaret-arac/" + root.getAttribute("data-plan-id") + "/talebe-ekle/";
                var csrf = document.createElement("input");
                csrf.type = "hidden";
                csrf.name = "csrfmiddlewaretoken";
                csrf.value = csrfToken(root);
                form.appendChild(csrf);
                var inp = document.createElement("input");
                inp.type = "hidden";
                inp.name = "talebe_ids";
                inp.value = btn.getAttribute("data-id");
                form.appendChild(inp);
                document.body.appendChild(form);
                form.submit();
            });
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
