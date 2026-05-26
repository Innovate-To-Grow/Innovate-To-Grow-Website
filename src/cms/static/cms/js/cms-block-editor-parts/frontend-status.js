(function () {
    var CHECK_INTERVAL_MS = 30000;
    var state = { reachable: null, maintenance: false, available: null };
    var timer = null;

    function getStatusUrl() {
        var config = window.CMS_ROUTE_EDITOR || {};
        return config.frontendStatusUrl || '';
    }

    function updateUI() {
        var icon = document.getElementById('cms-frontend-status-icon');
        var text = document.getElementById('cms-frontend-status-text');
        if (!icon || !text) return;

        if (state.available === null) {
            icon.className = 'cms-frontend-status-icon is-checking';
            text.textContent = 'Checking frontend…';
            return;
        }

        if (state.available) {
            icon.className = 'cms-frontend-status-icon is-ok';
            text.textContent = 'Frontend online';
        } else if (!state.reachable) {
            icon.className = 'cms-frontend-status-icon is-error';
            text.textContent = 'Frontend unreachable';
        } else if (state.maintenance) {
            icon.className = 'cms-frontend-status-icon is-warning';
            text.textContent = 'Maintenance mode active (preview still works)';
        }

        setPreviewEnabled(state.reachable);
    }

    function setPreviewEnabled(enabled) {
        var objectToolBtn = document.querySelector('[onclick="openLivePreview(); return false;"]');
        var inlineToggle = document.querySelector('.cms-inline-preview-toggle:not([disabled])');

        if (objectToolBtn) {
            var li = objectToolBtn.closest('li');
            if (li) {
                if (enabled) {
                    li.style.pointerEvents = '';
                    li.style.opacity = '';
                    objectToolBtn.title = 'Open a live-updating preview in a new tab';
                } else {
                    li.style.pointerEvents = 'none';
                    li.style.opacity = '0.4';
                    objectToolBtn.title = 'Preview unavailable — frontend is not reachable';
                }
            }
        }

        if (inlineToggle) {
            if (enabled) {
                inlineToggle.disabled = false;
                inlineToggle.title = 'Toggle inline live preview';
            } else {
                inlineToggle.disabled = true;
                inlineToggle.title = 'Preview unavailable — frontend is not reachable';
            }
        }
    }

    function check() {
        var url = getStatusUrl();
        if (!url) {
            state = { reachable: false, maintenance: false, available: false };
            updateUI();
            return;
        }

        fetch(url, { credentials: 'same-origin' })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                state.reachable = data.frontend_reachable;
                state.maintenance = data.maintenance_mode;
                state.available = data.preview_available;
                updateUI();
            })
            .catch(function () {
                state = { reachable: false, maintenance: false, available: false };
                updateUI();
            });
    }

    function start() {
        check();
        timer = setInterval(check, CHECK_INTERVAL_MS);
    }

    function stop() {
        if (timer) { clearInterval(timer); timer = null; }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }

    window.ITGCmsFrontendStatus = { check: check, start: start, stop: stop, getState: function () { return state; } };
})();
