// All three iframe preview sections rendered on the admin change form:
//   - Live Preview       /_embed/<slug>/           (saved embed view)
//   - Page Preview       /<page-route>             (full source page, blocks widgets)
//   - App Route Preview  /<app-route>?_isolated=1  (standalone, app_route widgets)
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

    function appRouteSection() { return document.getElementById('cms-widget-app-route-section'); }
    function appRoutePreviewIframe() { return document.getElementById('cms-widget-app-route-preview-iframe'); }
    function appRoutePreviewContainer() { return document.getElementById('cms-widget-app-route-preview-container'); }
    function appRouteStatus() { return document.getElementById('cms-widget-app-route-status'); }

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

    // --- App Route Preview (standalone, app_route widgets only) ---

    function setAppRouteStatus(message, kind) {
        var status = appRouteStatus();
        if (!status) return;
        status.textContent = message || '';
        status.className = 'cms-widget-preview-status' + (kind ? ' is-' + kind : '');
        status.hidden = !message;
    }

    function clearAppRouteStatus() {
        setAppRouteStatus('', '');
    }

    function buildFrontendUrl(route, isolated) {
        var frontend = cfg.frontendUrl || '';
        if (!frontend || !route) return '';
        try {
            var url = new URL(route, frontend + '/');
            if (isolated) {
                url.searchParams.set('_isolated', '1');
                var hiddenSections = ns.getSelectedHiddenSections ? ns.getSelectedHiddenSections() : [];
                if (hiddenSections.length) {
                    url.searchParams.set('hide-sections', hiddenSections.join(','));
                }
            }
            return safeHttpUrl(url.toString());
        } catch (e) {
            return '';
        }
    }

    function appendInlineCode(parent, value) {
        var code = document.createElement('code');
        code.textContent = value;
        parent.appendChild(code);
    }

    function setFrontendReachabilityError(frontend) {
        var status = appRouteStatus();
        if (!status) return;
        status.textContent = '';
        status.className = 'cms-widget-preview-status is-error';
        status.hidden = false;
        status.appendChild(document.createTextNode('Could not reach '));
        appendInlineCode(status, String(frontend || 'FRONTEND_URL'));
        status.appendChild(document.createTextNode('. In local dev, start the frontend with '));
        appendInlineCode(status, 'cd pages');
        status.appendChild(document.createTextNode(' and '));
        appendInlineCode(status, 'npm run dev');
        status.appendChild(document.createTextNode(', then refresh this preview.'));
    }

    function probePreviewUrl(url) {
        if (!window.fetch) return Promise.resolve(true);
        var controller = window.AbortController ? new AbortController() : null;
        var timeout = null;
        if (controller) {
            timeout = setTimeout(function () { controller.abort(); }, 3500);
        }
        // no-cors returns an opaque response for HTTP statuses, including 404/500.
        // Treat only network failures and aborts as "frontend unreachable."
        return fetch(url, {
            method: 'GET',
            mode: 'no-cors',
            cache: 'no-store',
            credentials: 'omit',
            signal: controller ? controller.signal : undefined,
        })
            .then(function () { return true; })
            .catch(function () { return false; })
            .then(function (ok) {
                if (timeout) clearTimeout(timeout);
                return ok;
            });
    }

    ns.showAppRoutePreview = function (route) {
        var frontend = cfg.frontendUrl || '';
        var sec = appRouteSection();
        var iframe = appRoutePreviewIframe();
        var label = document.getElementById('cms-widget-app-route-label');
        var openLink = document.getElementById('cms-widget-app-route-open-link');
        var placeholder = document.getElementById('cms-widget-app-route-placeholder');
        if (!sec || !iframe) return;
        sec.style.display = '';

        if (!route) {
            // Keep the section visible with a placeholder so users understand
            // where the preview will render once they pick a route.
            if (label) label.textContent = '(no route selected)';
            if (openLink) {
                openLink.removeAttribute('href');
                openLink.style.display = 'none';
            }
            iframe.removeAttribute('src');
            iframe.style.display = 'none';
            if (placeholder) placeholder.style.display = '';
            clearAppRouteStatus();
            state.currentAppRoute = '';
            return;
        }

        if (label) label.textContent = route;
        if (placeholder) placeholder.style.display = 'none';
        iframe.style.display = 'none';
        if (openLink) openLink.style.display = '';
        state.currentAppRoute = route;

        if (!frontend) {
            iframe.removeAttribute('src');
            if (openLink) openLink.removeAttribute('href');
            setAppRouteStatus('FRONTEND_URL is not configured, so app-route preview is unavailable.', 'error');
            return;
        }
        var isolatedUrl = buildFrontendUrl(route, true);
        var openUrl = buildFrontendUrl(route, false);
        if (!isolatedUrl) {
            iframe.removeAttribute('src');
            setAppRouteStatus('FRONTEND_URL must be an http(s) URL before this route can be previewed.', 'error');
            return;
        }
        if (openLink && openUrl) openLink.href = openUrl;
        var requestId = (state.appRoutePreviewRequestId || 0) + 1;
        state.appRoutePreviewRequestId = requestId;
        setAppRouteStatus('Loading app route preview...');
        probePreviewUrl(isolatedUrl).then(function (ok) {
            if (state.appRoutePreviewRequestId !== requestId) return;
            if (!ok) {
                iframe.removeAttribute('src');
                iframe.style.display = 'none';
                setFrontendReachabilityError(frontend);
                return;
            }
            clearAppRouteStatus();
            iframe.style.display = '';
            iframe.src = isolatedUrl;
        });
    };

    ns.hideAppRoutePreview = function () {
        var sec = appRouteSection();
        if (sec) sec.style.display = 'none';
        var iframe = appRoutePreviewIframe();
        if (iframe) {
            iframe.removeAttribute('src');
            iframe.style.display = 'none';
        }
        clearAppRouteStatus();
        state.currentAppRoute = '';
    };

    ns.refreshAppRoutePreview = function () {
        if (!state.currentAppRoute) return;
        ns.showAppRoutePreview(state.currentAppRoute);
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
