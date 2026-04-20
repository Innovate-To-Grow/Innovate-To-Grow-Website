(function () {
    const SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;

    const config = window.CMS_EMBED_WIDGET || {};
    let selected = new Set((config.initialBlockSortOrders || []).map(Number));

    function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    }

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
        if (!blocks.length) {
            container.innerHTML = '<p class="cms-widget-empty">This page has no blocks yet.</p>';
            return;
        }
        container.innerHTML = blocks.map(b => {
            const order = Number(b.sort_order);
            const id = 'cms-widget-block-cb-' + order;
            const label = escapeHtml(b.admin_label || '');
            const checked = selected.has(order) ? ' checked' : '';
            return '<div class="cms-widget-block-row">'
                + '<input type="checkbox" id="' + id + '" data-order="' + order + '"' + checked + '>'
                + '<label for="' + id + '">'
                + '<span class="cms-widget-block-order">#' + (order + 1) + '</span>'
                + '<span class="cms-widget-block-type">' + escapeHtml(b.block_type) + '</span>'
                + (label ? ' — ' + label : '')
                + '</label>'
                + '</div>';
        }).join('');
        container.querySelectorAll('input[type=checkbox]').forEach(cb => {
            cb.addEventListener('change', () => {
                const order = Number(cb.dataset.order);
                if (cb.checked) selected.add(order); else selected.delete(order);
                syncHidden();
                renderSnippet();
            });
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

    function previewSection() { return document.getElementById('cms-widget-preview-section'); }
    function previewIframe() { return document.getElementById('cms-widget-preview-iframe'); }
    function previewContainer() { return document.getElementById('cms-widget-preview-container'); }

    function hidePreview() {
        const sec = previewSection();
        if (sec) sec.style.display = 'none';
        currentPreviewUrl = '';
    }

    function showPreview(embedUrl) {
        const sec = previewSection();
        const iframe = previewIframe();
        if (!sec || !iframe) return;

        sec.style.display = '';

        if (embedUrl === currentPreviewUrl) return;
        currentPreviewUrl = embedUrl;

        clearTimeout(previewDebounce);
        previewDebounce = setTimeout(function () {
            iframe.src = embedUrl;
        }, 400);
    }

    function refreshPreview() {
        const iframe = previewIframe();
        if (!iframe || !currentPreviewUrl) return;
        iframe.src = '';
        setTimeout(function () { iframe.src = currentPreviewUrl; }, 50);
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

        window.addEventListener('message', function (e) {
            if (!e.data || e.data.type !== 'i2g-embed-resize') return;
            var iframe = previewIframe();
            if (iframe && e.data.height) {
                iframe.style.height = e.data.height + 'px';
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
        fetchBlocks(p ? p.value : config.initialPageId);
        renderSnippet();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
