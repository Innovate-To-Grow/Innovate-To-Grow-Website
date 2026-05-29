(function () {
    const P = window.ITGCmsBlockPrimitives;
    const renderApi = window.ITGCmsBlockRenderers;
    const livePreviewApi = window.ITGCmsBlockLivePreview;
    let blocks = [];
    let collapsedSet = new Set();
    let previewSet = new Set();
    let livePreviewTimer = null;
    let previewRefreshTimer = null;

    function findEmbedWidget(slug) {
        const widgets = Array.isArray(window.CMS_EMBED_WIDGETS) ? window.CMS_EMBED_WIDGETS : [];
        const normalized = String(slug || '').trim().toLowerCase();
        return widgets.find(widget => widget.slug === normalized) || null;
    }

    function getEmbedWidgetHiddenSectionPresets(slug) {
        const presets = Array.isArray(window.CMS_HIDDEN_SECTION_PRESETS) ? window.CMS_HIDDEN_SECTION_PRESETS : [];
        const widget = findEmbedWidget(slug);
        return presets.filter(preset => {
            const routes = Array.isArray(preset.routes) ? preset.routes : [];
            if (!routes.length) return true;
            return widget && widget.widget_type === 'app_route' && routes.includes(widget.app_route || '');
        });
    }

    function getEmbedWidgetSelectedHiddenSections(data) {
        if (Array.isArray(data.hidden_sections)) return data.hidden_sections;
        return data.hide_section_titles ? ['section_titles'] : [];
    }

    function normalizeEmbedWidgetHiddenSections(data) {
        if (!data || typeof data !== 'object') return;
        const selected = new Set(getEmbedWidgetSelectedHiddenSections(data).map(key => String(key || '').trim()).filter(Boolean));
        const normalized = getEmbedWidgetHiddenSectionPresets(data.slug)
            .map(preset => preset.key)
            .filter(key => selected.has(key));
        data.hidden_sections = normalized;
        data.hide_section_titles = normalized.includes('section_titles');
    }

    function init() {
        try { blocks = JSON.parse(JSON.stringify(window.CMS_INITIAL_BLOCKS || [])); } catch (e) { blocks = []; }
        const select = document.getElementById('cms-add-block-type');
        if (select) (window.CMS_BLOCK_TYPE_CHOICES || []).forEach(choice => { const opt = document.createElement('option'); opt.value = choice[0]; opt.textContent = choice[1]; select.appendChild(opt); });
        if (livePreviewApi.isActive()) setTimeout(() => { livePreviewApi.post(blocks); }, 300);
        ['id_title', 'id_route', 'id_meta_description', 'id_page_css_class'].forEach(fieldId => {
            const el = document.getElementById(fieldId);
            if (el) el.addEventListener('input', scheduleLivePreviewSync);
        });
        renderAll();
        syncToJson();
    }

    function renderAll() { renderApi.renderAll(blocks, collapsedSet, previewSet); }
    function syncToJson() {
        const hidden = document.getElementById('id_blocks_json');
        if (hidden) hidden.value = JSON.stringify(blocks);
        scheduleLivePreviewSync();
        schedulePreviewRefresh();
    }
    function schedulePreviewRefresh() { if (!previewSet.size) return; if (previewRefreshTimer) clearTimeout(previewRefreshTimer); previewRefreshTimer = setTimeout(refreshAllActivePreviews, 250); }
    function refreshAllActivePreviews() { if (!window.ITGCmsBlockPreview) return; window.ITGCmsBlockPreview.refreshAllPreviews(blocks, previewSet); }
    function scheduleLivePreviewSync() { if (!livePreviewApi.isActive() && !livePreviewApi.isInlineVisible()) return; if (livePreviewTimer) clearTimeout(livePreviewTimer); livePreviewTimer = setTimeout(() => { livePreviewApi.post(blocks); }, 500); }

    window.openLivePreview = function () { livePreviewApi.open(blocks); };
    window.toggleInlinePreview = function () { livePreviewApi.toggleInline(blocks); };
    window.refreshInlinePreview = function () { livePreviewApi.refreshInline(); };
    window.setPreviewDevice = function (device) { livePreviewApi.setDevice(device); };
    window.addBlock = function () {
        const select = document.getElementById('cms-add-block-type');
        if (!select || !select.value) return;
        blocks.push({ block_type: select.value, sort_order: blocks.length, admin_label: '', data: P.getDefaultData(select.value) });
        select.value = '';
        renderAll();
        syncToJson();
        const container = document.getElementById('cms-blocks-container');
        if (container && container.lastElementChild) container.lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
    window.removeBlock = function (idx) {
        if (!confirm('Remove this block?')) return;
        blocks.splice(idx, 1);
        collapsedSet = new Set([...collapsedSet].flatMap(i => i < idx ? [i] : i > idx ? [i - 1] : []));
        previewSet = new Set([...previewSet].flatMap(i => i < idx ? [i] : i > idx ? [i - 1] : []));
        renderAll(); syncToJson();
    };
    window.moveBlock = function (idx, direction) {
        const newIdx = idx + direction;
        if (newIdx < 0 || newIdx >= blocks.length) return;
        [blocks[idx], blocks[newIdx]] = [blocks[newIdx], blocks[idx]];
        collapsedSet = new Set([...collapsedSet].map(i => i === idx ? newIdx : i === newIdx ? idx : i));
        previewSet = new Set([...previewSet].map(i => i === idx ? newIdx : i === newIdx ? idx : i));
        renderAll(); syncToJson();
    };
    window.toggleCollapse = function (idx) { collapsedSet.has(idx) ? collapsedSet.delete(idx) : collapsedSet.add(idx); renderAll(); };
    window.toggleBlockPreview = function (idx) { previewSet.has(idx) ? previewSet.delete(idx) : previewSet.add(idx); renderAll(); };
    window.updateBlockProp = function (idx, prop, value) { blocks[idx][prop] = value; renderAll(); syncToJson(); };
    window.updateBlockData = function (idx, dataPath, value) { P.setNestedValue(blocks[idx].data, dataPath, value); syncToJson(); };
    window.updateBlockDataDirect = function (idx, dataPath, value) { P.setNestedValue(blocks[idx].data, dataPath, value); syncToJson(); };
    window.updateBlockDataJson = function (idx, fieldName, jsonStr) { try { const parsed = JSON.parse(jsonStr); if (fieldName) blocks[idx].data[fieldName] = parsed; else blocks[idx].data = parsed; syncToJson(); } catch (e) {} };
    window.updateEmbedWidgetSlug = function (idx, value) { blocks[idx].data.slug = value; normalizeEmbedWidgetHiddenSections(blocks[idx].data); renderAll(); syncToJson(); };
    window.updateEmbedWidgetHiddenSection = function (idx, key, checked) {
        const data = blocks[idx].data;
        const selected = new Set(getEmbedWidgetSelectedHiddenSections(data).map(item => String(item || '').trim()).filter(Boolean));
        if (checked) selected.add(key);
        else selected.delete(key);
        data.hidden_sections = Array.from(selected);
        normalizeEmbedWidgetHiddenSections(data);
        syncToJson();
    };
    window.getEmbedWidgetHiddenSectionPresets = getEmbedWidgetHiddenSectionPresets;
    window.getEmbedWidgetSelectedHiddenSections = getEmbedWidgetSelectedHiddenSections;
    window.addRepeaterItem = function (blockIdx, fieldName) { const data = blocks[blockIdx].data; if (!data[fieldName]) data[fieldName] = []; data[fieldName].push(P.getRepeaterDefault(blocks[blockIdx].block_type, fieldName)); renderAll(); syncToJson(); };
    window.removeRepeaterItem = function (blockIdx, fieldName, itemIdx) { const arr = blocks[blockIdx].data[fieldName]; if (!arr) return; arr.splice(itemIdx, 1); renderAll(); syncToJson(); };
    window.moveRepeaterItem = function (blockIdx, fieldName, itemIdx, direction) { const arr = blocks[blockIdx].data[fieldName]; const newIdx = itemIdx + direction; if (!arr || newIdx < 0 || newIdx >= arr.length) return; [arr[itemIdx], arr[newIdx]] = [arr[newIdx], arr[itemIdx]]; renderAll(); syncToJson(); };

    window.toggleJsonView = function () { const el = document.getElementById('json-raw-view'); if (el) el.classList.toggle('show'); };
    window.copyJson = function () { const editor = document.getElementById('json-editor'); if (!editor) return; editor.select(); try { navigator.clipboard && window.isSecureContext ? navigator.clipboard.writeText(editor.value) : document.execCommand('copy'); } catch (e) {} };
    window.applyJson = function () {
        const editor = document.getElementById('json-editor');
        if (!editor || !editor.value.trim()) return;
        try {
            const parsed = JSON.parse(editor.value);
            if (!Array.isArray(parsed)) { alert('JSON must be an array of block objects.'); return; }
            blocks = parsed;
            collapsedSet.clear();
            previewSet.clear();
            renderAll();
            syncToJson();
        } catch (e) {
            alert('Invalid JSON: ' + e.message);
        }
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
