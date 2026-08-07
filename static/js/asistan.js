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

    function renderMarkdown(text) {
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    function appendMessage(role, text, actions) {
        const wrap = document.createElement('div');
        wrap.className = 'asistan-msg ' + (role === 'user' ? 'user' : 'bot');
        wrap.innerHTML = renderMarkdown(text);

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

    async function sendMessage(message) {
        if (!message.trim()) {
            return;
        }

        appendMessage('user', message);
        history.push({ role: 'user', content: message });
        input.value = '';
        typing.hidden = false;
        suggestions.innerHTML = '';

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                },
                body: JSON.stringify({ message: message, history: history.slice(-14) }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'İstek başarısız.');
            }
            appendMessage('assistant', data.reply, data.actions);
            history.push({ role: 'assistant', content: data.reply });
            renderSuggestions(data.suggestions);
        } catch (error) {
            appendMessage('assistant', error.message || 'Bağlantı hatası. Tekrar deneyin.');
        } finally {
            typing.hidden = true;
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
            'Eğitim takibi, okuma, sınav veya “5-A okuma raporu” gibi isteklerde yardımcı olurum.',
        []
    );
    renderSuggestions([
        'Eğitim takip ile konuşalım',
        'Naber',
        '5-A okuma raporu gönder',
        'Kaç aktif talebe var?',
    ]);
})();
