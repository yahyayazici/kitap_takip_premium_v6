(function () {
    const panel = document.getElementById('asistan-panel');
    const fab = document.getElementById('asistan-fab');
    const closeBtn = document.getElementById('asistan-close');
    const form = document.getElementById('asistan-form');
    const input = document.getElementById('asistan-input');
    const messages = document.getElementById('asistan-messages');
    const suggestions = document.getElementById('asistan-suggestions');
    const typing = document.getElementById('asistan-typing');

    if (!panel || !fab || !form || !input || !messages) {
        return;
    }

    const history = [];
    const csrfToken = form.querySelector('[name=csrfmiddlewaretoken]').value;
    const apiUrl = form.dataset.apiUrl;

    function toggle(open) {
        panel.classList.toggle('open', open);
        fab.setAttribute('aria-expanded', open ? 'true' : 'false');
        if (open) {
            input.focus();
        }
    }

    const sendBtn = form.querySelector('.asistan-send');
    const ISTEK_ZAMAN_ASIMI_MS = 90000;

    function escapeHtml(text) {
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderMarkdown(text) {
        // Yapay zeka çıktısı HTML olarak yorumlanmasın diye önce kaçışlanır.
        return escapeHtml(text || '')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    function appendMessage(role, text, actions, uyari) {
        const wrap = document.createElement('div');
        wrap.className = 'asistan-msg ' + (role === 'user' ? 'user' : 'bot') + (role === 'error' ? ' hata' : '');
        wrap.innerHTML = renderMarkdown(text);

        if (uyari) {
            const note = document.createElement('div');
            note.className = 'asistan-uyari';
            note.textContent = uyari;
            wrap.appendChild(note);
        }

        if (actions && actions.length) {
            const actionsEl = document.createElement('div');
            actionsEl.className = 'asistan-actions';
            actions.forEach(function (action) {
                if (action.type === 'pdf' || action.type === 'link') {
                    const link = document.createElement('a');
                    link.className = 'asistan-action-btn' + (action.type === 'pdf' ? ' pdf' : '');
                    link.href = action.url;
                    link.target = '_blank';
                    link.rel = 'noopener';
                    link.textContent = action.type === 'pdf' ? '⬇ ' + action.label : action.label;
                    actionsEl.appendChild(link);
                }
            });
            wrap.appendChild(actionsEl);
        }

        messages.appendChild(wrap);
        messages.scrollTop = messages.scrollHeight;
    }

    function renderSuggestions(items) {
        suggestions.innerHTML = '';
        (items || []).forEach(function (text) {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.className = 'asistan-chip';
            chip.textContent = text;
            chip.addEventListener('click', function () {
                input.value = text;
                form.requestSubmit();
            });
            suggestions.appendChild(chip);
        });
    }

    let bekleniyor = false;

    function setBusy(busy) {
        bekleniyor = busy;
        typing.hidden = !busy;
        input.disabled = busy;
        if (sendBtn) {
            sendBtn.disabled = busy;
        }
    }

    function hataMesaji(status, data) {
        if (data && data.error) {
            return data.error;
        }
        if (status === 502 || status === 504) {
            return 'Sunucu zamanında yanıt vermedi (zaman aşımı). Lütfen tekrar deneyin.';
        }
        if (status === 403) {
            return 'Oturumunuz sona ermiş olabilir. Sayfayı yenileyip tekrar deneyin.';
        }
        return 'İstek başarısız oldu (' + status + '). Lütfen tekrar deneyin.';
    }

    async function sendMessage(message) {
        if (!message.trim() || bekleniyor) {
            return;
        }

        appendMessage('user', message);
        input.value = '';
        suggestions.innerHTML = '';
        setBusy(true);
        typing.textContent = 'Yanıt hazırlanıyor…';
        const uzunBekleme = setTimeout(function () {
            typing.textContent = 'Yanıt hazırlanıyor… Panel verileri inceleniyor, biraz daha sürebilir.';
        }, 8000);
        const controller = new AbortController();
        const zamanlayici = setTimeout(function () {
            controller.abort();
        }, ISTEK_ZAMAN_ASIMI_MS);

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                // Geçmiş: önceki mesajlar; mevcut mesaj ayrıca gönderilir.
                body: JSON.stringify({ message: message, history: history.slice(-12) }),
                signal: controller.signal,
            });
            let data = null;
            try {
                data = await response.json();
            } catch (parseError) {
                data = null;
            }
            if (!response.ok || !data) {
                throw new Error(hataMesaji(response.status, data));
            }
            appendMessage('assistant', data.reply, data.actions, data.uyari);
            history.push({ role: 'user', content: message });
            history.push({ role: 'assistant', content: data.reply });
            renderSuggestions(data.suggestions);
        } catch (error) {
            const metin = error.name === 'AbortError'
                ? 'Yanıt zamanında gelmedi (zaman aşımı). Lütfen sorunuzu tekrar gönderin.'
                : (error.message === 'Failed to fetch'
                    ? 'Sunucuya bağlanılamadı. İnternet bağlantınızı kontrol edin.'
                    : (error.message || 'Bağlantı hatası. Tekrar deneyin.'));
            appendMessage('error', metin);
        } finally {
            clearTimeout(zamanlayici);
            clearTimeout(uzunBekleme);
            setBusy(false);
            input.focus();
        }
    }

    fab.addEventListener('click', function () {
        toggle(!panel.classList.contains('open'));
    });

    if (closeBtn) {
        closeBtn.addEventListener('click', function () {
            toggle(false);
        });
    }

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        sendMessage(input.value);
    });

    appendMessage(
        'assistant',
        'Merhaba! İster sohbet edelim ister rapor isteyin — doğal Türkçe yazmanız yeterli. ' +
            'Eğitim takibi, okuma, sınav veya “5-A okuma raporu” gibi isteklerde yardımcı olurum. ' +
            'Kayıt ekleme, silme veya mesaj gönderme gibi işlemleri yapamam; bunlar için ilgili menüyü tarif ederim.',
        []
    );
    renderSuggestions([
        'Eğitim takip ile konuşalım',
        'Naber',
        '5-A okuma raporu gönder',
        'Kaç aktif talebe var?',
    ]);
})();
