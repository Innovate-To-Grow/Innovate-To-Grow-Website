// Block picker and CMS-page-related logic for the CMS Embed Widget admin.
// Renders block checkboxes, syncs the hidden block_sort_orders input, and
// autofills slug/admin_label from the selected page (honoring the autofill
// flags in ns.state so user-customized values aren't overwritten).
(function (ns) {
    var state = ns.state;
    var cfg = ns.config;
    var fields = ns.fields;
    var toKebab = ns.toKebab;

    ns.syncHidden = function () {
        var h = fields.hidden();
        if (h) h.value = JSON.stringify(Array.from(state.selected).sort(function (a, b) { return a - b; }));
    };

    function renderBlocks(blocks) {
        var container = fields.picker();
        if (!container) return;
        // Use DOM APIs instead of innerHTML so user-controlled block labels
        // are never reinterpreted as HTML even if an upstream sanitizer is
        // bypassed. CodeQL's taint analysis treats innerHTML = <string> as
        // unsafe regardless of manual escaping.
        while (container.firstChild) container.removeChild(container.firstChild);
        if (!blocks.length) {
            var empty = document.createElement('p');
            empty.className = 'cms-widget-empty';
            empty.textContent = 'This page has no blocks yet.';
            container.appendChild(empty);
            return;
        }
        blocks.forEach(function (b) {
            var order = Number(b.sort_order);
            var id = 'cms-widget-block-cb-' + order;
            var row = document.createElement('div');
            row.className = 'cms-widget-block-row';

            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.id = id;
            cb.dataset.order = String(order);
            cb.checked = state.selected.has(order);
            cb.addEventListener('change', function () {
                if (cb.checked) state.selected.add(order); else state.selected.delete(order);
                ns.syncHidden();
                ns.renderSnippet();
            });

            var label = document.createElement('label');
            label.htmlFor = id;

            var orderSpan = document.createElement('span');
            orderSpan.className = 'cms-widget-block-order';
            orderSpan.textContent = '#' + (order + 1);

            var typeSpan = document.createElement('span');
            typeSpan.className = 'cms-widget-block-type';
            typeSpan.textContent = String(b.block_type || '');

            label.appendChild(orderSpan);
            label.appendChild(typeSpan);

            var adminLabel = String(b.admin_label || '');
            if (adminLabel) {
                label.appendChild(document.createTextNode(' — ' + adminLabel));
            }

            row.appendChild(cb);
            row.appendChild(label);
            container.appendChild(row);
        });
    }

    ns.fetchBlocks = function (pageId) {
        if (!pageId) {
            renderBlocks([]);
            return;
        }
        var url = cfg.pageBlocksUrl + '?page_id=' + encodeURIComponent(pageId);
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : { blocks: [] }; })
            .then(function (data) {
                var blocks = (data && data.blocks) || [];
                var validOrders = new Set(blocks.map(function (b) { return Number(b.sort_order); }));
                state.selected = new Set(Array.from(state.selected).filter(function (o) { return validOrders.has(o); }));
                ns.syncHidden();
                renderBlocks(blocks);
                ns.renderSnippet();
            })
            .catch(function () { renderBlocks([]); });
    };

    function prefillFromPage(pageId) {
        if (!pageId || !cfg.pageInfoUrl) return;
        var slug = fields.slug();
        var label = fields.label();

        var url = cfg.pageInfoUrl + '?page_id=' + encodeURIComponent(pageId);
        fetch(url, { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : {}; })
            .then(function (data) {
                if (!data.title) return;
                if (slug && (!slug.value || state.slugAutofilled)) {
                    var route = (data.route || '').replace(/^\/|\/$/g, '');
                    var base = route ? toKebab(route) : toKebab(data.title);
                    if (base) {
                        slug.value = base + '-widget';
                        state.slugAutofilled = true;
                        ns.renderSnippet();
                    }
                }
                if (label && (!label.value || state.labelAutofilled)) {
                    label.value = data.title;
                    state.labelAutofilled = true;
                }
            })
            .catch(function () {});
    }

    function onPageChange(newId) {
        if (newId !== cfg.initialPageId) {
            state.selected = new Set();
            ns.syncHidden();
        }
        ns.fetchBlocks(newId);
        prefillFromPage(newId);
        ns.fetchPageRouteAndShowPreview(newId);
    }

    ns.bindPageChange = function () {
        var p = fields.page();
        if (!p) return;
        function handler() { onPageChange(p.value); }
        if (window.django && window.django.jQuery) {
            window.django.jQuery(p).on('change', handler);
        } else {
            p.addEventListener('change', handler);
        }
    };
})(window.CMSEmbedAdmin);
