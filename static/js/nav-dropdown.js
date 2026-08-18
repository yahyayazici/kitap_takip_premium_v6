(function () {
    const backdrop = document.createElement('div');
    backdrop.className = 'v3-nav-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);

    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
    const collapseQuery = window.matchMedia('(max-width: 1400px)');
    const SHELL_TOGGLE_SEL = '#v3-menu-toggle, #yonetim-menu-toggle, #talebe-menu-toggle, #ogretmen-menu-toggle, #veli-menu-toggle';
    const SHELL_NAV_SEL = '#v3-nav, #yonetim-nav, #talebe-nav, #ogretmen-nav, #veli-nav';

    function isCollapsedNav() {
        return collapseQuery.matches;
    }

    function syncHeaderHeight() {
        const header = document.querySelector('.v3-header, .cs-v6-header');
        if (!header) {
            return;
        }

        if (isCollapsedNav()) {
            document.documentElement.style.removeProperty('--v3-header-height');
            return;
        }

        document.documentElement.style.setProperty('--v3-header-height', header.offsetHeight + 'px');
    }

    function scheduleHeaderHeightSync() {
        window.requestAnimationFrame(function () {
            syncHeaderHeight();
        });
    }

    function updateBackdrop() {
        const anyDropdownOpen = document.querySelector('.v3-nav-dropdown.open');
        const mobileNavOpen = document.querySelector('.v3-nav.open, .cs-v6-nav.open');
        const showBackdrop = Boolean(anyDropdownOpen && !isCollapsedNav()) || Boolean(mobileNavOpen && isCollapsedNav());
        document.body.classList.toggle('v3-nav-menu-open', Boolean(anyDropdownOpen && !isCollapsedNav()));
        document.body.classList.toggle('v3-mobile-nav-open', Boolean(mobileNavOpen && isCollapsedNav()));
        backdrop.setAttribute('aria-hidden', showBackdrop ? 'false' : 'true');
    }

    function closeDropdowns(except) {
        document.querySelectorAll('.v3-nav-dropdown.open').forEach(function (dropdown) {
            if (dropdown === except) {
                return;
            }
            dropdown.classList.remove('open');
            const trigger = dropdown.querySelector('.v3-nav-trigger');
            if (trigger) {
                trigger.setAttribute('aria-expanded', 'false');
            }
        });
        updateBackdrop();
    }

    function closeMobileNav() {
        const nav = document.querySelector(SHELL_NAV_SEL);
        const toggle = document.querySelector(SHELL_TOGGLE_SEL);
        if (nav) {
            nav.classList.remove('open');
        }
        if (toggle) {
            toggle.setAttribute('aria-expanded', 'false');
        }
        closeDropdowns();
        updateBackdrop();
        scheduleHeaderHeightSync();
    }

    window.csCloseMobileNav = closeMobileNav;

    function openDropdown(dropdown) {
        closeDropdowns(dropdown);
        dropdown.classList.add('open');
        const trigger = dropdown.querySelector('.v3-nav-trigger');
        if (trigger) {
            trigger.setAttribute('aria-expanded', 'true');
        }
        updateBackdrop();
    }

    const toggle = document.querySelector(SHELL_TOGGLE_SEL);
    const nav = document.querySelector(SHELL_NAV_SEL);

    if (toggle && nav) {
        var toggleArmedUntil = 0;
        toggle.addEventListener('click', function (event) {
            if (Date.now() < toggleArmedUntil) {
                event.preventDefault();
                event.stopImmediatePropagation();
                return;
            }
            const open = nav.classList.toggle('open');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (open) {
                toggleArmedUntil = Date.now() + 450;
                nav.classList.add('cs-nav-arming');
                window.setTimeout(function () {
                    nav.classList.remove('cs-nav-arming');
                }, 450);
            } else {
                closeDropdowns();
            }
            updateBackdrop();
            scheduleHeaderHeightSync();
        });

        nav.querySelectorAll('a[href]').forEach(function (link) {
            link.addEventListener('click', function () {
                if (isCollapsedNav()) {
                    closeMobileNav();
                }
            });
        });
    }

    document.querySelectorAll('.v3-nav-dropdown').forEach(function (dropdown) {
        const trigger = dropdown.querySelector('.v3-nav-trigger');
        if (!trigger) {
            return;
        }

        trigger.addEventListener('click', function (event) {
            event.preventDefault();
            event.stopPropagation();
            const willOpen = !dropdown.classList.contains('open');
            if (willOpen) {
                if (isCollapsedNav()) {
                    closeDropdowns(dropdown);
                }
                openDropdown(dropdown);
            } else {
                dropdown.classList.remove('open');
                trigger.setAttribute('aria-expanded', 'false');
                updateBackdrop();
            }
        });

        if (finePointer.matches) {
            var leaveTimer = null;

            dropdown.addEventListener('mouseenter', function () {
                if (isCollapsedNav()) {
                    return;
                }
                if (leaveTimer) {
                    window.clearTimeout(leaveTimer);
                    leaveTimer = null;
                }
                openDropdown(dropdown);
            });

            dropdown.addEventListener('mouseleave', function () {
                if (isCollapsedNav()) {
                    return;
                }
                // Kısa gecikme: scrollbar/layout titremesinde yanlışlıkla kapanmayı önler
                if (leaveTimer) {
                    window.clearTimeout(leaveTimer);
                }
                leaveTimer = window.setTimeout(function () {
                    leaveTimer = null;
                    if (dropdown.matches(':hover')) {
                        return;
                    }
                    dropdown.classList.remove('open');
                    trigger.setAttribute('aria-expanded', 'false');
                    updateBackdrop();
                }, 120);
            });
        }
    });

    backdrop.addEventListener('click', function () {
        if (isCollapsedNav()) {
            closeMobileNav();
            return;
        }
        closeDropdowns();
    });

    document.addEventListener('click', function (event) {
        if (event.target.closest('.v3-nav-dropdown') || event.target.closest('.v3-nav-backdrop')) {
            return;
        }
        if (isCollapsedNav()) {
            return;
        }
        closeDropdowns();
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeMobileNav();
        }
    });

    collapseQuery.addEventListener('change', function () {
        closeMobileNav();
        syncHeaderHeight();
    });

    (function initToasts() {
        var wrap = document.querySelector('[data-v3-toasts]');
        if (!wrap) return;

        var max = Number(wrap.getAttribute('data-max') || 3);
        var ttl = Number(wrap.getAttribute('data-ttl') || 3200);
        var toasts = Array.prototype.slice.call(wrap.querySelectorAll('.v3-toast'));

        if (toasts.length > max) {
            toasts.slice(max).forEach(function (el) { el.remove(); });
            toasts = toasts.slice(0, max);
        }

        function dismiss(toast) {
            if (!toast || toast.classList.contains('is-leaving')) return;
            toast.classList.add('is-leaving');
            window.setTimeout(function () {
                if (toast.parentElement) toast.remove();
                if (wrap && !wrap.querySelector('.v3-toast')) wrap.remove();
            }, 220);
        }

        toasts.forEach(function (toast) {
            toast.style.setProperty('--v3-toast-ttl', ttl + 'ms');
            var closeBtn = toast.querySelector('.v3-toast-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', function () { dismiss(toast); });
            }
            window.setTimeout(function () { dismiss(toast); }, ttl);
        });
    })();

    syncHeaderHeight();
    window.addEventListener('resize', syncHeaderHeight);
})();
