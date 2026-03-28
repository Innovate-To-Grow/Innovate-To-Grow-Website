(function () {
    const iframe = document.getElementById('menu-preview-iframe');
    const renderApi = window.ITGMenuEditorRender;
    const routes = {
        appRoutes: window.APP_ROUTES || [],
        cmsRoutes: window.CMS_ROUTES || [],
        allRoutes: [...(window.APP_ROUTES || []), ...(window.CMS_ROUTES || [])],
    };
    let jsonInput = document.getElementById('id_items') || document.querySelector('textarea[name="items"]');
    let menuItems = [];

    function init() {
        if (jsonInput) {
            try { menuItems = Array.isArray(JSON.parse(jsonInput.value || '[]')) ? JSON.parse(jsonInput.value || '[]') : []; }
            catch (e) { console.error('Failed to parse initial JSON:', e); menuItems = []; }
        }
        renderAll();
        updatePreview();
    }

    function renderAll() { renderApi.renderAll(document.getElementById('menu-items-container'), document.getElementById('json-editor'), menuItems, routes); }
    function updatePreview() { renderApi.updatePreview(iframe, menuItems); }
    function syncToJson() { if (jsonInput) jsonInput.value = JSON.stringify(menuItems); document.getElementById('json-editor').value = JSON.stringify(menuItems, null, 2); updatePreview(); }
    function getItemByPath(path) { return eval(path); }
    function setItemProperty(path, property, value) { eval(`${path}.${property} = ${JSON.stringify(value)}`); }

    window.addMenuItem = function (type) {
        menuItems.push({ type, title: type === 'home' ? 'Home' : type === 'app' ? 'New App Link' : 'New External Link', url: type === 'home' ? '/' : '', icon: '', open_in_new_tab: type === 'external', children: [] });
        renderAll();
        syncToJson();
    };

    window.addChildItem = function (parentPath) {
        const parent = getItemByPath(parentPath);
        if (!parent.children) parent.children = [];
        parent.children.push({ type: 'external', title: 'New Child Link', url: '', icon: '', open_in_new_tab: false, children: [] });
        renderAll();
        syncToJson();
    };

    window.selectAppRoute = function (path, url) {
        const item = getItemByPath(path);
        item.url = url;
        const route = routes.allRoutes.find(entry => entry.url === url);
        if (route) {
            if (!item.title || item.title === 'New App Link') item.title = route.title;
            if (!item.icon) item.icon = route.icon;
        }
        renderAll();
        syncToJson();
    };

    window.updateItem = function (path, property, value) { setItemProperty(path, property, value); renderAll(); syncToJson(); };
    window.changeItemType = function (path, newType) {
        const item = getItemByPath(path);
        if (item.type === newType) return;
        item.type = newType;
        delete item.page_slug;
        delete item.homepage_page;
        item.url = newType === 'home' ? '/' : item.url || '';
        item.open_in_new_tab = newType === 'external';
        if (newType === 'home' && (!item.title || item.title === 'New External Link' || item.title === 'New App Link')) item.title = 'Home';
        renderAll();
        syncToJson();
    };

    window.removeItem = function (path) {
        const match = path.match(/(.+)\[(\d+)]$/);
        if (!match) return;
        eval(match[1]).splice(parseInt(match[2], 10), 1);
        renderAll();
        syncToJson();
    };

    window.moveItem = function (path, direction) {
        const match = path.match(/(.+)\[(\d+)]$/);
        if (!match) return;
        const parent = eval(match[1]);
        const index = parseInt(match[2], 10);
        const nextIndex = index + direction;
        if (nextIndex < 0 || nextIndex >= parent.length) return;
        parent.splice(nextIndex, 0, parent.splice(index, 1)[0]);
        renderAll();
        syncToJson();
    };

    window.toggleJsonView = function () { document.getElementById('json-raw-view').classList.toggle('show'); };
    window.copyJson = function () {
        const editor = document.getElementById('json-editor');
        const btn = event && event.target;
        editor.select();
        try { navigator.clipboard && window.isSecureContext ? navigator.clipboard.writeText(editor.value) : document.execCommand('copy'); }
        catch (e) {}
        if (!btn) return;
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy JSON'; }, 1200);
    };

    window.applyJson = function () {
        const editor = document.getElementById('json-editor');
        const btn = event && event.target;
        try {
            const parsed = JSON.parse(editor.value.trim() || '[]');
            if (!Array.isArray(parsed)) throw new Error('must be a JSON array');
            menuItems = parsed;
            renderAll();
            syncToJson();
            if (btn) { btn.textContent = 'Applied!'; setTimeout(() => { btn.textContent = 'Apply JSON'; }, 1200); }
        } catch (e) {
            if (!btn) return;
            btn.textContent = e.message === 'must be a JSON array' ? 'Error: must be a JSON array' : 'Invalid JSON';
            btn.style.color = '#dc3545';
            setTimeout(() => { btn.textContent = 'Apply JSON'; btn.style.color = ''; }, 2000);
        }
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
