(function () {
    const P = window.ITGCmsBlockPrimitives;

    function renderAll(blocks, collapsedSet) {
        const container = document.getElementById('cms-blocks-container');
        if (!container) return;
        container.innerHTML = !blocks.length ? '<p class="cms-blocks-empty">No content blocks yet. Add blocks using the dropdown below.</p>' : blocks.map((block, idx) => renderBlockCard(block, idx, blocks, collapsedSet)).join('');
        const jsonEditor = document.getElementById('json-editor');
        if (jsonEditor) jsonEditor.value = JSON.stringify(blocks, null, 2);
        initHtmlCodeEditors(container);
    }

    function initHtmlCodeEditors(container) {
        if (!window.CodeMirror || typeof window.CodeMirror.fromTextArea !== 'function') {
            container.querySelectorAll('textarea.html-field').forEach(textarea => { textarea.style.minHeight = '360px'; });
            return;
        }
        container.querySelectorAll('textarea.html-field').forEach(textarea => {
            if (textarea._cmInstance) return;
            const cm = window.CodeMirror.fromTextArea(textarea, { mode: 'htmlmixed', lineNumbers: true, lineWrapping: true, tabSize: 2, indentUnit: 2, viewportMargin: Infinity });
            textarea._cmInstance = cm;
            cm.setSize(null, 380);
            cm.on('change', instance => {
                const target = instance.getTextArea();
                target.value = instance.getValue();
                try { target.dispatchEvent(new Event('input', { bubbles: true })); }
                catch (e) { const evt = document.createEvent('Event'); evt.initEvent('input', true, true); target.dispatchEvent(evt); }
            });
        });
    }

    function renderBlockCard(block, idx, blocks, collapsedSet) {
        const isCollapsed = collapsedSet.has(idx);
        let actions = '';
        if (idx > 0) actions += `<button type="button" class="btn-block-move" onclick="moveBlock(${idx}, -1)" title="Move up">&uarr;</button>`;
        if (idx < blocks.length - 1) actions += `<button type="button" class="btn-block-move" onclick="moveBlock(${idx}, 1)" title="Move down">&darr;</button>`;
        actions += `<button type="button" class="btn-block-delete" onclick="removeBlock(${idx})" title="Delete block">&times;</button>`;
        return `<div class="cms-block-card${isCollapsed ? ' is-collapsed' : ''}" data-index="${idx}"><div class="cms-block-card-header" onclick="toggleCollapse(${idx})"><span class="cms-block-card-title"><span class="cms-block-collapse-icon">&rsaquo;</span><span class="block-order">#${idx + 1}</span><span class="cms-block-type-badge type-${P.escapeAttr(block.block_type)}">${P.escapeHtml(P.getTypeLabel(block.block_type))}</span><span class="cms-block-label-text">${P.escapeHtml(block.admin_label || '')}</span></span><div class="cms-block-card-actions" onclick="event.stopPropagation();">${actions}</div></div>${isCollapsed ? '' : `<div class="cms-block-card-body">${renderAdminLabel(block, idx)}${renderBlockFields(block, idx)}</div>`}</div>`;
    }

    function renderAdminLabel(block, idx) { return `<div class="cms-block-admin-label"><label>Admin Label</label><input type="text" value="${P.escapeAttr(block.admin_label)}" placeholder="Optional label for admin identification" onchange="updateBlockProp(${idx}, 'admin_label', this.value)"></div>`; }
    function renderBlockFields(block, idx) { const renderer = renderers[block.block_type]; return renderer ? renderer(block.data || {}, idx) : P.renderJsonSubEditor(block.data || {}, idx); }
    function renderHeroFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.textField('Subheading', data.subheading, idx, 'subheading') + '<div class="cms-block-field-row">' + P.textField('Image URL', data.image_url, idx, 'image_url') + P.textField('Image Alt Text', data.image_alt, idx, 'image_alt') + '</div>'; }
    function renderRichTextField(data, idx) { return '<div class="cms-block-field-row">' + P.textField('Heading', data.heading, idx, 'heading') + P.selectField('Heading Level', data.heading_level, idx, 'heading_level', [['', 'Default'], ['1', 'H1'], ['2', 'H2'], ['3', 'H3'], ['4', 'H4'], ['5', 'H5'], ['6', 'H6']]) + '</div>' + P.htmlField('Body HTML', data.body_html, idx, 'body_html'); }
    function renderFaqListFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.renderRepeater('FAQ Items', data.items || [], idx, 'items', (item, itemIdx) => P.textField('Question', item.question, idx, 'items.' + itemIdx + '.question') + P.htmlField('Answer HTML', item.answer_html, idx, 'items.' + itemIdx + '.answer_html')); }
    function renderLinkListFields(data, idx) { return '<div class="cms-block-field-row">' + P.textField('Heading', data.heading, idx, 'heading') + P.selectField('Style', data.style, idx, 'style', [['list', 'List'], ['grid', 'Grid'], ['inline', 'Inline']]) + '</div>' + P.renderRepeater('Links', data.items || [], idx, 'items', (item, itemIdx) => '<div class="cms-block-field-row">' + P.textField('Label', item.label, idx, 'items.' + itemIdx + '.label') + P.textField('URL', item.url, idx, 'items.' + itemIdx + '.url') + '</div><div class="cms-block-field-row">' + P.textField('Description', item.description, idx, 'items.' + itemIdx + '.description') + '</div>' + P.checkboxField('External link', item.is_external, idx, 'items.' + itemIdx + '.is_external')); }
    function renderCtaGroupFields(data, idx) { return P.renderRepeater('CTA Buttons', data.items || [], idx, 'items', (item, itemIdx) => '<div class="cms-block-field-row">' + P.textField('Label', item.label, idx, 'items.' + itemIdx + '.label') + P.textField('URL', item.href, idx, 'items.' + itemIdx + '.href') + P.textField('Style', item.style, idx, 'items.' + itemIdx + '.style') + '</div>'); }
    function renderImageTextFields(data, idx) { return '<div class="cms-block-field-row">' + P.textField('Heading', data.heading, idx, 'heading') + P.selectField('Image Position', data.image_position, idx, 'image_position', [['top', 'Top'], ['left', 'Left'], ['right', 'Right']]) + '</div><div class="cms-block-field-row">' + P.textField('Image URL', data.image_url, idx, 'image_url') + P.textField('Image Alt', data.image_alt, idx, 'image_alt') + '</div>' + P.htmlField('Body HTML', data.body_html, idx, 'body_html'); }
    function renderNoticeFields(data, idx) { return '<div class="cms-block-field-row">' + P.textField('Heading', data.heading, idx, 'heading') + P.selectField('Style', data.style, idx, 'style', [['info', 'Info'], ['warning', 'Warning'], ['success', 'Success']]) + '</div>' + P.htmlField('Body HTML', data.body_html, idx, 'body_html'); }
    function renderContactInfoFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.renderRepeater('Contacts', data.items || [], idx, 'items', (item, itemIdx) => '<div class="cms-block-field-row">' + P.textField('Label', item.label, idx, 'items.' + itemIdx + '.label') + P.textField('Value', item.value, idx, 'items.' + itemIdx + '.value') + P.selectField('Type', item.type, idx, 'items.' + itemIdx + '.type', [['email', 'Email'], ['phone', 'Phone'], ['url', 'URL'], ['text', 'Text']]) + '</div>'); }
    function renderSectionGroupFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.renderRepeater('Sections', data.sections || [], idx, 'sections', (section, sectionIdx) => '<div class="cms-block-field-row">' + P.textField('Section Heading', section.heading, idx, 'sections.' + sectionIdx + '.heading') + P.selectField('Heading Level', section.heading_level, idx, 'sections.' + sectionIdx + '.heading_level', [['', 'Default'], ['2', 'H2'], ['3', 'H3'], ['4', 'H4'], ['5', 'H5']]) + '</div>' + P.htmlField('Body HTML', section.body_html, idx, 'sections.' + sectionIdx + '.body_html')); }
    function renderTableFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.renderRepeater('Columns', data.columns || [], idx, 'columns', (col, colIdx) => P.textFieldDirect('Column Name', col, idx, 'columns.' + colIdx)) + P.renderJsonSubEditor({ rows: data.rows || [] }, idx, 'rows', 'Rows (JSON)'); }
    function renderNumberedListFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.htmlField('Preamble HTML', data.preamble_html, idx, 'preamble_html') + P.renderRepeater('Items', data.items || [], idx, 'items', (item, itemIdx) => P.textFieldDirect('Item Text', item, idx, 'items.' + itemIdx)); }
    function renderProposalCardsFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.htmlField('Footer HTML', data.footer_html, idx, 'footer_html') + P.renderRepeater('Proposals', data.proposals || [], idx, 'proposals', (proposal, proposalIdx) => '<div class="cms-block-field-row">' + P.textField('Type', proposal.type, idx, 'proposals.' + proposalIdx + '.type') + P.textField('Title', proposal.title, idx, 'proposals.' + proposalIdx + '.title') + P.textField('Organization', proposal.organization, idx, 'proposals.' + proposalIdx + '.organization') + '</div>' + P.htmlField('Background', proposal.background, idx, 'proposals.' + proposalIdx + '.background') + P.htmlField('Problem', proposal.problem, idx, 'proposals.' + proposalIdx + '.problem') + P.htmlField('Objectives', proposal.objectives, idx, 'proposals.' + proposalIdx + '.objectives')); }
    function renderNavigationGridFields(data, idx) { return P.textField('Heading', data.heading, idx, 'heading') + P.renderRepeater('Grid Items', data.items || [], idx, 'items', (item, itemIdx) => '<div class="cms-block-field-row">' + P.textField('Title', item.title, idx, 'items.' + itemIdx + '.title') + P.textField('URL', item.url, idx, 'items.' + itemIdx + '.url') + '</div>' + P.textField('Description', item.description, idx, 'items.' + itemIdx + '.description') + P.checkboxField('External link', item.is_external, idx, 'items.' + itemIdx + '.is_external')); }

    const renderers = { hero: renderHeroFields, rich_text: renderRichTextField, faq_list: renderFaqListFields, link_list: renderLinkListFields, cta_group: renderCtaGroupFields, image_text: renderImageTextFields, notice: renderNoticeFields, contact_info: renderContactInfoFields, section_group: renderSectionGroupFields, table: renderTableFields, numbered_list: renderNumberedListFields, proposal_cards: renderProposalCardsFields, navigation_grid: renderNavigationGridFields };
    window.ITGCmsBlockRenderers = { renderAll: renderAll };
})();
