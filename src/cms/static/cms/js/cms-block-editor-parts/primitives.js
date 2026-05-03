(function () {
    const BLOCK_SCHEMAS = window.CMS_BLOCK_SCHEMAS || {};
    const BLOCK_TYPE_CHOICES = window.CMS_BLOCK_TYPE_CHOICES || [];
    const PROTOTYPE_POLLUTION_KEYS = new Set(['__proto__', 'prototype', 'constructor']);

    function escapeHtml(val) {
        const div = document.createElement('div');
        div.textContent = val || '';
        return div.innerHTML;
    }

    function escapeAttr(val) {
        return String(val || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function getTypeLabel(type) {
        for (let i = 0; i < BLOCK_TYPE_CHOICES.length; i++) if (BLOCK_TYPE_CHOICES[i][0] === type) return BLOCK_TYPE_CHOICES[i][1];
        return type;
    }

    function getDefaultData(blockType) {
        const schema = BLOCK_SCHEMAS[blockType];
        if (!schema) return {};
        const data = {};
        schema.required.forEach(field => { data[field] = ['items', 'sections', 'columns', 'rows', 'proposals', 'sponsors'].includes(field) ? [] : ''; });
        if (blockType === 'embed') {
            data.sandbox = window.CMS_EMBED_DEFAULT_SANDBOX || 'allow-scripts allow-same-origin allow-forms allow-popups';
            data.aspect_ratio = '16:9';
            data.allowfullscreen = true;
        }
        if (blockType === 'embed_widget') {
            data.aspect_ratio = '';
            data.hide_section_titles = false;
        }
        return data;
    }

    function textField(label, value, blockIdx, dataPath) { return `<div class="cms-block-field"><label>${escapeHtml(label)}</label><input type="text" value="${escapeAttr(value)}" oninput="updateBlockData(${blockIdx}, '${dataPath}', this.value)"></div>`; }
    function textFieldDirect(label, value, blockIdx, dataPath) { return `<div class="cms-block-field"><label>${escapeHtml(label)}</label><input type="text" value="${escapeAttr(value)}" oninput="updateBlockDataDirect(${blockIdx}, '${dataPath}', this.value)"></div>`; }
    function htmlField(label, value, blockIdx, dataPath) { return `<div class="cms-block-field"><label>${escapeHtml(label)}</label><textarea class="html-field" oninput="updateBlockData(${blockIdx}, '${dataPath}', this.value)">${escapeHtml(value || '')}</textarea><span class="field-hint">Supports HTML markup</span></div>`; }
    function selectField(label, value, blockIdx, dataPath, options) { return `<div class="cms-block-field field-small"><label>${escapeHtml(label)}</label><select onchange="updateBlockData(${blockIdx}, '${dataPath}', this.value)">${options.map(opt => `<option value="${escapeAttr(opt[0])}"${String(value) === String(opt[0]) ? ' selected' : ''}>${escapeHtml(opt[1])}</option>`).join('')}</select></div>`; }
    function checkboxField(label, value, blockIdx, dataPath) { const id = 'cb-' + blockIdx + '-' + dataPath.replace(/\./g, '-'); return `<div class="cms-block-field-checkbox"><input type="checkbox" id="${id}"${value ? ' checked' : ''} onchange="updateBlockData(${blockIdx}, '${dataPath}', this.checked)"><label for="${id}">${escapeHtml(label)}</label></div>`; }
    function renderJsonSubEditor(data, blockIdx, fieldName, label) { return `<div class="cms-json-subeditor"><div class="cms-block-field"><label>${escapeHtml(label || 'Data (JSON)')}</label><textarea oninput="updateBlockDataJson(${blockIdx}, '${fieldName || ''}', this.value)">${escapeHtml(JSON.stringify(fieldName ? data[fieldName] : data, null, 2))}</textarea></div></div>`; }

    function renderRepeater(label, items, blockIdx, fieldName, renderItem) {
        const itemsHtml = !items.length ? '<p style="color:#999; font-style:italic; font-size:13px;">No items yet.</p>' : items.map((item, itemIdx) => {
            let itemActions = '';
            if (itemIdx > 0) itemActions += `<button type="button" onclick="moveRepeaterItem(${blockIdx}, '${fieldName}', ${itemIdx}, -1)">&uarr;</button>`;
            if (itemIdx < items.length - 1) itemActions += `<button type="button" onclick="moveRepeaterItem(${blockIdx}, '${fieldName}', ${itemIdx}, 1)">&darr;</button>`;
            itemActions += `<button type="button" class="btn-repeater-delete" onclick="removeRepeaterItem(${blockIdx}, '${fieldName}', ${itemIdx})">&times;</button>`;
            return `<div class="cms-repeater-item"><div class="cms-repeater-item-header"><span class="cms-repeater-item-number">Item ${itemIdx + 1}</span><div class="cms-repeater-item-actions">${itemActions}</div></div>${renderItem(item, itemIdx)}</div>`;
        }).join('');
        return `<div class="cms-repeater"><div class="cms-repeater-header"><label>${escapeHtml(label)}</label></div><div class="cms-repeater-items">${itemsHtml}</div><button type="button" class="btn-repeater-add" onclick="addRepeaterItem(${blockIdx}, '${fieldName}')">+ Add ${escapeHtml(label.replace(/s$/, ''))}</button></div>`;
    }

    function isSafePathPart(part) {
        return part !== '' && !PROTOTYPE_POLLUTION_KEYS.has(part);
    }

    function pathKey(part) {
        return /^\d+$/.test(part) ? parseInt(part, 10) : part;
    }

    function setNestedValue(obj, path, value) {
        if (!obj || typeof obj !== 'object' || typeof path !== 'string') return;
        const parts = path.split('.');
        if (!parts.length || !parts.every(isSafePathPart)) return;
        let current = obj;
        for (let i = 0; i < parts.length - 1; i++) {
            const key = pathKey(parts[i]);
            if (
                !Object.prototype.hasOwnProperty.call(current, key) ||
                current[key] === null ||
                typeof current[key] !== 'object'
            ) {
                current[key] = {};
            }
            current = current[key];
        }
        const lastKey = pathKey(parts[parts.length - 1]);
        current[lastKey] = value;
    }

    function getRepeaterDefault(blockType, fieldName) {
        const defaults = {
            'faq_list.items': () => ({question: '', answer_html: ''}),
            'link_list.items': () => ({label: '', url: '', description: '', is_external: false}),
            'cta_group.items': () => ({label: '', href: '', style: ''}),
            'contact_info.items': () => ({label: '', value: '', type: 'email'}),
            'section_group.sections': () => ({heading: '', heading_level: '', body_html: ''}),
            'table.columns': () => '',
            'numbered_list.items': () => '',
            'proposal_cards.proposals': () => ({type: '', title: '', organization: '', background: '', problem: '', objectives: ''}),
            'navigation_grid.items': () => ({title: '', url: '', description: '', is_external: false}),
            'sponsor_year.sponsors': () => ({name: '', logo_url: '', website: ''}),
        };
        return defaults[blockType + '.' + fieldName] ? defaults[blockType + '.' + fieldName]() : {};
    }

    window.ITGCmsBlockPrimitives = { escapeHtml, escapeAttr, getTypeLabel, getDefaultData, textField, textFieldDirect, htmlField, selectField, checkboxField, renderJsonSubEditor, renderRepeater, setNestedValue, getRepeaterDefault };
})();
