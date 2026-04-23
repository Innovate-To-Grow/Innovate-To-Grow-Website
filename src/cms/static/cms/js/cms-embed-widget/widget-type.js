// Widget-type toggle (blocks vs app_route) and the app_route form binding.
// Controls which fields and preview sections are shown, and autofills
// slug/admin_label from the selected app route (honoring ns.state autofill
// flags so user-customized values aren't overwritten).
(function (ns) {
    var state = ns.state;
    var fields = ns.fields;
    var toKebab = ns.toKebab;
    var BLOCKS = ns.WIDGET_TYPE_BLOCKS;
    var APP_ROUTE = ns.WIDGET_TYPE_APP_ROUTE;

    function setFormRowVisibility(inputId, visible) {
        var f = document.getElementById(inputId);
        if (!f) return;
        var row = f.closest('.form-row, .field-box, .form-group') || f.parentElement;
        if (row) row.style.display = visible ? '' : 'none';
    }

    ns.applyWidgetTypeVisibility = function () {
        var isAppRoute = state.currentWidgetType === APP_ROUTE;
        setFormRowVisibility('id_page', !isAppRoute);
        setFormRowVisibility('id_app_route', isAppRoute);

        document.querySelectorAll('.cms-widget-blocks-only').forEach(function (el) {
            el.style.display = isAppRoute ? 'none' : '';
        });
        document.querySelectorAll('.cms-widget-app-route-only').forEach(function (el) {
            el.style.display = isAppRoute ? '' : 'none';
        });

        if (isAppRoute) {
            ns.hidePreview();
            ns.hidePagePreview();
            var route = String((fields.appRoute() || {}).value || '').trim();
            ns.showAppRoutePreview(route);
        } else {
            ns.hideAppRoutePreview();
        }
        ns.renderSnippet();
    };

    ns.bindWidgetType = function () {
        var sel = fields.widgetType();
        if (!sel) return;
        function handler() {
            state.currentWidgetType = sel.value || BLOCKS;
            ns.applyWidgetTypeVisibility();
        }
        if (window.django && window.django.jQuery) {
            window.django.jQuery(sel).on('change', handler);
        } else {
            sel.addEventListener('change', handler);
        }
    };

    function prefillFromAppRoute(route) {
        if (!route) return;
        var slug = fields.slug();
        var label = fields.label();
        var routeChoice = Array.prototype.find.call(
            (fields.appRoute() || { options: [] }).options || [],
            function (opt) { return opt.value === route; },
        );
        var title = routeChoice
            ? String(routeChoice.textContent || '').replace(/\s*\(.*\)\s*$/, '').trim()
            : '';
        var base = toKebab(route.replace(/^\/+|\/+$/g, ''));
        var nextSlug = base ? base + '-widget' : '';
        // Regenerate slug/label when the field is empty OR when it still holds
        // a value we autofilled earlier — so switching routes updates them.
        // Leave alone once the user types their own value.
        if (slug && nextSlug && (!slug.value || state.slugAutofilled)) {
            slug.value = nextSlug;
            state.slugAutofilled = true;
        }
        if (label && title && (!label.value || state.labelAutofilled)) {
            label.value = title;
            state.labelAutofilled = true;
        }
    }

    ns.bindAppRoute = function () {
        var sel = fields.appRoute();
        if (!sel) return;
        function handler() {
            var route = String(sel.value || '').trim();
            if (route) {
                prefillFromAppRoute(route);
                ns.showAppRoutePreview(route);
            } else {
                ns.hideAppRoutePreview();
            }
            ns.renderSnippet();
        }
        if (window.django && window.django.jQuery) {
            window.django.jQuery(sel).on('change', handler);
        } else {
            sel.addEventListener('change', handler);
        }
    };
})(window.CMSEmbedAdmin);
