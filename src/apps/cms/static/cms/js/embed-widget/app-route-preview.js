// The App Route Preview section of the embed widget change form: /<app-route>?_isolated=1 in an iframe,
// for app_route widgets, after probing that the frontend serves the route. Extends window.CMSEmbedAdmin
// (core.js) with show/hide/refreshAppRoutePreview; previews.js binds its refresh button and width select.
(function (ns) {
    var state = ns.state;
    var cfg = ns.config;
    var safeHttpUrl = ns.safeHttpUrl;

    function appRouteSection() { return document.getElementById('cms-widget-app-route-section'); }
    function appRoutePreviewIframe() { return document.getElementById('cms-widget-app-route-preview-iframe'); }
    function appRouteStatus() { return document.getElementById('cms-widget-app-route-status'); }

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
            if (route === '/schedule') {
                var schedule = ns.fields && ns.fields.schedule ? ns.fields.schedule() : null;
                var scheduleId = schedule ? String(schedule.value || '').trim() : '';
                if (scheduleId) {
                    url.searchParams.set('schedule_id', scheduleId);
                }
            }
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
})(window.CMSEmbedAdmin);
