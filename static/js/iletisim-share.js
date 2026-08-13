(function () {
    "use strict";

    function qs(sel, root) {
        return (root || document).querySelector(sel);
    }

    function qsa(sel, root) {
        return Array.prototype.slice.call((root || document).querySelectorAll(sel));
    }

    function postForm(url, data, csrf) {
        var body = new URLSearchParams();
        Object.keys(data).forEach(function (k) {
            if (data[k] !== undefined && data[k] !== null) body.append(k, data[k]);
        });
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrf,
            },
            body: body.toString(),
            credentials: "same-origin",
        }).then(function (r) {
            return r.json();
        });
    }

    function olayKaydet(root, tur) {
        var pk = root.getAttribute("data-paket-id");
        var csrf = root.getAttribute("data-csrf");
        return postForm("/iletisim/api/paket/" + pk + "/olay/", { olay_tur: tur }, csrf);
    }

    function feedback(root, mesaj, isError) {
        var el = qs("[data-im-feedback]", root);
        if (!el) return;
        el.hidden = false;
        el.textContent = mesaj;
        el.style.color = isError ? "#d74a4a" : "#1aa477";
    }

    function guncelMesaj(root) {
        var ta = qs("[data-im-message]", root);
        return ta ? ta.value.trim() : qs("[data-im-wa-preview]", root).textContent.trim();
    }

    function waOnizlemeGuncelle(root) {
        var preview = qs("[data-im-wa-preview]", root);
        if (preview) preview.textContent = guncelMesaj(root);
    }

    function mobilMi() {
        return /Android|iPhone|iPod/i.test(navigator.userAgent);
    }

    function nativeShareDestek() {
        return typeof navigator !== "undefined" && typeof navigator.share === "function";
    }

    function paylasimPayload(file, mesaj) {
        return {
            files: [file],
            text: mesaj,
            title: (file.name || "KTT").replace(/\.pdf$/i, ""),
        };
    }

    function waButonlariHazir(root, hazir) {
        qsa("[data-im-whatsapp-share], [data-im-wa-pdf-send]", root).forEach(function (btn) {
            btn.disabled = !hazir;
            if (btn.hasAttribute("data-im-whatsapp-share")) {
                btn.textContent = hazir ? "WhatsApp'ta Paylaş" : "PDF hazırlanıyor…";
            }
        });
    }

    async function pdfBlobAl(url) {
        var res = await fetch(url, { credentials: "same-origin" });
        if (!res.ok) throw new Error("PDF indirilemedi.");
        var blob = await res.blob();
        var ad = "ktt.pdf";
        var cd = res.headers.get("Content-Disposition");
        if (cd) {
            var m = /filename="?([^";]+)"?/.exec(cd);
            if (m) ad = m[1];
        }
        return { blob: blob, ad: ad };
    }

    function pdfOnbellekYukle(root) {
        var download = qs("[data-im-download]", root);
        if (!download) {
            root._imPdfReady = true;
            return Promise.resolve(null);
        }
        waButonlariHazir(root, false);
        return pdfBlobAl(download.getAttribute("href"))
            .then(function (pdf) {
                root._imPdf = pdf;
                root._imPdfFile = new File([pdf.blob], pdf.ad, { type: "application/pdf" });
                root._imPdfReady = true;
                waButonlariHazir(root, true);
                return pdf;
            })
            .catch(function () {
                root._imPdfReady = false;
                waButonlariHazir(root, false);
                feedback(root, "PDF yüklenemedi. Sayfayı yenileyin.", true);
                return null;
            });
    }

    function pdfIndir(file) {
        var url = URL.createObjectURL(file);
        var a = document.createElement("a");
        a.href = url;
        a.download = file.name || "ktt.pdf";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(function () {
            URL.revokeObjectURL(url);
        }, 4000);
    }

    function whatsappDirektAc(mesaj) {
        var encoded = encodeURIComponent(mesaj);
        var appUrl = "whatsapp://send?text=" + encoded;
        var webUrl = "https://web.whatsapp.com/send?text=" + encoded;
        var uygulamaAcildi = false;

        function blurYakala() {
            uygulamaAcildi = true;
        }

        window.addEventListener("blur", blurYakala, { once: true });

        var link = document.createElement("a");
        link.href = appUrl;
        link.style.display = "none";
        document.body.appendChild(link);
        link.click();
        link.remove();

        window.setTimeout(function () {
            window.removeEventListener("blur", blurYakala);
            if (!uygulamaAcildi) {
                window.open(webUrl, "_blank", "noopener,noreferrer");
            }
        }, 900);
    }

    function pdfPanoyaKopyala(file) {
        if (!file || !navigator.clipboard || !window.ClipboardItem) {
            return Promise.resolve(false);
        }
        return navigator.clipboard
            .write([new ClipboardItem({ "application/pdf": file })])
            .then(function () {
                return true;
            })
            .catch(function () {
                return false;
            });
    }

    function dosyaPaylasimDene(root, mesaj, file) {
        if (!nativeShareDestek() || !file) {
            return Promise.resolve(false);
        }
        return navigator
            .share(paylasimPayload(file, mesaj))
            .then(function () {
                olayKaydet(root, "native_share_opened");
                feedback(root, "Mesaj ve PDF paylaşıldı — WhatsApp'ı seçin.");
                return true;
            })
            .catch(function (err) {
                if (err && err.name === "AbortError") throw err;
                return false;
            });
    }

    function whatsappYedek(root, mesaj, file) {
        return pdfPanoyaKopyala(file).then(function (panoOk) {
            pdfIndir(file);
            olayKaydet(root, "file_downloaded");
            whatsappDirektAc(mesaj);
            olayKaydet(root, "whatsapp_share_opened");
            if (panoOk) {
                feedback(
                    root,
                    "WhatsApp açıldı. PDF indirildi ve panoda — sohbette 📎 veya Cmd+V ile ekleyin."
                );
                return;
            }
            feedback(
                root,
                "WhatsApp açıldı. PDF indirildi — sohbette 📎 ile ekleyin."
            );
        });
    }

    function whatsappMesajPdfGonder(root) {
        var mesaj = guncelMesaj(root);
        if (!mesaj) {
            feedback(root, "Mesaj boş.", true);
            return;
        }
        if (!root._imPdfReady) {
            feedback(root, "PDF henüz hazır değil, lütfen bekleyin.", true);
            return;
        }

        var file = root._imPdfFile;

        if (!file) {
            whatsappDirektAc(mesaj);
            olayKaydet(root, "whatsapp_share_opened");
            feedback(root, "WhatsApp açıldı.");
            return;
        }

        if (nativeShareDestek()) {
            dosyaPaylasimDene(root, mesaj, file)
                .then(function (ok) {
                    if (ok) return;
                    return whatsappYedek(root, mesaj, file);
                })
                .catch(function (err) {
                    if (err && err.name === "AbortError") return;
                    return whatsappYedek(root, mesaj, file);
                });
            return;
        }

        whatsappYedek(root, mesaj, file);
    }

    function init() {
        var root = qs("[data-im-share]");
        if (!root) return;

        var csrf = root.getAttribute("data-csrf");
        var pk = root.getAttribute("data-paket-id");

        pdfOnbellekYukle(root);

        var mesajTa = qs("[data-im-message]", root);
        if (mesajTa) {
            mesajTa.addEventListener("input", function () {
                waOnizlemeGuncelle(root);
            });
        }

        var saveBtn = qs("[data-im-save-message]", root);
        if (saveBtn) {
            saveBtn.addEventListener("click", function () {
                postForm("/iletisim/api/paket/" + pk + "/mesaj/", { mesaj: guncelMesaj(root) }, csrf).then(
                    function (data) {
                        if (!data.ok) {
                            feedback(root, data.mesaj || "Kaydedilemedi.", true);
                            return;
                        }
                        feedback(root, "Mesaj güncellendi.");
                        waOnizlemeGuncelle(root);
                    }
                );
            });
        }

        var copyBtn = qs("[data-im-copy-message]", root);
        if (copyBtn) {
            copyBtn.addEventListener("click", function () {
                var mesaj = guncelMesaj(root);
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(mesaj).then(function () {
                        olayKaydet(root, "message_copied");
                        feedback(root, "Mesaj panoya kopyalandı.");
                    });
                } else {
                    feedback(root, "Panoya kopyalama desteklenmiyor.", true);
                }
            });
        }

        root.addEventListener("click", function (e) {
            var waBtn = e.target.closest("[data-im-whatsapp-share], [data-im-wa-pdf-send]");
            if (!waBtn) return;
            e.preventDefault();
            whatsappMesajPdfGonder(root);
        });

        var draftBtn = qs("[data-im-draft-save]", root);
        if (draftBtn) {
            draftBtn.addEventListener("click", function () {
                postForm("/iletisim/api/paket/" + pk + "/taslak/", {}, csrf).then(function (data) {
                    feedback(root, data.ok ? "Taslak kaydedildi." : data.mesaj || "Hata", !data.ok);
                });
            });
        }

        root.querySelectorAll("[data-im-download]").forEach(function (lnk) {
            lnk.addEventListener("click", function () {
                olayKaydet(root, "file_downloaded");
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
