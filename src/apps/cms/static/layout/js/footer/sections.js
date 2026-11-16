(function () {
    function escapeHtml(val) {
        const div = document.createElement('div');
        div.textContent = val || '';
        return div.innerHTML;
    }

    function escapeAttr(val) {
        return String(val || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function actionAttrs(call, eventName, args, valueSource) {
        const valueAttr = valueSource ? ` data-admin-value="${escapeAttr(valueSource)}"` : '';
        return `data-admin-call="${escapeAttr(call)}" data-admin-event="${escapeAttr(eventName)}" data-admin-args="${escapeAttr(JSON.stringify(args || []))}"${valueAttr}`;
    }

    function renderCtaButtons(data, routes, isCmsRoute) {
        document.getElementById('cta-list').innerHTML = (data.cta_buttons || []).map((btn, idx) => {
            const btnType = (btn.type === 'app' && isCmsRoute(btn.href)) ? 'cms' : (btn.type || 'external');
            const typeSelector = `<div class="item-field" style="max-width: 120px;"><label>Type</label><select ${actionAttrs('changeCtaType', 'change', [idx], 'value')}><option value="external" ${btnType === 'external' ? 'selected' : ''}>External</option><option value="app" ${btnType === 'app' ? 'selected' : ''}>App Route</option><option value="cms" ${btnType === 'cms' ? 'selected' : ''}>CMS Page</option></select></div>`;
            const urlField = btnType === 'app' ? selectField('App Route', 'selectCtaAppRoute', idx, btn.href, routes.appRoutes) : btnType === 'cms' ? selectField('CMS Page', 'selectCtaCmsRoute', idx, btn.href, routes.cmsRoutes) : `<div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(btn.href)}" placeholder="https://example.com" ${actionAttrs('updateCtaButton', 'change', [idx, 'href'], 'value')}></div>`;
            return `<div class="item-card"><div class="item-card-header"><span class="item-card-title">Button ${idx + 1}</span><div class="item-card-actions"><button type="button" class="btn-delete" ${actionAttrs('removeCtaButton', 'click', [idx])}>Delete</button></div></div><div class="item-row">${typeSelector}<div class="item-field"><label>Label</label><input type="text" value="${escapeAttr(btn.label)}" ${actionAttrs('updateCtaButton', 'change', [idx, 'label'], 'value')}></div>${urlField}<div class="item-field" style="max-width: 120px;"><label>Style</label><select ${actionAttrs('updateCtaButton', 'change', [idx, 'style'], 'value')}><option value="blue" ${btn.style === 'blue' ? 'selected' : ''}>Blue</option><option value="gold" ${btn.style === 'gold' ? 'selected' : ''}>Gold</option></select></div></div></div>`;
        }).join('');
    }

    function renderColumns(data) {
        document.getElementById('columns-list').innerHTML = (data.columns || []).map((col, idx) => `<div class="item-card"><div class="item-card-header"><span class="item-card-title">Column ${idx + 1}: ${escapeHtml(col.title || 'Untitled')}</span><div class="item-card-actions"><button type="button" class="btn-delete" ${actionAttrs('removeColumn', 'click', [idx])}>Delete</button></div></div><div class="item-row"><div class="item-field"><label>Title</label><input type="text" value="${escapeAttr(col.title)}" ${actionAttrs('updateColumn', 'change', [idx, 'title'], 'value')}></div></div><div class="item-field"><label>Body HTML (optional)</label><textarea rows="2" ${actionAttrs('updateColumn', 'change', [idx, 'body_html'], 'value')}>${escapeHtml(col.body_html || '')}</textarea></div><div class="column-links"><label style="font-weight: 600; margin-bottom: 8px; display: block;">Links</label>${(col.links || []).map((link, linkIdx) => `<div class="link-item"><input type="text" placeholder="Label" value="${escapeAttr(link.label)}" ${actionAttrs('updateColumnLink', 'change', [idx, linkIdx, 'label'], 'value')}><input type="text" placeholder="URL" value="${escapeAttr(link.href)}" ${actionAttrs('updateColumnLink', 'change', [idx, linkIdx, 'href'], 'value')}><button type="button" class="btn-delete" ${actionAttrs('removeColumnLink', 'click', [idx, linkIdx])}>×</button></div>`).join('')}<button type="button" class="btn-add" style="padding: 4px 8px; font-size: 11px;" ${actionAttrs('addColumnLink', 'click', [idx])}>+ Link</button></div></div>`).join('');
    }

    function renderSocialLinks(data) {
        const iconOptions = [{value: 'fa fa-facebook', label: 'Facebook'}, {value: 'fa fa-twitter', label: 'Twitter/X'}, {value: 'fa fa-linkedin', label: 'LinkedIn'}, {value: 'fa fa-instagram', label: 'Instagram'}, {value: 'fa fa-youtube', label: 'YouTube'}, {value: 'fa fa-github', label: 'GitHub'}];
        document.getElementById('social-list').innerHTML = (data.social_links || []).map((link, idx) => `<div class="item-card"><div class="item-card-header"><span class="item-card-title"><i class="${escapeAttr(link.icon_class)}"></i> ${escapeHtml(link.aria_label)}</span><div class="item-card-actions"><button type="button" class="btn-delete" ${actionAttrs('removeSocialLink', 'click', [idx])}>Delete</button></div></div><div class="item-row"><div class="item-field"><label>Platform</label><select ${actionAttrs('updateSocialPlatform', 'change', [idx], 'selected-text')}>${iconOptions.map(opt => `<option value="${opt.value}" ${link.icon_class === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}</select></div><div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(link.href)}" ${actionAttrs('updateSocialLink', 'change', [idx, 'href'], 'value')}></div></div></div>`).join('');
    }

    function renderFooterLinks(data, routes, isCmsRoute) {
        document.getElementById('footer-links-list').innerHTML = (data.footer_links || []).map((link, idx) => {
            const linkType = (link.type === 'app' && isCmsRoute(link.href)) ? 'cms' : (link.type || 'external');
            const typeSelector = `<div class="item-field" style="max-width: 120px;"><label>Type</label><select ${actionAttrs('changeFooterLinkType', 'change', [idx], 'value')}><option value="external" ${linkType === 'external' ? 'selected' : ''}>External</option><option value="app" ${linkType === 'app' ? 'selected' : ''}>App Route</option><option value="cms" ${linkType === 'cms' ? 'selected' : ''}>CMS Page</option></select></div>`;
            const urlField = linkType === 'app' ? selectField('App Route', 'selectFooterLinkAppRoute', idx, link.href, routes.appRoutes) : linkType === 'cms' ? selectField('CMS Page', 'selectFooterLinkCmsRoute', idx, link.href, routes.cmsRoutes) : `<div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(link.href)}" placeholder="https://example.com" ${actionAttrs('updateFooterLink', 'change', [idx, 'href'], 'value')}></div>`;
            return `<div class="item-card"><div class="item-row">${typeSelector}<div class="item-field"><label>Label</label><input type="text" value="${escapeAttr(link.label)}" ${actionAttrs('updateFooterLink', 'change', [idx, 'label'], 'value')}></div>${urlField}<div class="item-card-actions" style="align-self: flex-end; padding-bottom: 4px;"><button type="button" class="btn-delete" ${actionAttrs('removeFooterLink', 'click', [idx])}>Delete</button></div></div></div>`;
        }).join('');
    }

    function selectField(label, handlerName, idx, currentValue, options) {
        return `<div class="item-field"><label>${label}</label><select ${actionAttrs(handlerName, 'change', [idx], 'value')}><option value="">-- Select Page --</option>${options.map(route => `<option value="${escapeAttr(route.url)}" ${currentValue === route.url ? 'selected' : ''}>${escapeHtml(route.title)} (${escapeHtml(route.url)})</option>`).join('')}</select></div>`;
    }

    window.ITGFooterSections = {
        renderAll: function (data, routes, isCmsRoute) {
            renderCtaButtons(data, routes, isCmsRoute);
            renderColumns(data);
            renderSocialLinks(data);
            renderFooterLinks(data, routes, isCmsRoute);
            document.getElementById('contact-html-input').value = data.contact_html || '';
            document.getElementById('copyright-input').value = data.copyright || '';
            document.getElementById('json-editor').value = JSON.stringify(data, null, 2);
        },
    };
})();
