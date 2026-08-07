(function () {
    const backdrop = document.createElement('div');
    backdrop.className = 'v3-nav-backdrop';
    backdrop.setAttribute('aria-hidden', 'true');
    document.body.appendChild(backdrop);

    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');

    function syncHeaderHeight() {
        const header = document.querySelector('.v3-header, .cs-v6-header');
        if (header) {
            document.documentElement.style.setProperty('--v3-header-height', header.offsetHeight + 'px');
        }
    }

    function updateBackdrop() {
        const anyOpen = document.querySelector('.v3-nav-dropdown.open');
        document.body.classList.toggle('v3-nav-menu-open', Boolean(anyOpen));
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

    function openDropdown(dropdown) {
        closeDropdowns(dropdown);
        dropdown.classList.add('open');
        const trigger = dropdown.querySelector('.v3-nav-trigger');
        if (trigger) {
            trigger.setAttribute('aria-expanded', 'true');
        }
        updateBackdrop();
    }

    const toggle = document.getElementById('v3-menu-toggle') || document.getElementById('yonetim-menu-toggle');
    const nav = document.getElementById('v3-nav') || document.getElementById('yonetim-nav');

    if (toggle && nav) {
        toggle.addEventListener('click', function () {
            const open = nav.classList.toggle('open');
            toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
            if (!open) {
                closeDropdowns();
            }
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
                openDropdown(dropdown);
            } else {
                dropdown.classList.remove('open');
                trigger.setAttribute('aria-expanded', 'false');
                updateBackdrop();
            }
        });

        if (finePointer.matches) {
            dropdown.addEventListener('mouseenter', function () {
                openDropdown(dropdown);
            });

            dropdown.addEventListener('mouseleave', function () {
                dropdown.classList.remove('open');
                trigger.setAttribute('aria-expanded', 'false');
                updateBackdrop();
            });
        }
    });

    backdrop.addEventListener('click', function () {
        closeDropdowns();
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.v3-nav-dropdown') && !event.target.closest('.v3-nav-backdrop')) {
            closeDropdowns();
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closeDropdowns();
        }
    });

    document.querySelectorAll('.v3-toast-close').forEach(function (button) {
        button.addEventListener('click', function () {
            button.parentElement.remove();
        });
    });

    syncHeaderHeight();
    window.addEventListener('resize', syncHeaderHeight);
})();
