(function () {
    const page = document.getElementById("kttSonucGirPage");
    if (!page) return;

    const cikarUrl = page.dataset.cikarUrl;
    const bar = document.getElementById("kttKatilmayanBar");
    const countEl = document.getElementById("kttKatilmayanCount");
    const cikarBtn = document.getElementById("kttSecilenleriCikar");
    const selectAll = document.getElementById("kttSelectAllKatilmayan");
    const feedbackEl = document.getElementById("kttKatilmayanFeedback");
    const toplamSoru = Math.max(0, parseInt(page.dataset.toplamSoru || "0", 10) || 0);
    const table = document.getElementById("kttSonucTable");
    const csrfToken = document.querySelector("#kttSonucForm [name=csrfmiddlewaretoken]")?.value || "";

    function sayi(input) {
        const n = parseInt(String(input?.value || "0"), 10);
        return Number.isFinite(n) && n > 0 ? n : 0;
    }

    function formatSayi(n) {
        return (Math.round(n * 100) / 100).toFixed(2);
    }

    function satiriHesapla(row) {
        const dogruEl = row.querySelector(".ktt-dogru");
        const yanlisEl = row.querySelector(".ktt-yanlis");
        const bosEl = row.querySelector(".ktt-bos");
        if (!dogruEl || !yanlisEl || !bosEl) return;

        let dogru = sayi(dogruEl);
        let yanlis = sayi(yanlisEl);
        if (dogru > toplamSoru) {
            dogru = toplamSoru;
            dogruEl.value = String(dogru);
        }
        if (yanlis > toplamSoru - dogru) {
            yanlis = Math.max(0, toplamSoru - dogru);
            yanlisEl.value = String(yanlis);
        }

        const bos = Math.max(0, toplamSoru - dogru - yanlis);
        bosEl.value = String(bos);

        let net = dogru - yanlis / 4;
        if (net < 0) net = 0;
        const puan = toplamSoru > 0 ? (net * 100) / toplamSoru : 0;
        const netHucre = row.querySelector(".ktt-net");
        const puanHucre = row.querySelector(".ktt-puan");
        if (netHucre) netHucre.textContent = formatSayi(net);
        if (puanHucre) puanHucre.textContent = formatSayi(puan);
    }

    table?.querySelectorAll("tbody tr[data-talebe-id]").forEach((row) => {
        row.querySelectorAll(".ktt-dogru, .ktt-yanlis").forEach((input) => {
            input.addEventListener("input", () => satiriHesapla(row));
            input.addEventListener("change", () => satiriHesapla(row));
        });
    });

    function katilmayanChecks() {
        return Array.from(document.querySelectorAll(".ktt-katilmayan-check"));
    }

    function seciliChecks() {
        return katilmayanChecks().filter((cb) => cb.checked);
    }

    function guncelleSecim() {
        const secili = seciliChecks();
        const adet = secili.length;
        const sayac = document.getElementById("kttSecimSayisi");
        if (sayac) sayac.textContent = String(adet);
        if (cikarBtn && cikarBtn.dataset.busy !== "1") {
            cikarBtn.disabled = adet === 0;
        }

        if (selectAll) {
            const tumu = katilmayanChecks();
            selectAll.indeterminate = adet > 0 && adet < tumu.length;
            selectAll.checked = tumu.length > 0 && adet === tumu.length;
        }
    }

    function guncelleKatilmayanSayisi() {
        const kalan = katilmayanChecks().length;
        if (countEl) countEl.textContent = String(kalan);
        if (kalan === 0 && bar) {
            bar.hidden = true;
        }
        if (selectAll) {
            selectAll.disabled = kalan === 0;
            if (kalan === 0) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            }
        }
    }

    function mesajGoster(metin, tur) {
        if (!feedbackEl) return;
        feedbackEl.textContent = metin;
        feedbackEl.hidden = false;
        feedbackEl.classList.toggle("is-error", tur === "error");
        feedbackEl.classList.toggle("is-success", tur === "success");
        window.clearTimeout(mesajGoster._timer);
        mesajGoster._timer = window.setTimeout(() => {
            feedbackEl.hidden = true;
        }, 4000);
    }

    function satirlariKaldir(talebeIds) {
        const idSet = new Set(talebeIds.map(String));
        table?.querySelectorAll("tbody tr[data-talebe-id]").forEach((row) => {
            if (!idSet.has(row.dataset.talebeId)) return;
            row.classList.add("ktt-row-removing");
            window.setTimeout(() => row.remove(), 180);
        });
        window.setTimeout(() => {
            guncelleKatilmayanSayisi();
            guncelleSecim();
        }, 200);
    }

    async function secilenleriCikar() {
        const secili = seciliChecks();
        if (!secili.length || !cikarUrl || cikarBtn?.dataset.busy === "1") return;

        const adet = secili.length;
        const onay = window.confirm(
            adet === 1
                ? "Seçili öğrenci sonuç listesinden çıkarılsın mı?"
                : `${adet} öğrenci sonuç listesinden çıkarılsın mı?`
        );
        if (!onay) return;

        const formData = new FormData();
        secili.forEach((cb) => formData.append("talebe_ids", cb.value));

        const oncekiLabel = cikarBtn?.innerHTML || "";
        if (cikarBtn) {
            cikarBtn.dataset.busy = "1";
            cikarBtn.disabled = true;
            cikarBtn.textContent = "Çıkarılıyor…";
        }

        try {
            const response = await fetch(cikarUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: formData,
            });

            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                data = { ok: false, hata: "Sunucu yanıtı okunamadı." };
            }

            if (!response.ok || !data.ok) {
                mesajGoster(data.hata || "İşlem başarısız.", "error");
                return;
            }

            satirlariKaldir(data.talebe_ids || secili.map((cb) => cb.value));
            mesajGoster(data.mesaj || "Seçilen öğrenciler listeden çıkarıldı.", "success");
        } catch (_) {
            mesajGoster("Bağlantı hatası. Tekrar deneyin.", "error");
        } finally {
            if (cikarBtn) {
                delete cikarBtn.dataset.busy;
                cikarBtn.innerHTML = oncekiLabel;
            }
            guncelleSecim();
        }
    }

    katilmayanChecks().forEach((cb) => {
        cb.addEventListener("change", guncelleSecim);
    });

    selectAll?.addEventListener("change", () => {
        const checked = selectAll.checked;
        katilmayanChecks().forEach((cb) => {
            cb.checked = checked;
        });
        guncelleSecim();
    });

    cikarBtn?.addEventListener("click", secilenleriCikar);

    guncelleSecim();
})();
