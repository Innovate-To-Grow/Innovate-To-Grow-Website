(function () {
    function getLivePreviewKey() {
        const config = window.CMS_ROUTE_EDITOR || {};
        return config.pageId ? 'cms_live_preview_active_' + config.pageId : '';
    }

    function isActive() { const key = getLivePreviewKey(); return key ? sessionStorage.getItem(key) === 'true' : false; }
    function setActive(active) { const key = getLivePreviewKey(); if (!key) return; active ? sessionStorage.setItem(key, 'true') : sessionStorage.removeItem(key); }

    function gatherPageData(blocks) {
        const routeEl = document.getElementById('id_route');
        const titleEl = document.getElementById('id_title');
        const slugEl = document.getElementById('id_slug');
        const cssClassEl = document.getElementById('id_page_css_class');
        const metaDescEl = document.getElementById('id_meta_description');
        return { slug: slugEl ? slugEl.value : '', route: routeEl ? routeEl.value : (window.CMS_ROUTE_EDITOR && window.CMS_ROUTE_EDITOR.pageRoute) || '/', title: titleEl ? titleEl.value : '', page_css_class: cssClassEl ? cssClassEl.value : '', meta_description: metaDescEl ? metaDescEl.value : '', blocks: blocks.map((block, index) => ({ block_type: block.block_type, sort_order: index, data: block.data })) };
    }

    function post(blocks, callback) {
        const config = window.CMS_ROUTE_EDITOR || {};
        if (!config.pageId) return;
        const csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
        fetch('/cms/live-preview/' + config.pageId + '/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfEl ? csrfEl.value : '' },
            body: JSON.stringify(gatherPageData(blocks)),
            credentials: 'same-origin',
        }).then(response => { if (!response.ok) console.warn('[CMS Preview] POST failed with status ' + response.status); else if (callback) callback(); }).catch(err => console.warn('[CMS Preview] Network error:', err.message || err));
    }

    function open(blocks) {
        const config = window.CMS_ROUTE_EDITOR || {};
        if (!config.pageId) { alert('Save the page first before previewing.'); return; }
        setActive(true);
        let route = gatherPageData(blocks).route || '/';
        if (route.charAt(0) !== '/') route = '/' + route;
        const base = (config.frontendUrl || '').replace(/\/+$/, '') || window.location.origin;
        window.open(base + route + '?cms_live_preview=' + config.pageId, '_blank');
        post(blocks);
    }

    window.ITGCmsBlockLivePreview = { isActive, setActive, post, open };
})();
