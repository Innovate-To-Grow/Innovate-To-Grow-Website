(function () {
    var inlineLoaded = false;
    var syncStatusTimer = null;
    var keepaliveTimer = null;
    var KEEPALIVE_MS = 4 * 60 * 1000; // re-post every 4 min to keep 10-min TTL alive
    var lastBlocks = null;

    function getLivePreviewKey() {
        var config = window.CMS_ROUTE_EDITOR || {};
        return config.pageId ? 'cms_live_preview_active_' + config.pageId : '';
    }

    function isActive() { var key = getLivePreviewKey(); return key ? sessionStorage.getItem(key) === 'true' : false; }
    function setActive(active) { var key = getLivePreviewKey(); if (!key) return; active ? sessionStorage.setItem(key, 'true') : sessionStorage.removeItem(key); }

    function getSafePreviewRoute(route) {
        route = String(route || '').trim() || '/';
        if (/^[A-Za-z][A-Za-z0-9+.-]*:/.test(route) || route.indexOf('\\') !== -1 || route.indexOf('//') === 0) return '';
        return route.charAt(0) === '/' ? route : '/' + route;
    }

    function getSafePreviewBase(frontendUrl) {
        try {
            var base = new URL(String(frontendUrl || window.location.origin), window.location.origin);
            if (base.protocol !== 'http:' && base.protocol !== 'https:') return null;
            if (base.username || base.password) return null;
            return base;
        } catch (err) {
            return null;
        }
    }

    function getPreviewUrl() {
        var config = window.CMS_ROUTE_EDITOR || {};
        if (!config.pageId) return '';
        var routeEl = document.getElementById('id_route');
        var route = getSafePreviewRoute(routeEl ? routeEl.value : (config.pageRoute || '/'));
        var base = getSafePreviewBase(config.frontendUrl || '');
        if (!route || !base) return '';
        var url = new URL(route, base);
        url.searchParams.set('cms_live_preview', config.pageId);
        return url.toString();
    }

    function gatherPageData(blocks) {
        var routeEl = document.getElementById('id_route');
        var titleEl = document.getElementById('id_title');
        var slugEl = document.getElementById('id_slug');
        var cssClassEl = document.getElementById('id_page_css_class');
        var metaDescEl = document.getElementById('id_meta_description');
        return { slug: slugEl ? slugEl.value : '', route: routeEl ? routeEl.value : (window.CMS_ROUTE_EDITOR && window.CMS_ROUTE_EDITOR.pageRoute) || '/', title: titleEl ? titleEl.value : '', page_css_class: cssClassEl ? cssClassEl.value : '', meta_description: metaDescEl ? metaDescEl.value : '', blocks: blocks.map(function (block, index) { return { block_type: block.block_type, sort_order: index, data: block.data }; }) };
    }

    function showSyncStatus(text) {
        var el = document.getElementById('cms-preview-sync-status');
        if (!el) return;
        el.textContent = text;
        el.classList.add('is-visible');
        if (syncStatusTimer) clearTimeout(syncStatusTimer);
        syncStatusTimer = setTimeout(function () { el.classList.remove('is-visible'); }, 1200);
    }

    function post(blocks, callback) {
        var config = window.CMS_ROUTE_EDITOR || {};
        if (!config.pageId) return;
        lastBlocks = blocks;
        startKeepalive();
        var csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
        var wrapper = document.getElementById('cms-inline-preview');
        if (wrapper && wrapper.classList.contains('is-active')) showSyncStatus('Syncing\u2026');
        fetch('/cms/live-preview/' + config.pageId + '/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfEl ? csrfEl.value : '' },
            body: JSON.stringify(gatherPageData(blocks)),
            credentials: 'same-origin',
        }).then(function (response) {
            if (!response.ok) console.warn('[CMS Preview] POST failed with status ' + response.status);
            else {
                showSyncStatus('Synced');
                if (callback) callback();
            }
        }).catch(function (err) { console.warn('[CMS Preview] Network error:', err.message || err); });
    }

    function startKeepalive() {
        if (keepaliveTimer) return;
        keepaliveTimer = setInterval(function () {
            if (!isActive() && !isInlineVisible()) { stopKeepalive(); return; }
            if (lastBlocks) post(lastBlocks);
        }, KEEPALIVE_MS);
    }

    function stopKeepalive() {
        if (keepaliveTimer) { clearInterval(keepaliveTimer); keepaliveTimer = null; }
    }

    function open(blocks) {
        var config = window.CMS_ROUTE_EDITOR || {};
        if (!config.pageId) { alert('Save the page first before previewing.'); return; }
        var previewUrl = getPreviewUrl();
        if (!previewUrl) { alert('Preview URL is not configured correctly.'); return; }
        setActive(true);
        window.open(previewUrl, '_blank');
        post(blocks);
    }

    // --- Inline preview ---

    function isInlineVisible() {
        var wrapper = document.getElementById('cms-inline-preview');
        return wrapper ? wrapper.classList.contains('is-active') : false;
    }

    function toggleInline(blocks) {
        var wrapper = document.getElementById('cms-inline-preview');
        if (!wrapper) return;
        var showing = !wrapper.classList.contains('is-active');
        wrapper.classList.toggle('is-active', showing);

        var toggleBtn = document.querySelector('.cms-inline-preview-toggle');
        if (toggleBtn) toggleBtn.classList.toggle('is-active', showing);

        if (showing) {
            setActive(true);
            if (!inlineLoaded) {
                var iframe = document.getElementById('cms-preview-iframe');
                var previewUrl = getPreviewUrl();
                if (iframe && previewUrl) iframe.src = previewUrl;
                inlineLoaded = true;
            }
            post(blocks);
        }
    }

    function refreshInline() {
        var iframe = document.getElementById('cms-preview-iframe');
        if (!iframe) return;
        var url = getPreviewUrl();
        if (url) iframe.src = url;
    }

    function setDevice(device) {
        var wrap = document.getElementById('cms-preview-iframe-wrap');
        if (!wrap) return;
        wrap.className = 'cms-preview-iframe-wrap cms-preview-device-' + device;
        document.querySelectorAll('.cms-preview-device-btn').forEach(function (btn) {
            btn.classList.toggle('is-active', btn.getAttribute('data-device') === device);
        });
    }

    window.ITGCmsBlockLivePreview = { isActive: isActive, setActive: setActive, post: post, open: open, toggleInline: toggleInline, refreshInline: refreshInline, setDevice: setDevice, isInlineVisible: isInlineVisible };
})();
