(function () {
    const panel = document.querySelector("[data-ep-panel]");
    if (!panel) return;

    const planId = panel.dataset.plan;
    const hocaId = panel.dataset.hoca;
    const canEdit = panel.dataset.duzenle === "1";
    const csrfToken = document.querySelector("[name=csrfmiddlewaretoken]")?.value || "";

    function postJson(url, payload) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken,
            },
            body: JSON.stringify({ ...payload, plan_id: planId, hoca_id: hocaId }),
        }).then((r) => r.json());
    }

    function openModal(name) {
        document.querySelectorAll("[data-ep-modal]").forEach((modal) => {
            modal.hidden = modal.dataset.epModal !== name;
        });
    }

    function closeModals() {
        document.querySelectorAll("[data-ep-modal]").forEach((modal) => {
            modal.hidden = true;
        });
    }

    document.querySelectorAll("[data-ep-open]").forEach((btn) => {
        btn.addEventListener("click", () => openModal(btn.dataset.epOpen));
    });
    document.querySelectorAll("[data-ep-close]").forEach((btn) => {
        btn.addEventListener("click", closeModals);
    });

    let dragged = null;

    document.querySelectorAll(".ep-pool-card[draggable='true']").forEach((card) => {
        card.addEventListener("dragstart", (event) => {
            dragged = {
                havuzId: card.dataset.havuzId,
                baslik: card.dataset.baslik,
                hedef: card.dataset.hedef,
                renk: card.dataset.renk,
            };
            card.classList.add("dragging");
            event.dataTransfer.effectAllowed = "copy";
        });
        card.addEventListener("dragend", () => {
            card.classList.remove("dragging");
            dragged = null;
        });
    });

    function assignActivity(blokId, data) {
        return postJson("/etut-plani/api/faaliyet-ata/", {
            saat_bloku_id: blokId,
            havuz_id: data.havuzId || null,
            baslik: data.baslik || "",
            aciklama: data.aciklama || "",
            hedef: data.hedef || "",
            renk: data.renk || "",
        }).then((res) => {
            if (res.ok) window.location.reload();
            else alert(res.hata || "Kaydedilemedi.");
        });
    }

    document.querySelectorAll("[data-drop='1']").forEach((cell) => {
        cell.addEventListener("dragover", (event) => {
            if (!canEdit || !dragged) return;
            event.preventDefault();
            cell.classList.add("drag-over");
        });
        cell.addEventListener("dragleave", () => cell.classList.remove("drag-over"));
        cell.addEventListener("drop", (event) => {
            event.preventDefault();
            cell.classList.remove("drag-over");
            if (!canEdit || !dragged) return;
            const blokId = cell.dataset.blokId;
            if (!blokId) return;
            assignActivity(blokId, dragged);
        });
    });

    document.querySelectorAll("[data-ep-cell-add]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const cell = btn.closest("[data-blok-id]");
            document.getElementById("ep-blok-id").value = cell?.dataset.blokId || "";
            openModal("hucre");
        });
    });

    document.querySelectorAll("[data-drop='1'].ep-cell-empty").forEach((cell) => {
        cell.addEventListener("dblclick", () => {
            if (!canEdit) return;
            document.getElementById("ep-blok-id").value = cell.dataset.blokId || "";
            openModal("hucre");
        });
    });

    const hucreForm = document.querySelector("[data-ep-hucre-form]");
    if (hucreForm) {
        hucreForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const fd = new FormData(hucreForm);
            assignActivity(fd.get("blok_id"), {
                baslik: fd.get("baslik"),
                aciklama: fd.get("aciklama"),
                hedef: fd.get("hedef"),
                renk: fd.get("renk"),
            });
        });
    }

    document.querySelectorAll("[data-ep-remove]").forEach((btn) => {
        btn.addEventListener("click", () => {
            if (!confirm("Etkinlik kaldırılsın mı?")) return;
            postJson("/etut-plani/api/faaliyet-sil/", {
                faaliyet_id: btn.dataset.epRemove,
            }).then((res) => {
                if (res.ok) window.location.reload();
            });
        });
    });

    document.querySelectorAll("[data-ep-durum]").forEach((select) => {
        select.addEventListener("change", () => {
            postJson("/etut-plani/api/durum/", {
                faaliyet_id: select.dataset.epDurum,
                durum: select.value,
            });
        });
    });

    const ozelForm = document.querySelector("[data-ep-ozel-form]");
    if (ozelForm) {
        ozelForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const fd = new FormData(ozelForm);
            postJson("/etut-plani/api/havuz/", {
                baslik: fd.get("baslik"),
                hedef: fd.get("hedef"),
                renk: fd.get("renk"),
            }).then((res) => {
                if (res.ok) window.location.reload();
                else alert(res.hata || "Oluşturulamadı.");
            });
        });
    }

    const kopyalaBtn = document.querySelector("[data-ep-kopyala]");
    if (kopyalaBtn) {
        kopyalaBtn.addEventListener("click", () => {
            postJson("/etut-plani/api/kopyala/", {}).then((res) => {
                if (res.ok) {
                    alert(`${res.kopya} etkinlik kopyalandı.`);
                    window.location.reload();
                } else {
                    alert(res.hata || "Kopyalanamadı.");
                }
            });
        });
    }
})();
