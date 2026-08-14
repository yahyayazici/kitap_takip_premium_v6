(function () {
    "use strict";

    var fileInput = document.getElementById("olcme-kamera-input");
    var preview = document.getElementById("olcme-kamera-preview");
    var ocrBtn = document.getElementById("olcme-kamera-ocr");
    var textarea = document.querySelector('textarea[name="optik_metin"]');
    var statusEl = document.getElementById("olcme-kamera-status");

    if (!fileInput || !textarea) return;

    function setStatus(msg) {
        if (statusEl) statusEl.textContent = msg || "";
    }

    fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file || !preview) return;
        var url = URL.createObjectURL(file);
        preview.src = url;
        preview.hidden = false;
        setStatus("Fotoğraf yüklendi. Metni okumak için OCR’a basın.");
    });

    if (!ocrBtn) return;

    ocrBtn.addEventListener("click", function () {
        var file = fileInput.files && fileInput.files[0];
        if (!file) {
            setStatus("Önce fotoğraf seçin veya çekin.");
            return;
        }
        if (typeof Tesseract === "undefined") {
            setStatus("OCR kütüphanesi yüklenemedi. Metni elle yapıştırın.");
            return;
        }
        ocrBtn.disabled = true;
        setStatus("Metin okunuyor…");
        Tesseract.recognize(file, "eng+tur", { logger: function () {} })
            .then(function (result) {
                var text = (result.data && result.data.text) || "";
                text = text.replace(/\r/g, "").trim();
                if (textarea.value.trim()) {
                    textarea.value = textarea.value.trim() + "\n" + text;
                } else {
                    textarea.value = text;
                }
                setStatus(text ? "Metin alana eklendi; kontrol edip kaydedin." : "Metin bulunamadı; elle düzenleyin.");
            })
            .catch(function () {
                setStatus("OCR başarısız. Metni elle yapıştırın.");
            })
            .finally(function () {
                ocrBtn.disabled = false;
            });
    });
})();
