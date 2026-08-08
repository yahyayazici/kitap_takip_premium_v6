(function () {
  function qs(root, sel) { return root.querySelector(sel); }

  function okunduUrl(template, id) {
    return String(template || "").replace(/\/0\/?$/, "/" + id + "/").replace(/\/0\//, "/" + id + "/");
  }

  function renderList(root, items) {
    var list = qs(root, "[data-bn-list]");
    if (!list) return;
    if (!items || !items.length) {
      list.innerHTML = '<li class="bn-empty">Yeni bildirim yok.</li>';
      return;
    }
    list.innerHTML = items.map(function (b) {
      var cls = "bn-item" + (b.okundu ? "" : " is-unread");
      var meta = (b.tur_etiket || "") + (b.bitis_etiket ? " · şu güne kadar " + b.bitis_etiket : "") + (b.zaman_etiket ? " · " + b.zaman_etiket : "");
      var href = b.link || root.dataset.merkezUrl || "#";
      return (
        '<li><a class="' + cls + '" href="' + href + '" data-bn-item data-id="' + b.id + '">' +
          '<p class="bn-item-title">' + escapeHtml(b.baslik) + '</p>' +
          (b.mesaj ? '<p class="bn-item-msg">' + escapeHtml(truncate(b.mesaj, 110)) + '</p>' : '') +
          '<p class="bn-item-meta">' + escapeHtml(meta) + '</p>' +
        '</a></li>'
      );
    }).join("");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function truncate(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  function setBadge(root, n) {
    var badge = qs(root, "[data-bn-badge]");
    var btn = qs(root, "[data-bn-toggle]");
    n = Number(n) || 0;
    if (badge) {
      badge.textContent = String(n);
      badge.hidden = n <= 0;
    }
    if (btn) btn.classList.toggle("has-unread", n > 0);
  }

  function post(url, csrf) {
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrf || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      credentials: "same-origin",
    }).then(function (r) { return r.json(); });
  }

  function load(root) {
    var url = root.dataset.listeUrl;
    if (!url) return;
    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (!data || !data.ok) return;
        setBadge(root, data.okunmamis);
        renderList(root, data.bildirimler || []);
      })
      .catch(function () {
        var list = qs(root, "[data-bn-list]");
        if (list) list.innerHTML = '<li class="bn-empty">Bildirimler yüklenemedi.</li>';
      });
  }

  function bind(root) {
    if (root.dataset.bound) return;
    root.dataset.bound = "1";
    var btn = qs(root, "[data-bn-toggle]");
    var panel = qs(root, "[data-bn-panel]");
    var csrf = root.dataset.csrf || "";

    if (btn && panel) {
      btn.addEventListener("click", function (e) {
        e.stopPropagation();
        var open = !panel.classList.contains("is-open");
        panel.classList.toggle("is-open", open);
        panel.hidden = !open;
        btn.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) load(root);
      });
    }

    document.addEventListener("click", function (e) {
      if (!root.contains(e.target) && panel) {
        panel.classList.remove("is-open");
        panel.hidden = true;
        if (btn) btn.setAttribute("aria-expanded", "false");
      }
    });

    root.addEventListener("click", function (e) {
      var item = e.target.closest("[data-bn-item]");
      if (item) {
        var id = item.getAttribute("data-id");
        var tpl = root.dataset.okunduUrl;
        if (id && tpl) {
          post(okunduUrl(tpl, id), csrf).then(function (data) {
            if (data && data.ok) setBadge(root, data.okunmamis);
          });
        }
        return;
      }
      if (e.target.closest("[data-bn-tumunu]")) {
        e.preventDefault();
        post(root.dataset.tumunuUrl, csrf).then(function (data) {
          if (data && data.ok) {
            setBadge(root, 0);
            load(root);
          }
        });
      }
    });

    // İlk yüklemede rozet
    if (Number(root.querySelector("[data-bn-badge]")?.textContent || 0) === 0) {
      // context'ten geldiyse bırak; yoksa sessizce güncelle
    }
  }

  document.querySelectorAll("[data-bn-root]").forEach(bind);
})();
