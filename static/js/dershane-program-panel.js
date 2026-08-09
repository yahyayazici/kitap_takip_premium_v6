(function () {
    const panel = document.querySelector("[data-dp-panel]");
    if (!panel) return;

    const modals = document.querySelectorAll("[data-dp-modal]");
    const openButtons = document.querySelectorAll("[data-dp-open]");
    const closeButtons = document.querySelectorAll("[data-dp-close]");
    const matrix = document.querySelector("[data-dp-matrix]");
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

    function openModal(name) {
        modals.forEach((modal) => {
            modal.classList.toggle("open", modal.dataset.dpModal === name);
        });
    }

    function closeModals() {
        modals.forEach((modal) => modal.classList.remove("open"));
    }

    openButtons.forEach((button) => {
        button.addEventListener("click", () => openModal(button.dataset.dpOpen));
    });

    closeButtons.forEach((button) => {
        button.addEventListener("click", closeModals);
    });

    modals.forEach((modal) => {
        modal.addEventListener("click", (event) => {
            if (event.target === modal) closeModals();
        });
    });

    document.querySelectorAll("[data-dp-assign]").forEach((el) => {
        el.addEventListener("click", (event) => {
            if (el.classList.contains("dp-dragging-active")) return;
            const data = JSON.parse(el.dataset.dpAssign || "{}");
            document.getElementById("dp-atama-blok").value = data.blok || "";
            document.getElementById("dp-atama-grup").value = data.grup || "";
            const dersSelect = document.getElementById("dp-atama-ders");
            const ogretmenSelect = document.getElementById("dp-atama-ogretmen");
            if (dersSelect) {
                [...dersSelect.options].forEach((option) => {
                    option.selected = option.text === data.ders;
                });
            }
            if (ogretmenSelect) {
                [...ogretmenSelect.options].forEach((option) => {
                    option.selected = option.text === data.ogretmen;
                });
            }
            openModal("atama");
        });
    });

    document.querySelectorAll("[data-dp-edit-block]").forEach((button) => {
        button.addEventListener("click", () => {
            const data = JSON.parse(button.dataset.dpEditBlock || "{}");
            document.getElementById("dp-saat-blok-id").value = data.id || "";
            document.getElementById("dp-saat-bas").value = data.baslangic || "";
            document.getElementById("dp-saat-bit").value = data.bitis || "";
            document.getElementById("dp-saat-tur").value = data.tur || "ders";
            document.getElementById("dp-saat-aciklama").value = data.aciklama || "";
            openModal("saat");
        });
    });

    const blockList = document.querySelector("[data-dp-block-list]");
    if (blockList) {
        let draggedRow = null;
        blockList.querySelectorAll(".dp-block-row").forEach((row) => {
            row.addEventListener("dragstart", () => {
                draggedRow = row;
                row.classList.add("dragging");
            });
            row.addEventListener("dragend", () => {
                row.classList.remove("dragging");
                const ids = [...blockList.querySelectorAll(".dp-block-row")].map(
                    (item) => item.dataset.blokId
                );
                if (!ids.length) return;
                const form = document.createElement("form");
                form.method = "post";
                form.innerHTML = `
                    <input type="hidden" name="csrfmiddlewaretoken" value="${csrfToken}">
                    <input type="hidden" name="program" value="${panel.dataset.program}">
                    <input type="hidden" name="gun" value="${panel.dataset.gun}">
                    <input type="hidden" name="action" value="saat_sirala">
                    <input type="hidden" name="sira" value="${ids.join(",")}">
                `;
                document.body.appendChild(form);
                form.submit();
            });
            row.addEventListener("dragover", (event) => {
                event.preventDefault();
                const target = row;
                if (!draggedRow || draggedRow === target) return;
                const rect = target.getBoundingClientRect();
                const horizontal = blockList.classList.contains("dp-block-strip")
                    || getComputedStyle(blockList).flexDirection.startsWith("row")
                    || blockList.style.display === "flex";
                const after = horizontal
                    ? event.clientX > rect.left + rect.width / 2
                    : event.clientY > rect.top + rect.height / 2;
                blockList.insertBefore(
                    draggedRow,
                    after ? target.nextSibling : target
                );
            });
        });
    }

    /* ——— Ders sürükle-bırak ——— */
    let draggedDers = null;

    function findAssignmentCell(blokId, grupId) {
        return document.querySelector(
            `[data-blok-id="${blokId}"][data-grup-id="${grupId}"]`
        );
    }

    function updateCell(cell, result) {
        if (!cell || !result.ok) return;
        const assignData = {
            blok: result.blok_id,
            grup: result.grup_id,
            ders: result.ders,
            ogretmen: result.ogretmen || "",
        };
        cell.dataset.dpAssign = JSON.stringify(assignData);

        if (cell.classList.contains("dp-mob-group")) {
            cell.classList.remove("is-empty");
            cell.style.setProperty("--cell-bg", result.renk || "#f8fafc");
            const grupLabel = cell.querySelector(".dp-mob-grup-label")?.textContent || "";
            cell.innerHTML =
                `<span class="dp-mob-grup-label">${grupLabel}</span>` +
                `<strong class="dp-mob-ders">${result.ders}</strong>` +
                `<span class="dp-mob-ogretmen">${result.ogretmen || "—"}</span>`;
            return;
        }

        cell.classList.remove("dp-cell-empty");
        cell.style.background = result.renk || "#f8fafc";
        cell.innerHTML =
            `<strong class="dp-cell-ders">${result.ders}</strong>` +
            `<span class="dp-cell-ogretmen">${result.ogretmen || "—"}</span>`;
    }

    async function surukleAtama(target, payload) {
        if (!matrix || !draggedDers) return;
        const url = matrix.dataset.atamaUrl;
        if (!url) return;

        target.classList.add("dp-drop-loading");
        try {
            const response = await fetch(url, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken,
                },
                body: JSON.stringify({
                    saat_bloku_id: payload.saat_bloku_id,
                    ders_id: draggedDers.id,
                    grup_ids: payload.grup_ids || [],
                    sinif_seviye: payload.sinif_seviye || "",
                    tum_gruplar: payload.tum_gruplar || false,
                }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || "Atama başarısız.");
            }
            (data.sonuclar || []).forEach((result) => {
                if (!result.ok) return;
                updateCell(findAssignmentCell(result.blok_id, result.grup_id), result);
            });
        } catch (error) {
            window.alert(error.message || "Atama kaydedilemedi.");
        } finally {
            target.classList.remove("dp-drop-loading");
        }
    }

    document.querySelectorAll(".dp-ders-chip").forEach((chip) => {
        chip.addEventListener("dragstart", (event) => {
            draggedDers = {
                id: parseInt(chip.dataset.dersId, 10),
                ad: chip.dataset.dersAd,
                renk: chip.dataset.dersRenk,
            };
            chip.classList.add("dragging");
            event.dataTransfer.effectAllowed = "copy";
            event.dataTransfer.setData("text/plain", chip.dataset.dersAd || "");
        });
        chip.addEventListener("dragend", () => {
            chip.classList.remove("dragging");
            draggedDers = null;
        });
    });

    document.querySelectorAll(".dp-droppable").forEach((zone) => {
        zone.addEventListener("dragover", (event) => {
            if (!draggedDers) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = "copy";
            zone.classList.add("dp-drop-over");
        });
        zone.addEventListener("dragleave", () => {
            zone.classList.remove("dp-drop-over");
        });
        zone.addEventListener("drop", (event) => {
            event.preventDefault();
            zone.classList.remove("dp-drop-over");
            if (!draggedDers) return;

            const blokId = parseInt(zone.dataset.blokId, 10);
            if (!blokId) return;

            const payload = {
                saat_bloku_id: blokId,
                grup_ids: [],
                sinif_seviye: "",
                tum_gruplar: false,
            };

            if (zone.dataset.tumGruplar === "1") {
                payload.tum_gruplar = true;
            } else if (zone.dataset.sinif) {
                payload.sinif_seviye = zone.dataset.sinif;
            } else if (zone.dataset.grupId) {
                payload.grup_ids = [parseInt(zone.dataset.grupId, 10)];
            }

            surukleAtama(zone, payload);
        });
    });

    const shareButton = document.querySelector("[data-dp-share]");
    if (shareButton) {
        shareButton.addEventListener("click", async () => {
            const url = `${window.location.origin}/dershane-programi/goruntule/genel/?program=${panel.dataset.program}`;
            try {
                await navigator.clipboard.writeText(url);
                shareButton.textContent = "Kopyalandı";
                setTimeout(() => {
                    shareButton.textContent = "Linki Kopyala";
                }, 1800);
            } catch (error) {
                window.prompt("Program bağlantısı:", url);
            }
        });
    }
})();
