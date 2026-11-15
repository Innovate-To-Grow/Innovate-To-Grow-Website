// All three iframe preview sections rendered on the admin change form:
//   - Live Preview       /_embed/<slug>/           (saved embed view)
//   - Page Preview       /<page-route>             (full source page, blocks widgets)
//   - App Route Preview  /<app-route>?_isolated=1  (standalone, app_route widgets)
// The App Route Preview's helpers live in app-route-preview.js (loaded right after this file).
// Exposes show/hide/refresh helpers on window.CMSEmbedAdmin plus bindPreview
// which wires the refresh buttons, width selects, and postMessage resize.
(function (ns) {
    var state = ns.state;
    var cfg = ns.config;
    var safeHttpUrl = ns.safeHttpUrl;

    function previewSection() { return document.getElementById('cms-widget-preview-section'); }
    function previewIframe() { return document.getElementById('cms-widget-preview-iframe'); }
    function previewContainer() { return document.getElementById('cms-widget-preview-container'); }

    function pagePreviewSection() { return document.getElementById('cms-widget-page-preview-section'); }
    function pagePreviewIframe() { return document.getElementById('cms-widget-page-preview-iframe'); }
    function pagePreviewContainer() { return document.getElementById('cms-widget-page-preview-container'); }

    function appRoutePreviewContainer() { return document.getElementById('cms-widget-app-route-preview-container'); }

    // --- Live Preview (/_embed/<slug>/) ---

    ns.hidePreview = function () {
        var sec = previewSection();
        if (sec) sec.style.display = 'none';
        state.currentPreviewUrl = '';
    };

    ns.showPreview = function (embedUrl) {
        var sec = previewSection();
        var iframe = previewIframe();
        if (!sec || !iframe) return;

        var safeUrl = safeHttpUrl(embedUrl);
        if (!safeUrl) {
            ns.hidePreview();
            return;
        }

        sec.style.display = '';

        if (safeUrl === state.currentPreviewUrl) return;
        state.currentPreviewUrl = safeUrl;

        clearTimeout(state.previewDebounce);
        state.previewDebounce = setTimeout(function () {
            iframe.src = safeUrl;
        }, 400);
    };

    ns.refreshPreview = function () {
        var iframe = previewIframe();
        if (!iframe || !state.currentPreviewUrl) return;
        // currentPreviewUrl is already validated in showPreview, but re-check
        // on refresh so the sink can't be reached with a stale unsafe value
        // across re-entrancy.
        var safeUrl = safeHttpUrl(state.currentPreviewUrl);
        if (!safeUrl) return;
        iframe.src = '';
        setTimeout(function () { iframe.src = safeUrl; }, 50);
    };

    // --- Page Preview (full source page, blocks widgets only) ---

    ns.showPagePreview = function (route) {
        var frontend = cfg.frontendUrl || '';
        if (!frontend || !route) {
            ns.hidePagePreview();
            return;
        }
        var pageUrl = safeHttpUrl(frontend + route);
        if (!pageUrl) {
            ns.hidePagePreview();
            return;
        }
        state.currentPageRoute = route;
        var sec = pagePreviewSection();
        var iframe = pagePreviewIframe();
        var routeLabel = document.getElementById('cms-widget-page-route-label');
        var openLink = document.getElementById('cms-widget-page-open-link');
        if (!sec || !iframe) return;

        sec.style.display = '';
        if (routeLabel) routeLabel.textContent = route;
        if (openLink) openLink.href = pageUrl;
        iframe.src = pageUrl;
    };

    ns.hidePagePreview = function () {
        var sec = pagePreviewSection();
        if (sec) sec.style.display = 'none';
        state.currentPageRoute = '';
    };

    ns.refreshPagePreview = function () {
        var iframe = pagePreviewIframe();
        var frontend = cfg.frontendUrl || '';
        if (!iframe || !state.currentPageRoute || !frontend) return;
        var pageUrl = safeHttpUrl(frontend + state.currentPageRoute);
        if (!pageUrl) return;
        iframe.src = '';
        setTimeout(function () { iframe.src = pageUrl; }, 50);
    };

    ns.fetchPageRouteAndShowPreview = function (pageId) {
        if (!pageId || !cfg.pageInfoUrl) {
            ns.hidePagePreview();
            return;
        }
        var url = cfg.pageInfoUrl + '?page_id=' + encodeURIComponent(pageId);
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (data) {
                if (data.route) {
                    ns.showPagePreview(data.route);
                } else {
                    ns.hidePagePreview();
                }
            })
            .catch(function () { ns.hidePagePreview(); });
    };

    // --- Shared bindings: refresh buttons, width selects, postMessage ---

    ns.bindPreview = function () {
        var refreshBtn = document.getElementById('cms-widget-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', ns.refreshPreview);
        }

        var widthSelect = document.getElementById('cms-widget-preview-width');
        if (widthSelect) {
            widthSelect.addEventListener('change', function () {
                var container = previewContainer();
                if (container) container.style.maxWidth = widthSelect.value;
            });
        }

        var pageRefreshBtn = document.getElementById('cms-widget-page-refresh-btn');
        if (pageRefreshBtn) {
            pageRefreshBtn.addEventListener('click', ns.refreshPagePreview);
        }

        var pageWidthSelect = document.getElementById('cms-widget-page-preview-width');
        if (pageWidthSelect) {
            pageWidthSelect.addEventListener('change', function () {
                var container = pagePreviewContainer();
                if (container) container.style.maxWidth = pageWidthSelect.value;
            });
        }

        var appRouteRefreshBtn = document.getElementById('cms-widget-app-route-refresh-btn');
        if (appRouteRefreshBtn) {
            appRouteRefreshBtn.addEventListener('click', ns.refreshAppRoutePreview);
        }

        var appRouteWidthSelect = document.getElementById('cms-widget-app-route-preview-width');
        if (appRouteWidthSelect) {
            appRouteWidthSelect.addEventListener('change', function () {
                var container = appRoutePreviewContainer();
                if (container) container.style.maxWidth = appRouteWidthSelect.value;
            });
        }

        window.addEventListener('message', function (e) {
            // Only accept resize messages from the configured frontend origin
            // (the embed iframe's own origin). Split into two separate checks
            // so the origin allowlist is obvious to CodeQL's taint analysis
            // and to future readers.
            if (!ns.FRONTEND_ORIGIN) return;
            if (e.origin !== ns.FRONTEND_ORIGIN) return;
            if (!e.data || e.data.type !== 'i2g-embed-resize') return;
            var iframe = previewIframe();
            // Clamp height to a positive integer so a malformed payload
            // can't inject CSS via string concatenation.
            var height = Number(e.data.height);
            if (iframe && Number.isFinite(height) && height > 0 && height < 10000) {
                iframe.style.height = Math.floor(height) + 'px';
            }
        });
    };
})(window.CMSEmbedAdmin);
