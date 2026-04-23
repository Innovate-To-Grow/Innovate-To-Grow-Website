// Shared foundation for the CMS Embed Widget admin scripts.
// Defines window.CMSEmbedAdmin with: constants, config, mutable state,
// field accessors, and URL/text utilities. Must be loaded before the
// other cms-embed-widget/*.js modules.
window.CMSEmbedAdmin = window.CMSEmbedAdmin || {};
(function (ns) {
    ns.SLUG_RE = /^[a-z0-9][a-z0-9-]*$/;
    ns.WIDGET_TYPE_BLOCKS = 'blocks';
    ns.WIDGET_TYPE_APP_ROUTE = 'app_route';

    ns.config = window.CMS_EMBED_WIDGET || {};

    ns.state = {
        selected: new Set((ns.config.initialBlockSortOrders || []).map(Number)),
        currentWidgetType: ns.config.initialWidgetType || ns.WIDGET_TYPE_BLOCKS,
        // Track whether slug/label were auto-filled from a page or app route.
        // Once the user types into either field, we stop overwriting it on
        // subsequent route/page changes so custom values are preserved. Starts
        // false so saved widgets (populated from the DB) are treated as user-owned.
        slugAutofilled: false,
        labelAutofilled: false,
        currentAppRoute: '',
        currentPreviewUrl: '',
        currentPageRoute: '',
        previewDebounce: null,
    };

    ns.fields = {
        hidden: function () { return document.getElementById('id_block_sort_orders'); },
        slug: function () { return document.getElementById('id_slug'); },
        page: function () { return document.getElementById('id_page'); },
        widgetType: function () { return document.getElementById('id_widget_type'); },
        appRoute: function () { return document.getElementById('id_app_route'); },
        label: function () { return document.getElementById('id_admin_label'); },
        snippet: function () { return document.getElementById('cms-widget-snippet'); },
        url: function () { return document.getElementById('cms-widget-embed-url'); },
        link: function () { return document.getElementById('cms-widget-embed-link'); },
        hint: function () { return document.getElementById('cms-widget-hint'); },
        picker: function () { return document.getElementById('cms-widget-block-picker'); },
    };

    // Resolve the frontend origin once at module load. Used by the preview
    // postMessage listener to reject messages from any other window.
    ns.FRONTEND_ORIGIN = (function () {
        try {
            return ns.config.frontendUrl ? new URL(ns.config.frontendUrl).origin : '';
        } catch (e) {
            return '';
        }
    })();

    // Return `url` unchanged if it's an http(s) URL; empty string otherwise.
    // Guards iframe.src assignments so a crafted slug/route can't produce a
    // javascript: or data: URL that executes in the admin context. The slug
    // validator upstream rejects such inputs, but defense-in-depth at the
    // sink keeps CodeQL's taint analysis happy and protects future edits.
    ns.safeHttpUrl = function (url) {
        try {
            var u = new URL(url, window.location.href);
            return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '';
        } catch (e) {
            return '';
        }
    };

    ns.toKebab = function (str) {
        return String(str).toLowerCase()
            .replace(/[^a-z0-9\s-]/g, '')
            .replace(/[\s_]+/g, '-')
            .replace(/-+/g, '-')
            .replace(/^-|-$/g, '');
    };
})(window.CMSEmbedAdmin);
