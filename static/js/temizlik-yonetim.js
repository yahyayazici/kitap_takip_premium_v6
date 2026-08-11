(function () {
    const panel = document.querySelector("[data-tz-panel]");
    if (!panel) return;

    const listeId = panel.dataset.listeId;
    const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const baseUrl = window.location.pathname;
    const SCROLL_KEY = `tz-panel-scroll:${listeId || ""}`;

    function saveScroll() {
        try {
            sessionStorage.setItem(
                SCROLL_KEY,
                String(window.scrollY || window.pageYOffset || 0)
            );
        } catch (e) {}
    }

    function restoreScroll() {
        /* Önce kaydedilen piksel — #kat- hash'i katın tepesine atıyordu */
        try {
            const y = parseInt(sessionStorage.getItem(SCROLL_KEY) || "", 10);
            if (!isNaN(y) && y > 0) {
                window.scrollTo(0, y);
                return true;
            }
        } catch (e) {}

        const hash = (location.hash || "").replace(/^#/, "");
        if (hash) {
            const el = document.getElementById(hash);
            if (el) {
                el.scrollIntoView({ block: "center", behavior: "instant" });
                return true;
            }
        }
        return false;
    }

    panel.querySelectorAll("form[method='post']").forEach((form) => {
        form.addEventListener("submit", saveScroll);
    });

    function applyRestore() {
        requestAnimationFrame(() => {
            const usedScroll = restoreScroll();
            requestAnimationFrame(() => {
                restoreScroll();
                try {
                    sessionStorage.removeItem(SCROLL_KEY);
                } catch (e) {}
                if (usedScroll && location.hash) {
                    history.replaceState(
                        null,
                        "",
                        location.pathname + location.search
                    );
                }
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", applyRestore);
    } else {
        applyRestore();
    }

    function openModal(name) {
        document.querySelectorAll("[data-tz-modal]").forEach((m) => {
            m.hidden = m.dataset.tzModal !== name;
        });
    }

    function closeModals() {
        document.querySelectorAll("[data-tz-modal]").forEach((m) => {
            m.hidden = true;
        });
    }

    document.querySelectorAll("[data-tz-open]").forEach((btn) => {
        btn.addEventListener("click", () => openModal(btn.dataset.tzOpen));
    });
    document.querySelectorAll("[data-tz-close]").forEach((btn) => {
        btn.addEventListener("click", closeModals);
    });

    document.querySelectorAll("[data-tz-mahal-ekle]").forEach((btn) => {
        btn.addEventListener("click", () => {
            saveScroll();
            document.getElementById("tz-mahal-kat-id").value = btn.dataset.tzMahalEkle;
            openModal("mahal-ekle");
        });
    });

    const alanInput = document.getElementById("tz-alan-id");
    const searchInput = document.getElementById("tz-talebe-ara");
    const results = document.getElementById("tz-talebe-sonuc");

    document.querySelectorAll("[data-tz-gorevli-ekle]").forEach((btn) => {
        btn.addEventListener("click", () => {
            alanInput.value = btn.dataset.tzGorevliEkle;
            searchInput.value = "";
            results.innerHTML = "";
            openModal("gorevli-ekle");
            searchInput.focus();
        });
    });

    let searchTimer;
    if (searchInput) {
        searchInput.addEventListener("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                const q = searchInput.value.trim();
                if (q.length < 1) {
                    results.innerHTML = "";
                    return;
                }
                const res = await fetch(`${baseUrl}?ajax=talebe_ara&q=${encodeURIComponent(q)}`);
                const data = await res.json();
                results.innerHTML = "";
                data.talebeler.forEach((t) => {
                    const li = document.createElement("li");
                    li.innerHTML = `<button type="button" data-talebe-id="${t.id}"><strong>${t.ad_soyad}</strong>${t.sinif ? `<span>${t.sinif}</span>` : ""}</button>`;
                    li.querySelector("button").addEventListener("click", () => {
                        const form = document.createElement("form");
                        form.method = "post";
                        form.innerHTML = `
                            <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
                            <input type="hidden" name="action" value="gorevli_ekle">
                            <input type="hidden" name="alan_id" value="${alanInput.value}">
                            <input type="hidden" name="talebe_id" value="${t.id}">
                        `;
                        document.body.appendChild(form);
                        form.submit();
                    });
                    results.appendChild(li);
                });
            }, 250);
        });
    }

    let dragged = null;

    document.querySelectorAll(".tz-talebe-chip[draggable='true']").forEach((chip) => {
        chip.addEventListener("dragstart", (e) => {
            dragged = {
                gorevliId: chip.dataset.gorevliId,
                talebeId: chip.dataset.talebeId,
            };
            chip.classList.add("is-dragging");
            e.dataTransfer.effectAllowed = "move";
        });
        chip.addEventListener("dragend", () => {
            chip.classList.remove("is-dragging");
            dragged = null;
        });
    });

    document.querySelectorAll(".tz-bulk-chip[draggable='true']").forEach((chip) => {
        chip.addEventListener("dragstart", (e) => {
            dragged = { talebeId: chip.dataset.talebeId };
            e.dataTransfer.effectAllowed = "copy";
        });
        chip.addEventListener("dragend", () => {
            dragged = null;
        });
    });

    function postMove(gorevliId, hedefAlanId) {
        const form = document.createElement("form");
        form.method = "post";
        form.innerHTML = `
            <input type="hidden" name="csrfmiddlewaretoken" value="${csrf}">
            <input type="hidden" name="action" value="${gorevliId ? "gorevli_tasi" : "gorevli_ekle"}">
            ${gorevliId ? `<input type="hidden" name="gorevli_id" value="${gorevliId}">` : ""}
            ${!gorevliId && dragged?.talebeId ? `<input type="hidden" name="talebe_id" value="${dragged.talebeId}">` : ""}
            <input type="hidden" name="hedef_alan_id" value="${hedefAlanId}">
            <input type="hidden" name="alan_id" value="${hedefAlanId}">
        `;
        document.body.appendChild(form);
        form.submit();
    }

    async function ajaxGorevliEkle(alanId, talebeId) {
        const body = new FormData();
        body.append("csrfmiddlewaretoken", csrf);
        body.append("action", "gorevli_ekle");
        body.append("alan_id", alanId);
        body.append("talebe_id", talebeId);
        const res = await fetch(baseUrl, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body,
        });
        if (!res.ok) return null;
        return res.json();
    }

    async function ajaxGorevliSil(gorevliId) {
        const body = new FormData();
        body.append("csrfmiddlewaretoken", csrf);
        body.append("action", "gorevli_sil");
        body.append("gorevli_id", gorevliId);
        const res = await fetch(baseUrl, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body,
        });
        if (!res.ok) return null;
        return res.json();
    }

    function bindBulkAssignedChip(span) {
        span.addEventListener("dragstart", (e) => {
            dragged = {
                gorevliId: span.dataset.gorevliId,
                talebeId: span.dataset.talebeId,
                bulkUndo: true,
            };
            span.classList.add("is-dragging");
            e.dataTransfer.effectAllowed = "move";
        });
        span.addEventListener("dragend", () => {
            span.classList.remove("is-dragging");
            dragged = null;
        });
        const btn = span.querySelector("[data-tz-bulk-geri]");
        if (btn) {
            btn.addEventListener("click", async (e) => {
                e.preventDefault();
                e.stopPropagation();
                await bulkGeriAl(span);
            });
        }
    }

    async function bulkGeriAl(span) {
        const gorevliId = span.dataset.gorevliId;
        const talebeId = span.dataset.talebeId;
        if (!gorevliId) return;
        const data = await ajaxGorevliSil(gorevliId);
        if (!data || !data.ok) return;
        span.remove();
        const source = document.querySelector(
            `.tz-bulk-chip[data-talebe-id="${talebeId || data.talebe_id}"]`
        );
        if (source) source.classList.remove("is-assigned");
    }

    function bulkChipEkle(zone, adSoyad, gorevliId, talebeId) {
        let row = zone.querySelector(".tz-chip-row");
        if (!row) {
            row = document.createElement("div");
            row.className = "tz-chip-row";
            zone.appendChild(row);
        }
        const span = document.createElement("span");
        span.className = "tz-talebe-chip tz-bulk-assigned";
        span.draggable = true;
        span.dataset.gorevliId = String(gorevliId || "");
        span.dataset.talebeId = String(talebeId || "");
        const ad = (adSoyad || "").trim();
        const kisa = ad.length > 14 ? ad.slice(0, 13) + "…" : ad;
        span.appendChild(document.createTextNode(kisa + " "));
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "tz-bulk-geri";
        btn.dataset.tzBulkGeri = "1";
        btn.title = "Geri al";
        btn.textContent = "×";
        span.appendChild(btn);
        row.appendChild(span);
        bindBulkAssignedChip(span);
    }

    document.querySelectorAll(".tz-bulk-assigned").forEach(bindBulkAssignedChip);

    /* Atanmış chip'e karşılık sol listedeki talebeyi soluk göster */
    document.querySelectorAll(".tz-bulk-assigned[data-talebe-id]").forEach((chip) => {
        const source = document.querySelector(
            `.tz-bulk-chip[data-talebe-id="${chip.dataset.talebeId}"]`
        );
        if (source) source.classList.add("is-assigned");
    });

    const geriDrop = document.querySelector("[data-tz-bulk-geri-drop]");
    if (geriDrop) {
        geriDrop.addEventListener("dragover", (e) => {
            if (!dragged?.bulkUndo || !dragged.gorevliId) return;
            e.preventDefault();
            geriDrop.classList.add("drag-over");
        });
        geriDrop.addEventListener("dragleave", () =>
            geriDrop.classList.remove("drag-over")
        );
        geriDrop.addEventListener("drop", async (e) => {
            e.preventDefault();
            geriDrop.classList.remove("drag-over");
            if (!dragged?.bulkUndo || !dragged.gorevliId) return;
            const span = document.querySelector(
                `.tz-bulk-assigned[data-gorevli-id="${dragged.gorevliId}"]`
            );
            if (span) await bulkGeriAl(span);
        });
    }

    document.querySelectorAll("[data-drop='1']").forEach((zone) => {
        zone.addEventListener("dragover", (e) => {
            if (!dragged) return;
            e.preventDefault();
            zone.classList.add("drag-over");
        });
        zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
        zone.addEventListener("drop", async (e) => {
            e.preventDefault();
            zone.classList.remove("drag-over");
            if (!dragged) return;
            const hedefId = zone.dataset.mahalId;
            if (!hedefId) return;

            /* Toplu dağıtım: AJAX — modal kapanmasın, sıra sıra atansın */
            if (
                dragged.talebeId &&
                !dragged.gorevliId &&
                zone.classList.contains("tz-bulk-drop")
            ) {
                const talebeId = dragged.talebeId;
                const source = document.querySelector(
                    `.tz-bulk-chip[data-talebe-id="${talebeId}"]`
                );
                const data = await ajaxGorevliEkle(hedefId, talebeId);
                if (!data || !data.ok) return;
                const ad =
                    data.ad_soyad ||
                    (source ? source.textContent.trim() : "");
                bulkChipEkle(zone, ad, data.gorevli_id, data.talebe_id || talebeId);
                if (source) source.classList.add("is-assigned");
                return;
            }

            /* Toplu modda mahaller arası taşıma */
            if (
                dragged.bulkUndo &&
                dragged.gorevliId &&
                zone.classList.contains("tz-bulk-drop")
            ) {
                postMove(dragged.gorevliId, hedefId);
                return;
            }

            if (dragged.gorevliId) {
                postMove(dragged.gorevliId, hedefId);
            } else if (dragged.talebeId) {
                postMove(null, hedefId);
            }
        });
    });
})();
