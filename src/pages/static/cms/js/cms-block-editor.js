/**
 * CMS Block Visual Editor
 * Handles visual editing of CMS page blocks in Django admin.
 * Follows the same pattern as the Menu/Footer visual editors.
 */
(function () {
    const BLOCK_SCHEMAS = window.CMS_BLOCK_SCHEMAS || {};
    const BLOCK_TYPE_CHOICES = window.CMS_BLOCK_TYPE_CHOICES || [];

    let blocks = [];
    let collapsedSet = new Set();
    let livePreviewActive = false;
    let livePreviewTimer = null;

    // ===== Helpers =====
    function escapeHtml(val) {
        const div = document.createElement('div');
        div.textContent = val || '';
        return div.innerHTML;
    }

    function escapeAttr(val) {
        return String(val || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function getTypeLabel(type) {
        for (var i = 0; i < BLOCK_TYPE_CHOICES.length; i++) {
            if (BLOCK_TYPE_CHOICES[i][0] === type) return BLOCK_TYPE_CHOICES[i][1];
        }
        return type;
    }

    function getDefaultData(blockType) {
        var schema = BLOCK_SCHEMAS[blockType];
        if (!schema) return {};
        var data = {};
        schema.required.forEach(function (field) {
            if (field === 'items' || field === 'sections' || field === 'columns' || field === 'rows' || field === 'proposals') {
                data[field] = [];
            } else {
                data[field] = '';
            }
        });
        return data;
    }

    // ===== Init =====
    function init() {
        try {
            blocks = JSON.parse(JSON.stringify(window.CMS_INITIAL_BLOCKS || []));
        } catch (e) {
            blocks = [];
        }

        // Populate block type dropdown
        var select = document.getElementById('cms-add-block-type');
        if (select) {
            BLOCK_TYPE_CHOICES.forEach(function (choice) {
                var opt = document.createElement('option');
                opt.value = choice[0];
                opt.textContent = choice[1];
                select.appendChild(opt);
            });
        }

        renderAll();
        syncToJson();
    }

    // ===== Render =====
    function renderAll() {
        var container = document.getElementById('cms-blocks-container');
        if (!container) return;

        if (blocks.length === 0) {
            container.innerHTML = '<p class="cms-blocks-empty">No content blocks yet. Add blocks using the dropdown below.</p>';
        } else {
            container.innerHTML = blocks.map(function (block, idx) {
                return renderBlockCard(block, idx);
            }).join('');
        }

        // Update JSON editor
        var jsonEditor = document.getElementById('json-editor');
        if (jsonEditor) {
            jsonEditor.value = JSON.stringify(blocks, null, 2);
        }

        // Enhance HTML fields with a real code editor (syntax highlighting)
        initHtmlCodeEditors(container);
    }

    function initHtmlCodeEditors(container) {
        if (!container) return;
        if (!window.CodeMirror || typeof window.CodeMirror.fromTextArea !== 'function') {
            // Fallback: just ensure reasonable height
            var fallbacks = container.querySelectorAll('textarea.html-field');
            for (var i = 0; i < fallbacks.length; i++) {
                fallbacks[i].style.minHeight = '360px';
            }
            return;
        }

        var textareas = container.querySelectorAll('textarea.html-field');
        for (var t = 0; t < textareas.length; t++) {
            var ta = textareas[t];
            if (ta._cmInstance) continue;

            var cm = window.CodeMirror.fromTextArea(ta, {
                mode: 'htmlmixed',
                lineNumbers: true,
                lineWrapping: true,
                tabSize: 2,
                indentUnit: 2,
                viewportMargin: Infinity,
            });
            ta._cmInstance = cm;

            cm.setSize(null, 380);

            // Keep existing onchange="updateBlockData(...)" behavior by updating the underlying textarea
            // and dispatching a change event.
            cm.on('change', function (instance) {
                var textarea = instance.getTextArea();
                textarea.value = instance.getValue();
                try {
                    textarea.dispatchEvent(new Event('change', {bubbles: true}));
                } catch (e) {
                    // IE11-ish fallback (unlikely, but safe)
                    var evt = document.createEvent('Event');
                    evt.initEvent('change', true, true);
                    textarea.dispatchEvent(evt);
                }
            });
        }
    }

    function renderBlockCard(block, idx) {
        var isCollapsed = collapsedSet.has(idx);
        var typeLabel = getTypeLabel(block.block_type);
        var displayLabel = block.admin_label || '';
        var collapseClass = isCollapsed ? ' is-collapsed' : '';

        // Action buttons
        var actions = '';
        if (idx > 0) actions += '<button type="button" class="btn-block-move" onclick="moveBlock(' + idx + ', -1)" title="Move up">&uarr;</button>';
        if (idx < blocks.length - 1) actions += '<button type="button" class="btn-block-move" onclick="moveBlock(' + idx + ', 1)" title="Move down">&darr;</button>';
        actions += '<button type="button" class="btn-block-delete" onclick="removeBlock(' + idx + ')" title="Delete block">&times;</button>';

        var body = '';
        if (!isCollapsed) {
            body = '<div class="cms-block-card-body">' +
                renderAdminLabel(block, idx) +
                renderBlockFields(block, idx) +
                '</div>';
        }

        return '<div class="cms-block-card' + collapseClass + '" data-index="' + idx + '">' +
            '<div class="cms-block-card-header" onclick="toggleCollapse(' + idx + ')">' +
            '<span class="cms-block-card-title">' +
            '<span class="cms-block-collapse-icon">&rsaquo;</span>' +
            '<span class="block-order">#' + (idx + 1) + '</span>' +
            '<span class="cms-block-type-badge type-' + escapeAttr(block.block_type) + '">' + escapeHtml(typeLabel) + '</span>' +
            '<span class="cms-block-label-text">' + escapeHtml(displayLabel) + '</span>' +
            '</span>' +
            '<div class="cms-block-card-actions" onclick="event.stopPropagation();">' + actions + '</div>' +
            '</div>' +
            body +
            '</div>';
    }

    function renderAdminLabel(block, idx) {
        return '<div class="cms-block-admin-label">' +
            '<label>Admin Label</label>' +
            '<input type="text" value="' + escapeAttr(block.admin_label) + '" ' +
            'placeholder="Optional label for admin identification" ' +
            'onchange="updateBlockProp(' + idx + ', \'admin_label\', this.value)">' +
            '</div>';
    }

    // ===== Per-type field renderers =====
    function renderBlockFields(block, idx) {
        var type = block.block_type;
        var data = block.data || {};
        var renderers = {
            hero: renderHeroFields,
            rich_text: renderRichTextField,
            faq_list: renderFaqListFields,
            link_list: renderLinkListFields,
            cta_group: renderCtaGroupFields,
            image_text: renderImageTextFields,
            notice: renderNoticeFields,
            contact_info: renderContactInfoFields,
            google_sheet: renderGoogleSheetFields,
            section_group: renderSectionGroupFields,
            table: renderTableFields,
            numbered_list: renderNumberedListFields,
            proposal_cards: renderProposalCardsFields,
            navigation_grid: renderNavigationGridFields,
            schedule_grid: renderScheduleGridFields,
        };

        var renderer = renderers[type];
        if (renderer) return renderer(data, idx);

        // Fallback: raw JSON editor for unknown types
        return renderJsonSubEditor(data, idx);
    }

    // ----- Hero -----
    function renderHeroFields(data, idx) {
        return textField('Heading', data.heading, idx, 'heading') +
            textField('Subheading', data.subheading, idx, 'subheading') +
            '<div class="cms-block-field-row">' +
            textField('Image URL', data.image_url, idx, 'image_url') +
            textField('Image Alt Text', data.image_alt, idx, 'image_alt') +
            '</div>';
    }

    // ----- Rich Text -----
    function renderRichTextField(data, idx) {
        return '<div class="cms-block-field-row">' +
            textField('Heading', data.heading, idx, 'heading') +
            selectField('Heading Level', data.heading_level, idx, 'heading_level', [
                ['', 'Default'], ['1', 'H1'], ['2', 'H2'], ['3', 'H3'], ['4', 'H4'], ['5', 'H5'], ['6', 'H6']
            ]) +
            '</div>' +
            htmlField('Body HTML', data.body_html, idx, 'body_html');
    }

    // ----- FAQ List -----
    function renderFaqListFields(data, idx) {
        var items = data.items || [];
        return textField('Heading', data.heading, idx, 'heading') +
            renderRepeater('FAQ Items', items, idx, 'items', function (item, itemIdx) {
                return textField('Question', item.question, idx, 'items.' + itemIdx + '.question') +
                    htmlField('Answer HTML', item.answer_html, idx, 'items.' + itemIdx + '.answer_html');
            }, function () {
                return {question: '', answer_html: ''};
            });
    }

    // ----- Link List -----
    function renderLinkListFields(data, idx) {
        var items = data.items || [];
        return '<div class="cms-block-field-row">' +
            textField('Heading', data.heading, idx, 'heading') +
            selectField('Style', data.style, idx, 'style', [
                ['list', 'List'], ['grid', 'Grid'], ['inline', 'Inline']
            ]) +
            '</div>' +
            renderRepeater('Links', items, idx, 'items', function (item, itemIdx) {
                return '<div class="cms-block-field-row">' +
                    textField('Label', item.label, idx, 'items.' + itemIdx + '.label') +
                    textField('URL', item.url, idx, 'items.' + itemIdx + '.url') +
                    '</div>' +
                    '<div class="cms-block-field-row">' +
                    textField('Description', item.description, idx, 'items.' + itemIdx + '.description') +
                    '</div>' +
                    checkboxField('External link', item.is_external, idx, 'items.' + itemIdx + '.is_external');
            }, function () {
                return {label: '', url: '', description: '', is_external: false};
            });
    }

    // ----- CTA Group -----
    function renderCtaGroupFields(data, idx) {
        var items = data.items || [];
        return renderRepeater('CTA Buttons', items, idx, 'items', function (item, itemIdx) {
            return '<div class="cms-block-field-row">' +
                textField('Label', item.label, idx, 'items.' + itemIdx + '.label') +
                textField('URL', item.href, idx, 'items.' + itemIdx + '.href') +
                textField('Style', item.style, idx, 'items.' + itemIdx + '.style') +
                '</div>';
        }, function () {
            return {label: '', href: '', style: ''};
        });
    }

    // ----- Image + Text -----
    function renderImageTextFields(data, idx) {
        return '<div class="cms-block-field-row">' +
            textField('Heading', data.heading, idx, 'heading') +
            selectField('Image Position', data.image_position, idx, 'image_position', [
                ['top', 'Top'], ['left', 'Left'], ['right', 'Right']
            ]) +
            '</div>' +
            '<div class="cms-block-field-row">' +
            textField('Image URL', data.image_url, idx, 'image_url') +
            textField('Image Alt', data.image_alt, idx, 'image_alt') +
            '</div>' +
            htmlField('Body HTML', data.body_html, idx, 'body_html');
    }

    // ----- Notice -----
    function renderNoticeFields(data, idx) {
        return '<div class="cms-block-field-row">' +
            textField('Heading', data.heading, idx, 'heading') +
            selectField('Style', data.style, idx, 'style', [
                ['info', 'Info'], ['warning', 'Warning'], ['success', 'Success']
            ]) +
            '</div>' +
            htmlField('Body HTML', data.body_html, idx, 'body_html');
    }

    // ----- Contact Info -----
    function renderContactInfoFields(data, idx) {
        var items = data.items || [];
        return textField('Heading', data.heading, idx, 'heading') +
            renderRepeater('Contacts', items, idx, 'items', function (item, itemIdx) {
                return '<div class="cms-block-field-row">' +
                    textField('Label', item.label, idx, 'items.' + itemIdx + '.label') +
                    textField('Value', item.value, idx, 'items.' + itemIdx + '.value') +
                    selectField('Type', item.type, idx, 'items.' + itemIdx + '.type', [
                        ['email', 'Email'], ['phone', 'Phone'], ['url', 'URL'], ['text', 'Text']
                    ]) +
                    '</div>';
            }, function () {
                return {label: '', value: '', type: 'email'};
            });
    }

    // ----- Google Sheet -----
    function renderGoogleSheetFields(data, idx) {
        return textField('Heading', data.heading, idx, 'heading') +
            '<div class="cms-block-field-row">' +
            textField('Sheet Source Slug', data.sheet_source_slug, idx, 'sheet_source_slug') +
            textField('Sheet View Slug', data.sheet_view_slug, idx, 'sheet_view_slug') +
            '</div>' +
            textField('Display Mode', data.display_mode, idx, 'display_mode');
    }

    // ----- Section Group -----
    function renderSectionGroupFields(data, idx) {
        var sections = data.sections || [];
        return textField('Heading', data.heading, idx, 'heading') +
            renderRepeater('Sections', sections, idx, 'sections', function (section, sIdx) {
                return '<div class="cms-block-field-row">' +
                    textField('Section Heading', section.heading, idx, 'sections.' + sIdx + '.heading') +
                    selectField('Heading Level', section.heading_level, idx, 'sections.' + sIdx + '.heading_level', [
                        ['', 'Default'], ['2', 'H2'], ['3', 'H3'], ['4', 'H4'], ['5', 'H5']
                    ]) +
                    '</div>' +
                    htmlField('Body HTML', section.body_html, idx, 'sections.' + sIdx + '.body_html');
            }, function () {
                return {heading: '', heading_level: '', body_html: ''};
            });
    }

    // ----- Table -----
    function renderTableFields(data, idx) {
        return textField('Heading', data.heading, idx, 'heading') +
            renderRepeater('Columns', data.columns || [], idx, 'columns', function (col, cIdx) {
                return textFieldDirect('Column Name', col, idx, 'columns.' + cIdx);
            }, function () {
                return '';
            }) +
            renderJsonSubEditor({rows: data.rows || []}, idx, 'rows', 'Rows (JSON)');
    }

    // ----- Numbered List -----
    function renderNumberedListFields(data, idx) {
        var items = data.items || [];
        return textField('Heading', data.heading, idx, 'heading') +
            htmlField('Preamble HTML', data.preamble_html, idx, 'preamble_html') +
            renderRepeater('Items', items, idx, 'items', function (item, iIdx) {
                return textFieldDirect('Item Text', item, idx, 'items.' + iIdx);
            }, function () {
                return '';
            });
    }

    // ----- Proposal Cards -----
    function renderProposalCardsFields(data, idx) {
        var proposals = data.proposals || [];
        return textField('Heading', data.heading, idx, 'heading') +
            htmlField('Footer HTML', data.footer_html, idx, 'footer_html') +
            renderRepeater('Proposals', proposals, idx, 'proposals', function (p, pIdx) {
                return '<div class="cms-block-field-row">' +
                    textField('Type', p.type, idx, 'proposals.' + pIdx + '.type') +
                    textField('Title', p.title, idx, 'proposals.' + pIdx + '.title') +
                    textField('Organization', p.organization, idx, 'proposals.' + pIdx + '.organization') +
                    '</div>' +
                    htmlField('Background', p.background, idx, 'proposals.' + pIdx + '.background') +
                    htmlField('Problem', p.problem, idx, 'proposals.' + pIdx + '.problem') +
                    htmlField('Objectives', p.objectives, idx, 'proposals.' + pIdx + '.objectives');
            }, function () {
                return {type: '', title: '', organization: '', background: '', problem: '', objectives: ''};
            });
    }

    // ----- Navigation Grid -----
    function renderNavigationGridFields(data, idx) {
        var items = data.items || [];
        return textField('Heading', data.heading, idx, 'heading') +
            renderRepeater('Grid Items', items, idx, 'items', function (item, iIdx) {
                return '<div class="cms-block-field-row">' +
                    textField('Title', item.title, idx, 'items.' + iIdx + '.title') +
                    textField('URL', item.url, idx, 'items.' + iIdx + '.url') +
                    '</div>' +
                    textField('Description', item.description, idx, 'items.' + iIdx + '.description') +
                    checkboxField('External link', item.is_external, idx, 'items.' + iIdx + '.is_external');
            }, function () {
                return {title: '', url: '', description: '', is_external: false};
            });
    }

    // ----- Schedule Grid -----
    function renderScheduleGridFields(data, idx) {
        return textField('Heading', data.heading, idx, 'heading') +
            textField('Sheet Source Slug', data.sheet_source_slug, idx, 'sheet_source_slug');
    }

    // ===== Field Primitives =====
    function textField(label, value, blockIdx, dataPath) {
        return '<div class="cms-block-field">' +
            '<label>' + escapeHtml(label) + '</label>' +
            '<input type="text" value="' + escapeAttr(value) + '" ' +
            'onchange="updateBlockData(' + blockIdx + ', \'' + dataPath + '\', this.value)">' +
            '</div>';
    }

    function textFieldDirect(label, value, blockIdx, dataPath) {
        // For simple array items (strings, not objects)
        return '<div class="cms-block-field">' +
            '<label>' + escapeHtml(label) + '</label>' +
            '<input type="text" value="' + escapeAttr(value) + '" ' +
            'onchange="updateBlockDataDirect(' + blockIdx + ', \'' + dataPath + '\', this.value)">' +
            '</div>';
    }

    function htmlField(label, value, blockIdx, dataPath) {
        return '<div class="cms-block-field">' +
            '<label>' + escapeHtml(label) + '</label>' +
            '<textarea class="html-field" ' +
            'onchange="updateBlockData(' + blockIdx + ', \'' + dataPath + '\', this.value)">' +
            escapeHtml(value || '') + '</textarea>' +
            '<span class="field-hint">Supports HTML markup</span>' +
            '</div>';
    }

    function selectField(label, value, blockIdx, dataPath, options) {
        var optsHtml = options.map(function (opt) {
            var selected = String(value) === String(opt[0]) ? ' selected' : '';
            return '<option value="' + escapeAttr(opt[0]) + '"' + selected + '>' + escapeHtml(opt[1]) + '</option>';
        }).join('');

        return '<div class="cms-block-field field-small">' +
            '<label>' + escapeHtml(label) + '</label>' +
            '<select onchange="updateBlockData(' + blockIdx + ', \'' + dataPath + '\', this.value)">' +
            optsHtml +
            '</select>' +
            '</div>';
    }

    function checkboxField(label, value, blockIdx, dataPath) {
        var checked = value ? ' checked' : '';
        var id = 'cb-' + blockIdx + '-' + dataPath.replace(/\./g, '-');
        return '<div class="cms-block-field-checkbox">' +
            '<input type="checkbox" id="' + id + '"' + checked + ' ' +
            'onchange="updateBlockData(' + blockIdx + ', \'' + dataPath + '\', this.checked)">' +
            '<label for="' + id + '">' + escapeHtml(label) + '</label>' +
            '</div>';
    }

    function renderJsonSubEditor(data, blockIdx, fieldName, label) {
        var jsonStr = JSON.stringify(fieldName ? data[fieldName] : data, null, 2);
        var displayLabel = label || 'Data (JSON)';
        return '<div class="cms-json-subeditor">' +
            '<div class="cms-block-field">' +
            '<label>' + escapeHtml(displayLabel) + '</label>' +
            '<textarea onchange="updateBlockDataJson(' + blockIdx + ', \'' + (fieldName || '') + '\', this.value)">' +
            escapeHtml(jsonStr) + '</textarea>' +
            '</div>' +
            '</div>';
    }

    // ===== Repeater =====
    function renderRepeater(label, items, blockIdx, fieldName, renderItem, createDefault) {
        var itemsHtml = '';
        if (items.length === 0) {
            itemsHtml = '<p style="color:#999; font-style:italic; font-size:13px;">No items yet.</p>';
        } else {
            itemsHtml = items.map(function (item, itemIdx) {
                var itemActions = '';
                if (itemIdx > 0) itemActions += '<button type="button" onclick="moveRepeaterItem(' + blockIdx + ', \'' + fieldName + '\', ' + itemIdx + ', -1)">&uarr;</button>';
                if (itemIdx < items.length - 1) itemActions += '<button type="button" onclick="moveRepeaterItem(' + blockIdx + ', \'' + fieldName + '\', ' + itemIdx + ', 1)">&darr;</button>';
                itemActions += '<button type="button" class="btn-repeater-delete" onclick="removeRepeaterItem(' + blockIdx + ', \'' + fieldName + '\', ' + itemIdx + ')">&times;</button>';

                return '<div class="cms-repeater-item">' +
                    '<div class="cms-repeater-item-header">' +
                    '<span class="cms-repeater-item-number">Item ' + (itemIdx + 1) + '</span>' +
                    '<div class="cms-repeater-item-actions">' + itemActions + '</div>' +
                    '</div>' +
                    renderItem(item, itemIdx) +
                    '</div>';
            }).join('');
        }

        return '<div class="cms-repeater">' +
            '<div class="cms-repeater-header"><label>' + escapeHtml(label) + '</label></div>' +
            '<div class="cms-repeater-items">' + itemsHtml + '</div>' +
            '<button type="button" class="btn-repeater-add" onclick="addRepeaterItem(' + blockIdx + ', \'' + fieldName + '\')">+ Add ' + escapeHtml(label.replace(/s$/, '')) + '</button>' +
            '</div>';
    }

    // ===== Data Accessors =====
    function setNestedValue(obj, path, value) {
        var parts = path.split('.');
        var current = obj;
        for (var i = 0; i < parts.length - 1; i++) {
            var key = parts[i];
            if (/^\d+$/.test(key)) key = parseInt(key);
            if (current[key] === undefined) current[key] = {};
            current = current[key];
        }
        var lastKey = parts[parts.length - 1];
        if (/^\d+$/.test(lastKey)) lastKey = parseInt(lastKey);
        current[lastKey] = value;
    }

    function getNestedValue(obj, path) {
        var parts = path.split('.');
        var current = obj;
        for (var i = 0; i < parts.length; i++) {
            var key = parts[i];
            if (/^\d+$/.test(key)) key = parseInt(key);
            if (current === undefined || current === null) return undefined;
            current = current[key];
        }
        return current;
    }

    // Default data factories for repeater items (keyed by block_type + field)
    var repeaterDefaults = {};

    // ===== Sync =====
    function syncToJson() {
        var hidden = document.getElementById('id_blocks_json');
        if (hidden) {
            hidden.value = JSON.stringify(blocks);
        }
        scheduleLivePreviewSync();
    }

    // ===== Live Preview =====
    function gatherPageData() {
        var routeEl = document.getElementById('id_route');
        var titleEl = document.getElementById('id_title');
        var slugEl = document.getElementById('id_slug');
        var cssClassEl = document.getElementById('id_page_css_class');
        var metaDescEl = document.getElementById('id_meta_description');

        return {
            slug: slugEl ? slugEl.value : '',
            route: routeEl ? routeEl.value : (window.CMS_ROUTE_EDITOR && window.CMS_ROUTE_EDITOR.pageRoute) || '/',
            title: titleEl ? titleEl.value : '',
            page_css_class: cssClassEl ? cssClassEl.value : '',
            meta_description: metaDescEl ? metaDescEl.value : '',
            blocks: blocks.map(function (b, i) {
                return {block_type: b.block_type, sort_order: i, data: b.data};
            }),
        };
    }

    function postLivePreview(callback) {
        var config = window.CMS_ROUTE_EDITOR || {};
        var pageId = config.pageId;
        if (!pageId) return;

        var csrfToken = '';
        var csrfEl = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfEl) csrfToken = csrfEl.value;

        fetch('/cms/live-preview/' + pageId + '/', {
            method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
            body: JSON.stringify(gatherPageData()),
            credentials: 'same-origin',
        })
            .then(function () {
                if (callback) callback();
            })
            .catch(function () { /* silently ignore */
            });
    }

    function scheduleLivePreviewSync() {
        if (!livePreviewActive) return;
        if (livePreviewTimer) clearTimeout(livePreviewTimer);
        livePreviewTimer = setTimeout(function () {
            postLivePreview();
        }, 500);
    }

    window.openLivePreview = function () {
        var config = window.CMS_ROUTE_EDITOR || {};
        var pageId = config.pageId;
        if (!pageId) {
            alert('Save the page first before previewing.');
            return;
        }

        livePreviewActive = true;

        postLivePreview(function () {
            var route = gatherPageData().route || '/';
            if (route.charAt(0) !== '/') route = '/' + route;
            var base = (config.frontendUrl || '').replace(/\/+$/, '') || window.location.origin;
            window.open(base + route + '?cms_live_preview=' + pageId, '_blank');
        });
    };

    // ===== Global Actions =====
    window.addBlock = function () {
        var select = document.getElementById('cms-add-block-type');
        if (!select || !select.value) return;
        var blockType = select.value;

        blocks.push({
            block_type: blockType,
            sort_order: blocks.length,
            admin_label: '',
            data: getDefaultData(blockType),
        });

        select.value = '';
        renderAll();
        syncToJson();

        // Scroll to new block
        var container = document.getElementById('cms-blocks-container');
        if (container && container.lastElementChild) {
            container.lastElementChild.scrollIntoView({behavior: 'smooth', block: 'center'});
        }
    };

    window.removeBlock = function (idx) {
        if (!confirm('Remove this block?')) return;
        blocks.splice(idx, 1);
        // Fix collapsed set
        var newCollapsed = new Set();
        collapsedSet.forEach(function (i) {
            if (i < idx) newCollapsed.add(i);
            else if (i > idx) newCollapsed.add(i - 1);
        });
        collapsedSet = newCollapsed;
        renderAll();
        syncToJson();
    };

    window.moveBlock = function (idx, direction) {
        var newIdx = idx + direction;
        if (newIdx < 0 || newIdx >= blocks.length) return;
        var temp = blocks[idx];
        blocks[idx] = blocks[newIdx];
        blocks[newIdx] = temp;

        // Fix collapsed set
        var newCollapsed = new Set();
        collapsedSet.forEach(function (i) {
            if (i === idx) newCollapsed.add(newIdx);
            else if (i === newIdx) newCollapsed.add(idx);
            else newCollapsed.add(i);
        });
        collapsedSet = newCollapsed;

        renderAll();
        syncToJson();
    };

    window.toggleCollapse = function (idx) {
        if (collapsedSet.has(idx)) {
            collapsedSet.delete(idx);
        } else {
            collapsedSet.add(idx);
        }
        renderAll();
    };

    window.updateBlockProp = function (idx, prop, value) {
        blocks[idx][prop] = value;
        renderAll();
        syncToJson();
    };

    window.updateBlockData = function (idx, dataPath, value) {
        var data = blocks[idx].data;
        setNestedValue(data, dataPath, value);
        syncToJson();
        // Don't re-render for simple value changes to avoid losing focus
    };

    window.updateBlockDataDirect = function (idx, dataPath, value) {
        // For simple array items: "items.2" means blocks[idx].data.items[2] = value
        var data = blocks[idx].data;
        setNestedValue(data, dataPath, value);
        syncToJson();
    };

    window.updateBlockDataJson = function (idx, fieldName, jsonStr) {
        try {
            var parsed = JSON.parse(jsonStr);
            if (fieldName) {
                blocks[idx].data[fieldName] = parsed;
            } else {
                blocks[idx].data = parsed;
            }
            syncToJson();
        } catch (e) {
            // Invalid JSON - do nothing, user is still editing
        }
    };

    // ===== Repeater Actions =====
    window.addRepeaterItem = function (blockIdx, fieldName) {
        var data = blocks[blockIdx].data;
        if (!data[fieldName]) data[fieldName] = [];
        var defaultItem = getRepeaterDefault(blocks[blockIdx].block_type, fieldName);
        data[fieldName].push(defaultItem);
        renderAll();
        syncToJson();
    };

    window.removeRepeaterItem = function (blockIdx, fieldName, itemIdx) {
        var arr = blocks[blockIdx].data[fieldName];
        if (arr) {
            arr.splice(itemIdx, 1);
            renderAll();
            syncToJson();
        }
    };

    window.moveRepeaterItem = function (blockIdx, fieldName, itemIdx, direction) {
        var arr = blocks[blockIdx].data[fieldName];
        if (!arr) return;
        var newIdx = itemIdx + direction;
        if (newIdx < 0 || newIdx >= arr.length) return;
        var temp = arr[itemIdx];
        arr[itemIdx] = arr[newIdx];
        arr[newIdx] = temp;
        renderAll();
        syncToJson();
    };

    function getRepeaterDefault(blockType, fieldName) {
        var defaults = {
            'faq_list.items': function () {
                return {question: '', answer_html: ''};
            },
            'link_list.items': function () {
                return {label: '', url: '', description: '', is_external: false};
            },
            'cta_group.items': function () {
                return {label: '', href: '', style: ''};
            },
            'contact_info.items': function () {
                return {label: '', value: '', type: 'email'};
            },
            'section_group.sections': function () {
                return {heading: '', heading_level: '', body_html: ''};
            },
            'table.columns': function () {
                return '';
            },
            'numbered_list.items': function () {
                return '';
            },
            'proposal_cards.proposals': function () {
                return {type: '', title: '', organization: '', background: '', problem: '', objectives: ''};
            },
            'navigation_grid.items': function () {
                return {title: '', url: '', description: '', is_external: false};
            },
        };
        var key = blockType + '.' + fieldName;
        if (defaults[key]) return defaults[key]();
        return {};
    }

    // ===== JSON Toggle =====
    window.toggleJsonView = function () {
        var el = document.getElementById('json-raw-view');
        if (el) el.classList.toggle('show');
    };

    window.copyJson = function () {
        var editor = document.getElementById('json-editor');
        if (!editor) return;
        editor.select();
        try {
            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(editor.value);
            } else {
                document.execCommand('copy');
            }
        } catch (e) { /* ignore */
        }
    };

    window.applyJson = function () {
        var editor = document.getElementById('json-editor');
        if (!editor) return;
        var text = editor.value.trim();
        if (!text) return;
        try {
            var parsed = JSON.parse(text);
            if (!Array.isArray(parsed)) {
                alert('JSON must be an array of block objects.');
                return;
            }
            blocks = parsed;
            collapsedSet.clear();
            renderAll();
            syncToJson();
        } catch (e) {
            alert('Invalid JSON: ' + e.message);
        }
    };

    // ===== Bootstrap =====
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
