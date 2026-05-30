(function () {
    const routes = { appRoutes: window.APP_ROUTES || [], cmsRoutes: window.CMS_ROUTES || [] };
    const sectionApi = window.ITGFooterSections;
    const previewApi = window.ITGFooterPreview;
    let jsonInput = null;
    let iframe = null;
    let errorBox = null;
    let footerData = { cta_buttons: [], contact_html: '', columns: [], social_links: [], copyright: '', footer_links: [] };

    function isCmsRoute(url) { return !!url && routes.cmsRoutes.some(route => route.url === url); }

    function init() {
        jsonInput = document.getElementById('id_content') || document.querySelector('textarea[name="content"]');
        iframe = document.getElementById('footer-preview-iframe');
        errorBox = document.getElementById('footer-preview-error');
        if (jsonInput) {
            try { footerData = { ...footerData, ...JSON.parse(jsonInput.value || '{}') }; }
            catch (e) { console.error('Failed to parse initial JSON:', e); }
        }
        document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(node => node.classList.remove('active'));
            document.querySelectorAll('.editor-section').forEach(node => node.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('section-' + btn.dataset.tab).classList.add('active');
        }));
        document.getElementById('contact-html-input').addEventListener('input', event => { footerData.contact_html = event.target.value; syncToJson(); });
        document.getElementById('copyright-input').addEventListener('input', event => { footerData.copyright = event.target.value; syncToJson(); });
        setupJsonEditorEvents();
        renderAll();
        updatePreview();
    }

    function renderAll() { sectionApi.renderAll(footerData, routes, isCmsRoute); }
    function updatePreview() { previewApi.updatePreview(iframe, errorBox, footerData); }
    function syncToJson() { if (jsonInput) jsonInput.value = JSON.stringify(footerData); document.getElementById('json-editor').value = JSON.stringify(footerData, null, 2); updatePreview(); }

    window.addCtaButton = type => updateAndRender(() => footerData.cta_buttons.push({ type: type || 'external', label: 'New Button', href: ['app', 'cms'].includes(type) ? '' : '#', style: 'blue' }), true);
    window.removeCtaButton = idx => updateAndRender(() => footerData.cta_buttons.splice(idx, 1), true);
    window.updateCtaButton = (idx, field, value) => updateAndRender(() => { footerData.cta_buttons[idx][field] = value; });
    window.changeCtaType = (idx, newType) => updateAndRender(() => { const btn = footerData.cta_buttons[idx]; btn.type = newType; btn.href = ['app', 'cms'].includes(newType) ? '' : '#'; }, true);
    window.selectCtaAppRoute = (idx, url) => updateAndRender(() => { const btn = footerData.cta_buttons[idx]; btn.href = url; const route = routes.appRoutes.find(entry => entry.url === url); if (route && (!btn.label || btn.label === 'New Button')) btn.label = route.title; }, true);
    window.selectCtaCmsRoute = (idx, url) => updateAndRender(() => { const btn = footerData.cta_buttons[idx]; btn.href = url; const route = routes.cmsRoutes.find(entry => entry.url === url); if (route && (!btn.label || btn.label === 'New Button')) btn.label = route.title; }, true);
    window.addColumn = () => updateAndRender(() => footerData.columns.push({ title: 'New Column', links: [], body_html: '' }), true);
    window.removeColumn = idx => updateAndRender(() => footerData.columns.splice(idx, 1), true);
    window.addColumnLink = colIdx => updateAndRender(() => { (footerData.columns[colIdx].links ||= []).push({ label: 'New Link', href: '#', target: '_blank', rel: 'noopener' }); }, true);
    window.removeColumnLink = (colIdx, linkIdx) => updateAndRender(() => footerData.columns[colIdx].links.splice(linkIdx, 1), true);
    window.updateColumn = (idx, field, value) => updateAndRender(() => { footerData.columns[idx][field] = value; });
    window.updateColumnLink = (colIdx, linkIdx, field, value) => updateAndRender(() => { footerData.columns[colIdx].links[linkIdx][field] = value; });
    window.addSocialLink = () => updateAndRender(() => footerData.social_links.push({ href: '#', icon_class: 'fa fa-facebook', aria_label: 'Facebook', target: '_blank', rel: 'noopener' }), true);
    window.removeSocialLink = idx => updateAndRender(() => footerData.social_links.splice(idx, 1), true);
    window.updateSocialLink = (idx, field, value) => updateAndRender(() => { footerData.social_links[idx][field] = value; });
    window.addFooterLink = type => updateAndRender(() => footerData.footer_links.push({ type: type || 'external', label: 'New Link', href: ['app', 'cms'].includes(type) ? '' : '#', target: type === 'external' ? '_blank' : '', rel: type === 'external' ? 'noopener' : '' }), true);
    window.removeFooterLink = idx => updateAndRender(() => footerData.footer_links.splice(idx, 1), true);
    window.updateFooterLink = (idx, field, value) => updateAndRender(() => { footerData.footer_links[idx][field] = value; });
    window.changeFooterLinkType = (idx, newType) => updateAndRender(() => { const link = footerData.footer_links[idx]; link.type = newType; link.href = ['app', 'cms'].includes(newType) ? '' : '#'; link.target = newType === 'external' ? '_blank' : ''; link.rel = newType === 'external' ? 'noopener' : ''; }, true);
    window.selectFooterLinkAppRoute = (idx, url) => updateAndRender(() => { const link = footerData.footer_links[idx]; link.href = url; const route = routes.appRoutes.find(entry => entry.url === url); if (route && (!link.label || link.label === 'New Link')) link.label = route.title; }, true);
    window.selectFooterLinkCmsRoute = (idx, url) => updateAndRender(() => { const link = footerData.footer_links[idx]; link.href = url; const route = routes.cmsRoutes.find(entry => entry.url === url); if (route && (!link.label || link.label === 'New Link')) link.label = route.title; }, true);

    window.toggleJsonView = () => document.getElementById('json-raw-view').classList.toggle('show');
    window.applyJsonChanges = function () {
        const jsonEditor = document.getElementById('json-editor');
        const jsonErrorBox = document.getElementById('json-error');
        if (!jsonEditor || !jsonEditor.value.trim()) return showJsonStatus(jsonErrorBox, jsonEditor, 'Please enter JSON content', false);
        try {
            let parsed = JSON.parse(jsonEditor.value);
            if (Array.isArray(parsed) && parsed.length && parsed[0].fields) parsed = parsed[0].fields.content || parsed[0].fields;
            if (parsed.content && typeof parsed.content === 'object' && !parsed.cta_buttons) parsed = parsed.content;
            if (typeof parsed !== 'object' || parsed === null) throw new Error('JSON must be an object');
            footerData = { cta_buttons: parsed.cta_buttons || [], contact_html: parsed.contact_html || '', columns: parsed.columns || [], social_links: parsed.social_links || [], copyright: parsed.copyright || '', footer_links: parsed.footer_links || [] };
            if (!jsonInput) jsonInput = document.getElementById('id_content') || document.querySelector('textarea[name="content"]');
            renderAll();
            syncToJson();
            showJsonStatus(jsonErrorBox, jsonEditor, '✓ JSON applied successfully!', true);
        } catch (e) {
            showJsonStatus(jsonErrorBox, jsonEditor, 'Invalid JSON: ' + e.message, false);
        }
    };

    function setupJsonEditorEvents() {
        const jsonEditor = document.getElementById('json-editor');
        const applyBtn = document.querySelector('.btn-apply-json');
        if (jsonEditor) {
            jsonEditor.addEventListener('input', function () { this.style.borderColor = ''; const box = document.getElementById('json-error'); if (box) { box.textContent = ''; box.className = 'json-error'; } });
            jsonEditor.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); window.applyJsonChanges(); } });
        }
        if (applyBtn) applyBtn.addEventListener('click', event => { event.preventDefault(); window.applyJsonChanges(); });
    }

    function updateAndRender(callback, rerender) { callback(); if (rerender) renderAll(); syncToJson(); }
    function showJsonStatus(box, editor, message, success) {
        if (box) { box.textContent = message; box.className = message ? 'json-error show' : 'json-error'; box.style.background = success ? '#d4edda' : ''; box.style.borderColor = success ? '#c3e6cb' : ''; box.style.color = success ? '#155724' : ''; }
        if (editor) editor.style.borderColor = success ? '#28a745' : '#dc3545';
        if (success) setTimeout(() => { if (box) { box.textContent = ''; box.className = 'json-error'; box.style.background = ''; box.style.borderColor = ''; box.style.color = ''; } editor.style.borderColor = ''; }, 2000);
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
