(function () {
    const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

    const config = window.CMS_EMBED_WIDGET || {};
    let selected = new Set((config.initialBlockSortOrders || []).map(Number));

    function hiddenField() { return document.getElementById('id_block_sort_orders'); }
    function slugField() { return document.getElementById('id_slug'); }
    function pageField() { return document.getElementById('id_page'); }
    function picker() { return document.getElementById('cms-widget-block-picker'); }
    function snippetEl() { return document.getElementById('cms-widget-snippet'); }
    function urlEl() { return document.getElementById('cms-widget-embed-url'); }
    function linkEl() { return document.getElementById('cms-widget-embed-link'); }
    function hintEl() { return document.getElementById('cms-widget-hint'); }

    function syncHidden() {
        const h = hiddenField();
        if (h) h.value = JSON.stringify(Array.from(selected).sort((a, b) => a - b));
    }

    function renderSnippet() {
        const slug = String((slugField() || {}).value || '').trim().toLowerCase();
        const frontend = config.frontendUrl || '';
        const slugValid = !!slug && SLUG_RE.test(slug);
        const hint = hintEl();
        hint.style.display = 'none';
        hint.textContent = '';

        if (!slugValid) {
            urlEl().textContent = '(invalid slug)';
            linkEl().style.display = 'none';
            snippetEl().value = '';
            hidePreview();
            if (slug) {
                hint.textContent = 'Slug must be kebab-case: lowercase, digits, hyphens.';
                hint.style.display = '';
            }
            return;
        }
        if (!selected.size) {
            urlEl().textContent = '(select at least one block)';
            linkEl().style.display = 'none';
            snippetEl().value = '';
            hidePreview();
            return;
        }
        if (!frontend) {
            urlEl().textContent = '(FRONTEND_URL not configured)';
            linkEl().style.display = 'none';
            snippetEl().value = '';
            hidePreview();
            hint.textContent = 'FRONTEND_URL is not configured — snippet preview unavailable.';
            hint.style.display = '';
            return;
        }

        const embedUrl = frontend + '/_embed/' + slug;
        urlEl().textContent = embedUrl;
        const link = linkEl();
        link.href = embedUrl;
        link.style.display = '';
        snippetEl().value = window.ITGEmbedSnippet.buildEmbedSnippet(embedUrl, slug);
        showPreview(embedUrl);
    }

    function renderBlocks(blocks) {
        const container = picker();
        if (!container) return;
        // Use DOM APIs instead of innerHTML so user-controlled block labels
        // are never reinterpreted as HTML even if an upstream sanitizer is
        // bypassed. CodeQL's taint analysis treats innerHTML = <string> as
        // unsafe regardless of manual escaping.
        while (container.firstChild) container.removeChild(container.firstChild);
        if (!blocks.length) {
            const empty = document.createElement('p');
            empty.className = 'cms-widget-empty';
            empty.textContent = 'This page has no blocks yet.';
            container.appendChild(empty);
            return;
        }
        blocks.forEach(b => {
            const order = Number(b.sort_order);
            const id = 'cms-widget-block-cb-' + order;
            const row = document.createElement('div');
            row.className = 'cms-widget-block-row';

            const cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.id = id;
            cb.dataset.order = String(order);
            cb.checked = selected.has(order);
            cb.addEventListener('change', () => {
                if (cb.checked) selected.add(order); else selected.delete(order);
                syncHidden();
                renderSnippet();
            });

            const label = document.createElement('label');
            label.htmlFor = id;

            const orderSpan = document.createElement('span');
            orderSpan.className = 'cms-widget-block-order';
            orderSpan.textContent = '#' + (order + 1);

            const typeSpan = document.createElement('span');
            typeSpan.className = 'cms-widget-block-type';
            typeSpan.textContent = String(b.block_type || '');

            label.appendChild(orderSpan);
            label.appendChild(typeSpan);

            const adminLabel = String(b.admin_label || '');
            if (adminLabel) {
                label.appendChild(document.createTextNode(' — ' + adminLabel));
            }

            row.appendChild(cb);
            row.appendChild(label);
            container.appendChild(row);
        });
    }

    function fetchBlocks(pageId) {
        if (!pageId) {
            renderBlocks([]);
            return;
        }
        const url = config.pageBlocksUrl + '?page_id=' + encodeURIComponent(pageId);
        fetch(url, { credentials: 'same-origin' })
            .then(r => r.ok ? r.json() : { blocks: [] })
            .then(data => {
                const blocks = (data && data.blocks) || [];
                const validOrders = new Set(blocks.map(b => Number(b.sort_order)));
                selected = new Set(Array.from(selected).filter(o => validOrders.has(o)));
                syncHidden();
                renderBlocks(blocks);
                renderSnippet();
            })
            .catch(() => renderBlocks([]));
    }

    function toKebab(str) {
        return String(str).toLowerCase()
            .replace(/[^a-z0-9\s-]/g, '')
            .replace(/[\s_]+/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '');
    }

    function prefillFromPage(pageId) {
        if (!pageId || !config.pageInfoUrl) return;
        var slug = slugField();
        var label = document.getElementById('id_admin_label');
        if ((slug && slug.value) || (label && label.value)) return;

        var url = config.pageInfoUrl + '?page_id=' + encodeURIComponent(pageId);
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (data) {
                if (!data.title) return;
                if (slug && !slug.value) {
                    var route = (data.route || '').replace(/^\/|\/$/g, '');
                    var base = route ? toKebab(route) : toKebab(data.title);
                    slug.value = base + '-widget';
                    renderSnippet();
                }
                if (label && !label.value) {
                    label.value = data.title;
                }
            })
            .catch(function () {});
    }

    function onPageChange(newId) {
        if (newId !== config.initialPageId) {
            selected = new Set();
            syncHidden();
        }
        fetchBlocks(newId);
        prefillFromPage(newId);
        fetchPageRouteAndShowPreview(newId);
    }

    function bindPageChange() {
        const p = pageField();
        if (!p) return;

        if (window.django && window.django.jQuery) {
            window.django.jQuery(p).on('change', function () {
                onPageChange(p.value);
            });
        } else {
            p.addEventListener('change', function () {
                onPageChange(p.value);
            });
        }
    }

    function bindSlug() {
        const s = slugField();
        if (s) s.addEventListener('input', renderSnippet);
    }

    let currentPreviewUrl = '';
    let previewDebounce = null;
    let currentPageRoute = '';

    // Resolve the frontend origin once at module load. Used by the preview
    // postMessage listener to reject messages from any other window.
    const FRONTEND_ORIGIN = (function () {
        try {
            return config.frontendUrl ? new URL(config.frontendUrl).origin : '';
        } catch (e) {
            return '';
        }
    })();

    // Return `url` unchanged if it's an http(s) URL; empty string otherwise.
    // Guards iframe.src assignments so a crafted slug/route can't produce a
    // javascript: or data: URL that executes in the admin context. The slug
    // validator upstream rejects such inputs, but defense-in-depth at the
    // sink keeps CodeQL's taint analysis happy and protects future edits.
    function safeHttpUrl(url) {
        try {
            const u = new URL(url, window.location.href);
            return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
        } catch (e) {
            return '';
        }
    }

    function previewSection() { return document.getElementById('cms-widget-preview-section'); }
    function previewIframe() { return document.getElementById('cms-widget-preview-iframe'); }
    function previewContainer() { return document.getElementById('cms-widget-preview-container'); }

    function pagePreviewSection() { return document.getElementById('cms-widget-page-preview-section'); }
    function pagePreviewIframe() { return document.getElementById('cms-widget-page-preview-iframe'); }
    function pagePreviewContainer() { return document.getElementById('cms-widget-page-preview-container'); }

    function hidePreview() {
        const sec = previewSection();
        if (sec) sec.style.display = 'none';
        currentPreviewUrl = '';
    }

    function showPreview(embedUrl) {
        const sec = previewSection();
        const iframe = previewIframe();
        if (!sec || !iframe) return;

        const safeUrl = safeHttpUrl(embedUrl);
        if (!safeUrl) {
            hidePreview();
            return;
        }

        sec.style.display = '';

        if (safeUrl === currentPreviewUrl) return;
        currentPreviewUrl = safeUrl;

        clearTimeout(previewDebounce);
        previewDebounce = setTimeout(function () {
            iframe.src = safeUrl;
        }, 400);
    }

    function refreshPreview() {
        const iframe = previewIframe();
        if (!iframe || !currentPreviewUrl) return;
        // currentPreviewUrl is already validated in showPreview, but re-check
        // on refresh so the sink can't be reached with a stale unsafe value
        // across re-entrancy.
        const safeUrl = safeHttpUrl(currentPreviewUrl);
        if (!safeUrl) return;
        iframe.src = '';
        setTimeout(function () { iframe.src = safeUrl; }, 50);
    }

    function showPagePreview(route) {
        var frontend = config.frontendUrl || '';
        if (!frontend || !route) {
            hidePagePreview();
            return;
        }
        var pageUrl = safeHttpUrl(frontend + route);
        if (!pageUrl) {
            hidePagePreview();
            return;
        }
        currentPageRoute = route;
        var sec = pagePreviewSection();
        var iframe = pagePreviewIframe();
        var routeLabel = document.getElementById('cms-widget-page-route-label');
        var openLink = document.getElementById('cms-widget-page-open-link');
        if (!sec || !iframe) return;

        sec.style.display = '';
        if (routeLabel) routeLabel.textContent = route;
        if (openLink) openLink.href = pageUrl;
        iframe.src = pageUrl;
    }

    function hidePagePreview() {
        var sec = pagePreviewSection();
        if (sec) sec.style.display = 'none';
        currentPageRoute = '';
    }

    function refreshPagePreview() {
        var iframe = pagePreviewIframe();
        var frontend = config.frontendUrl || '';
        if (!iframe || !currentPageRoute || !frontend) return;
        var pageUrl = safeHttpUrl(frontend + currentPageRoute);
        if (!pageUrl) return;
        iframe.src = '';
        setTimeout(function () { iframe.src = pageUrl; }, 50);
    }

    function fetchPageRouteAndShowPreview(pageId) {
        if (!pageId || !config.pageInfoUrl) {
            hidePagePreview();
            return;
        }
        var url = config.pageInfoUrl + '?page_id=' + encodeURIComponent(pageId);
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (data) {
                if (data.route) {
                    showPagePreview(data.route);
                } else {
                    hidePagePreview();
                }
            })
            .catch(function () { hidePagePreview(); });
    }

    function bindPreview() {
        var refreshBtn = document.getElementById('cms-widget-refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', refreshPreview);
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
            pageRefreshBtn.addEventListener('click', refreshPagePreview);
        }

        var pageWidthSelect = document.getElementById('cms-widget-page-preview-width');
        if (pageWidthSelect) {
            pageWidthSelect.addEventListener('change', function () {
                var container = pagePreviewContainer();
                if (container) container.style.maxWidth = pageWidthSelect.value;
            });
        }

        window.addEventListener('message', function (e) {
            // Only accept resize messages from the configured frontend origin
            // (the embed iframe's own origin). Split into two separate checks
            // so the origin allowlist is obvious to CodeQL's taint analysis
            // and to future readers.
            if (!FRONTEND_ORIGIN) return;
            if (e.origin !== FRONTEND_ORIGIN) return;
            if (!e.data || e.data.type !== 'i2g-embed-resize') return;
            var iframe = previewIframe();
            // Clamp height to a positive integer so a malformed payload
            // can't inject CSS via string concatenation.
            var height = Number(e.data.height);
            if (iframe && Number.isFinite(height) && height > 0 && height < 10000) {
                iframe.style.height = Math.floor(height) + 'px';
            }
        });
    }

    function bindCopy() {
        const btn = document.getElementById('cms-widget-copy-btn');
        if (!btn) return;
        btn.addEventListener('click', () => {
            const ta = snippetEl();
            if (!ta || !ta.value) return;
            ta.select();
            let ok = false;
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(ta.value);
                    ok = true;
                } else {
                    ok = document.execCommand('copy');
                }
            } catch (e) { ok = false; }
            const orig = btn.textContent;
            btn.textContent = ok ? 'Copied!' : 'Copy failed';
            setTimeout(() => { btn.textContent = orig; }, 1500);
        });
    }

    function init() {
        syncHidden();
        bindSlug();
        bindPageChange();
        bindCopy();
        bindPreview();
        const p = pageField();
        const initialId = p ? p.value : config.initialPageId;
        fetchBlocks(initialId);
        fetchPageRouteAndShowPreview(initialId);
        renderSnippet();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
