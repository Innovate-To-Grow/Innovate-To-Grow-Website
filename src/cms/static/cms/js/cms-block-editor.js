(function () {
    const P = window.ITGCmsBlockPrimitives;
    const renderApi = window.ITGCmsBlockRenderers;
    const embedsApi = window.ITGCmsEmbeds;
    const livePreviewApi = window.ITGCmsBlockLivePreview;
    let blocks = [];
    let embeds = [];
    let collapsedSet = new Set();
    let previewSet = new Set();
    let livePreviewTimer = null;
    let previewRefreshTimer = null;

    function init() {
        try { blocks = JSON.parse(JSON.stringify(window.CMS_INITIAL_BLOCKS || [])); } catch (e) { blocks = []; }
        try { embeds = JSON.parse(JSON.stringify(window.CMS_INITIAL_EMBED_CONFIGS || [])); } catch (e) { embeds = []; }
        if (!Array.isArray(embeds)) embeds = [];
        const select = document.getElementById('cms-add-block-type');
        if (select) (window.CMS_BLOCK_TYPE_CHOICES || []).forEach(choice => { const opt = document.createElement('option'); opt.value = choice[0]; opt.textContent = choice[1]; select.appendChild(opt); });
        if (livePreviewApi.isActive()) setTimeout(() => { livePreviewApi.post(blocks); }, 300);
        ['id_title', 'id_route', 'id_meta_description', 'id_page_css_class'].forEach(fieldId => {
            const el = document.getElementById(fieldId);
            if (el) el.addEventListener('input', scheduleLivePreviewSync);
        });
        renderAll();
        renderEmbeds();
        syncToJson();
    }

    function renderAll() { renderApi.renderAll(blocks, collapsedSet, previewSet); }
    function renderEmbeds() { if (embedsApi) embedsApi.renderAll(embeds, blocks); }
    function syncToJson() {
        const hidden = document.getElementById('id_blocks_json');
        if (hidden) hidden.value = JSON.stringify(blocks);
        const embedsHidden = document.getElementById('id_embed_configs_json');
        if (embedsHidden) embedsHidden.value = JSON.stringify(embeds);
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
        renderEmbeds();
        syncToJson();
        const container = document.getElementById('cms-blocks-container');
        if (container && container.lastElementChild) container.lastElementChild.scrollIntoView({ behavior: 'smooth', block: 'center' });
    };
    window.removeBlock = function (idx) {
        if (!confirm('Remove this block?')) return;
        blocks.splice(idx, 1);
        collapsedSet = new Set([...collapsedSet].flatMap(i => i < idx ? [i] : i > idx ? [i - 1] : []));
        previewSet = new Set([...previewSet].flatMap(i => i < idx ? [i] : i > idx ? [i - 1] : []));
        if (embedsApi) embeds = embedsApi.reindexAfterBlockRemove(embeds, idx);
        renderAll(); renderEmbeds(); syncToJson();
    };
    window.moveBlock = function (idx, direction) {
        const newIdx = idx + direction;
        if (newIdx < 0 || newIdx >= blocks.length) return;
        [blocks[idx], blocks[newIdx]] = [blocks[newIdx], blocks[idx]];
        collapsedSet = new Set([...collapsedSet].map(i => i === idx ? newIdx : i === newIdx ? idx : i));
        previewSet = new Set([...previewSet].map(i => i === idx ? newIdx : i === newIdx ? idx : i));
        if (embedsApi) embeds = embedsApi.reindexAfterBlockMove(embeds, idx, newIdx);
        renderAll(); renderEmbeds(); syncToJson();
    };
    window.toggleCollapse = function (idx) { collapsedSet.has(idx) ? collapsedSet.delete(idx) : collapsedSet.add(idx); renderAll(); };
    window.toggleBlockPreview = function (idx) { previewSet.has(idx) ? previewSet.delete(idx) : previewSet.add(idx); renderAll(); };
    window.updateBlockProp = function (idx, prop, value) { blocks[idx][prop] = value; renderAll(); renderEmbeds(); syncToJson(); };
    window.updateBlockData = function (idx, dataPath, value) { P.setNestedValue(blocks[idx].data, dataPath, value); syncToJson(); };
    window.updateBlockDataDirect = function (idx, dataPath, value) { P.setNestedValue(blocks[idx].data, dataPath, value); syncToJson(); };
    window.updateBlockDataJson = function (idx, fieldName, jsonStr) { try { const parsed = JSON.parse(jsonStr); if (fieldName) blocks[idx].data[fieldName] = parsed; else blocks[idx].data = parsed; syncToJson(); } catch (e) {} };
    window.addRepeaterItem = function (blockIdx, fieldName) { const data = blocks[blockIdx].data; if (!data[fieldName]) data[fieldName] = []; data[fieldName].push(P.getRepeaterDefault(blocks[blockIdx].block_type, fieldName)); renderAll(); syncToJson(); };
    window.removeRepeaterItem = function (blockIdx, fieldName, itemIdx) { const arr = blocks[blockIdx].data[fieldName]; if (!arr) return; arr.splice(itemIdx, 1); renderAll(); syncToJson(); };
    window.moveRepeaterItem = function (blockIdx, fieldName, itemIdx, direction) { const arr = blocks[blockIdx].data[fieldName]; const newIdx = itemIdx + direction; if (!arr || newIdx < 0 || newIdx >= arr.length) return; [arr[itemIdx], arr[newIdx]] = [arr[newIdx], arr[itemIdx]]; renderAll(); syncToJson(); };

    // --- Embed config handlers ---
    window.addEmbedConfig = function () {
        var embedsApi = window.ITGCmsEmbeds;
        var defaultSlug = embedsApi && embedsApi.generateDefaultSlug ? embedsApi.generateDefaultSlug(embeds) : '';
        // Pre-select every existing block so the iframe snippet is immediately
        // visible and copyable. The user can uncheck any they don't want.
        var allBlockIndices = blocks.map(function (_, i) { return i; });
        embeds.push({ slug: defaultSlug, admin_label: '', block_sort_orders: allBlockIndices });
        renderEmbeds();
        syncToJson();
    };
    window.removeEmbedConfig = function (idx) {
        if (!confirm('Remove this embed?')) return;
        embeds.splice(idx, 1);
        renderEmbeds();
        syncToJson();
    };
    window.updateEmbedSlug = function (idx, value) {
        if (!embeds[idx]) return;
        embeds[idx].slug = String(value || '').trim().toLowerCase();
        renderEmbeds();
        syncToJson();
    };
    window.updateEmbedLabel = function (idx, value) {
        if (!embeds[idx]) return;
        embeds[idx].admin_label = String(value || '');
        renderEmbeds();
        syncToJson();
    };
    window.toggleEmbedBlock = function (embedIdx, blockIdx, checked) {
        const embed = embeds[embedIdx];
        if (!embed) return;
        const orders = Array.isArray(embed.block_sort_orders) ? embed.block_sort_orders : [];
        const numIdx = Number(blockIdx);
        const set = new Set(orders);
        if (checked) set.add(numIdx); else set.delete(numIdx);
        embed.block_sort_orders = Array.from(set).sort((a, b) => a - b);
        renderEmbeds();
        syncToJson();
    };
    window.copyEmbedSnippet = function (idx) {
        const card = document.querySelector('.cms-embed-card[data-embed-index="' + idx + '"]');
        if (!card) return;
        const textarea = card.querySelector('.cms-embed-snippet');
        if (!textarea) return;
        textarea.select();
        let ok = false;
        try {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(textarea.value);
                ok = true;
            } else {
                ok = document.execCommand('copy');
            }
        } catch (e) { ok = false; }
        const btn = card.querySelector('.btn-embed-copy');
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = ok ? 'Copied!' : 'Copy failed';
            setTimeout(() => { btn.textContent = orig; }, 1500);
        }
    };

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
            renderEmbeds();
            syncToJson();
        } catch (e) {
            alert('Invalid JSON: ' + e.message);
        }
    };

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
