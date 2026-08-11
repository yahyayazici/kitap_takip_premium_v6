(function () {
    const panel = document.querySelector("[data-tz-panel]");
    if (!panel) return;

    const listeId = panel.dataset.listeId;
    const csrf = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";
    const baseUrl = window.location.pathname;

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

    function bulkChipEkle(zone, adSoyad) {
        let row = zone.querySelector(".tz-chip-row");
        if (!row) {
            row = document.createElement("div");
            row.className = "tz-chip-row";
            zone.appendChild(row);
        }
        const span = document.createElement("span");
        span.className = "tz-talebe-chip";
        const ad = (adSoyad || "").trim();
        span.textContent = ad.length > 14 ? ad.slice(0, 13) + "…" : ad;
        row.appendChild(span);
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
            if (dragged.talebeId && !dragged.gorevliId && zone.classList.contains("tz-bulk-drop")) {
                const talebeId = dragged.talebeId;
                const source = document.querySelector(
                    `.tz-bulk-chip[data-talebe-id="${talebeId}"]`
                );
                const data = await ajaxGorevliEkle(hedefId, talebeId);
                if (!data || !data.ok) return;
                const ad =
                    data.ad_soyad ||
                    (source ? source.textContent.replace(/^👤\s*/, "") : "");
                bulkChipEkle(zone, ad);
                if (source) source.classList.add("is-assigned");
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
