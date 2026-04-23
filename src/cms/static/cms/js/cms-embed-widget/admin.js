// Embed URL & snippet rendering, slug/copy bindings, and module entry point.
// Depends on core.js + previews.js + blocks.js + widget-type.js being loaded
// before this file (see change_form.html).
(function (ns) {
    var state = ns.state;
    var cfg = ns.config;
    var fields = ns.fields;

    ns.renderSnippet = function () {
        var slug = String((fields.slug() || {}).value || '').trim().toLowerCase();
        var frontend = cfg.frontendUrl || '';
        var slugValid = !!slug && ns.SLUG_RE.test(slug);
        var hint = fields.hint();
        hint.style.display = 'none';
        hint.textContent = '';

        if (!slugValid) {
            fields.url().textContent = '(invalid slug)';
            fields.link().style.display = 'none';
            fields.snippet().value = '';
            ns.hidePreview();
            if (slug) {
                hint.textContent = 'Slug must be kebab-case: lowercase, digits, hyphens.';
                hint.style.display = '';
            }
            return;
        }
        if (state.currentWidgetType === ns.WIDGET_TYPE_BLOCKS && !state.selected.size) {
            fields.url().textContent = '(select at least one block)';
            fields.link().style.display = 'none';
            fields.snippet().value = '';
            ns.hidePreview();
            return;
        }
        if (state.currentWidgetType === ns.WIDGET_TYPE_APP_ROUTE) {
            var route = String((fields.appRoute() || {}).value || '').trim();
            if (!route) {
                fields.url().textContent = '(select an app route)';
                fields.link().style.display = 'none';
                fields.snippet().value = '';
                ns.hidePreview();
                return;
            }
        }
        if (!frontend) {
            fields.url().textContent = '(FRONTEND_URL not configured)';
            fields.link().style.display = 'none';
            fields.snippet().value = '';
            ns.hidePreview();
            hint.textContent = 'FRONTEND_URL is not configured — snippet preview unavailable.';
            hint.style.display = '';
            return;
        }

        var embedUrl = frontend + '/_embed/' + slug;
        fields.url().textContent = embedUrl;
        var link = fields.link();
        link.href = embedUrl;
        link.style.display = '';
        fields.snippet().value = window.ITGEmbedSnippet.buildEmbedSnippet(embedUrl, slug);
        if (state.currentWidgetType === ns.WIDGET_TYPE_APP_ROUTE) {
            // App route widgets have a dedicated standalone preview section.
            // Skip the Live Preview (/_embed/<slug>/) iframe to avoid a duplicate
            // — and because it would 404 before the widget is saved.
            ns.hidePreview();
        } else {
            ns.showPreview(embedUrl);
        }
    };

    function bindSlug() {
        var s = fields.slug();
        if (!s) return;
        s.addEventListener('input', function () {
            // User typed — stop auto-overwriting on subsequent route changes.
            state.slugAutofilled = false;
            ns.renderSnippet();
        });
        var label = fields.label();
        if (label) {
            label.addEventListener('input', function () { state.labelAutofilled = false; });
        }
    }

    function bindCopy() {
        var btn = document.getElementById('cms-widget-copy-btn');
        if (!btn) return;
        btn.addEventListener('click', function () {
            var ta = fields.snippet();
            if (!ta || !ta.value) return;
            ta.select();
            var ok = false;
            try {
                if (navigator.clipboard && window.isSecureContext) {
                    navigator.clipboard.writeText(ta.value);
                    ok = true;
                } else {
                    ok = document.execCommand('copy');
                }
            } catch (e) { ok = false; }
            var orig = btn.textContent;
            btn.textContent = ok ? 'Copied!' : 'Copy failed';
            setTimeout(function () { btn.textContent = orig; }, 1500);
        });
    }

    function init() {
        ns.syncHidden();
        bindSlug();
        ns.bindPageChange();
        ns.bindWidgetType();
        ns.bindAppRoute();
        bindCopy();
        ns.bindPreview();
        var sel = fields.widgetType();
        state.currentWidgetType = (sel && sel.value) || state.currentWidgetType;
        var p = fields.page();
        var initialId = p ? p.value : cfg.initialPageId;
        if (state.currentWidgetType !== ns.WIDGET_TYPE_APP_ROUTE) {
            ns.fetchBlocks(initialId);
            ns.fetchPageRouteAndShowPreview(initialId);
        }
        ns.applyWidgetTypeVisibility();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})(window.CMSEmbedAdmin);
