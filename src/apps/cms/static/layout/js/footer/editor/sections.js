(function () {
    function escapeHtml(val) {
        const div = document.createElement('div');
        div.textContent = val || '';
        return div.innerHTML;
    }

    function escapeAttr(val) {
        return String(val || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function renderCtaButtons(data, routes, isCmsRoute) {
        document.getElementById('cta-list').innerHTML = (data.cta_buttons || []).map((btn, idx) => {
            const btnType = (btn.type === 'app' && isCmsRoute(btn.href)) ? 'cms' : (btn.type || 'external');
            const typeSelector = `<div class="item-field" style="max-width: 120px;"><label>Type</label><select onchange="changeCtaType(${idx}, this.value)"><option value="external" ${btnType === 'external' ? 'selected' : ''}>External</option><option value="app" ${btnType === 'app' ? 'selected' : ''}>App Route</option><option value="cms" ${btnType === 'cms' ? 'selected' : ''}>CMS Page</option></select></div>`;
            const urlField = btnType === 'app' ? selectField('App Route', 'selectCtaAppRoute', idx, btn.href, routes.appRoutes) : btnType === 'cms' ? selectField('CMS Page', 'selectCtaCmsRoute', idx, btn.href, routes.cmsRoutes) : `<div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(btn.href)}" placeholder="https://example.com" onchange="updateCtaButton(${idx}, 'href', this.value)"></div>`;
            return `<div class="item-card"><div class="item-card-header"><span class="item-card-title">Button ${idx + 1}</span><div class="item-card-actions"><button type="button" class="btn-delete" onclick="removeCtaButton(${idx})">Delete</button></div></div><div class="item-row">${typeSelector}<div class="item-field"><label>Label</label><input type="text" value="${escapeAttr(btn.label)}" onchange="updateCtaButton(${idx}, 'label', this.value)"></div>${urlField}<div class="item-field" style="max-width: 120px;"><label>Style</label><select onchange="updateCtaButton(${idx}, 'style', this.value)"><option value="blue" ${btn.style === 'blue' ? 'selected' : ''}>Blue</option><option value="gold" ${btn.style === 'gold' ? 'selected' : ''}>Gold</option></select></div></div></div>`;
        }).join('');
    }

    function renderColumns(data) {
        document.getElementById('columns-list').innerHTML = (data.columns || []).map((col, idx) => `<div class="item-card"><div class="item-card-header"><span class="item-card-title">Column ${idx + 1}: ${escapeHtml(col.title || 'Untitled')}</span><div class="item-card-actions"><button type="button" class="btn-delete" onclick="removeColumn(${idx})">Delete</button></div></div><div class="item-row"><div class="item-field"><label>Title</label><input type="text" value="${escapeAttr(col.title)}" onchange="updateColumn(${idx}, 'title', this.value)"></div></div><div class="item-field"><label>Body HTML (optional)</label><textarea rows="2" onchange="updateColumn(${idx}, 'body_html', this.value)">${escapeHtml(col.body_html || '')}</textarea></div><div class="column-links"><label style="font-weight: 600; margin-bottom: 8px; display: block;">Links</label>${(col.links || []).map((link, linkIdx) => `<div class="link-item"><input type="text" placeholder="Label" value="${escapeAttr(link.label)}" onchange="updateColumnLink(${idx}, ${linkIdx}, 'label', this.value)"><input type="text" placeholder="URL" value="${escapeAttr(link.href)}" onchange="updateColumnLink(${idx}, ${linkIdx}, 'href', this.value)"><button type="button" class="btn-delete" onclick="removeColumnLink(${idx}, ${linkIdx})">×</button></div>`).join('')}<button type="button" class="btn-add" style="padding: 4px 8px; font-size: 11px;" onclick="addColumnLink(${idx})">+ Link</button></div></div>`).join('');
    }

    function renderSocialLinks(data) {
        const iconOptions = [{value: 'fa fa-facebook', label: 'Facebook'}, {value: 'fa fa-twitter', label: 'Twitter/X'}, {value: 'fa fa-linkedin', label: 'LinkedIn'}, {value: 'fa fa-instagram', label: 'Instagram'}, {value: 'fa fa-youtube', label: 'YouTube'}, {value: 'fa fa-github', label: 'GitHub'}];
        document.getElementById('social-list').innerHTML = (data.social_links || []).map((link, idx) => `<div class="item-card"><div class="item-card-header"><span class="item-card-title"><i class="${escapeAttr(link.icon_class)}"></i> ${escapeHtml(link.aria_label)}</span><div class="item-card-actions"><button type="button" class="btn-delete" onclick="removeSocialLink(${idx})">Delete</button></div></div><div class="item-row"><div class="item-field"><label>Platform</label><select onchange="updateSocialLink(${idx}, 'icon_class', this.value); updateSocialLink(${idx}, 'aria_label', this.options[this.selectedIndex].text);">${iconOptions.map(opt => `<option value="${opt.value}" ${link.icon_class === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}</select></div><div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(link.href)}" onchange="updateSocialLink(${idx}, 'href', this.value)"></div></div></div>`).join('');
    }

    function renderFooterLinks(data, routes, isCmsRoute) {
        document.getElementById('footer-links-list').innerHTML = (data.footer_links || []).map((link, idx) => {
            const linkType = (link.type === 'app' && isCmsRoute(link.href)) ? 'cms' : (link.type || 'external');
            const typeSelector = `<div class="item-field" style="max-width: 120px;"><label>Type</label><select onchange="changeFooterLinkType(${idx}, this.value)"><option value="external" ${linkType === 'external' ? 'selected' : ''}>External</option><option value="app" ${linkType === 'app' ? 'selected' : ''}>App Route</option><option value="cms" ${linkType === 'cms' ? 'selected' : ''}>CMS Page</option></select></div>`;
            const urlField = linkType === 'app' ? selectField('App Route', 'selectFooterLinkAppRoute', idx, link.href, routes.appRoutes) : linkType === 'cms' ? selectField('CMS Page', 'selectFooterLinkCmsRoute', idx, link.href, routes.cmsRoutes) : `<div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(link.href)}" placeholder="https://example.com" onchange="updateFooterLink(${idx}, 'href', this.value)"></div>`;
            return `<div class="item-card"><div class="item-row">${typeSelector}<div class="item-field"><label>Label</label><input type="text" value="${escapeAttr(link.label)}" onchange="updateFooterLink(${idx}, 'label', this.value)"></div>${urlField}<div class="item-card-actions" style="align-self: flex-end; padding-bottom: 4px;"><button type="button" class="btn-delete" onclick="removeFooterLink(${idx})">Delete</button></div></div></div>`;
        }).join('');
    }

    function selectField(label, handlerName, idx, currentValue, options) {
        return `<div class="item-field"><label>${label}</label><select onchange="${handlerName}(${idx}, this.value)"><option value="">-- Select Page --</option>${options.map(route => `<option value="${escapeAttr(route.url)}" ${currentValue === route.url ? 'selected' : ''}>${escapeHtml(route.title)} (${escapeHtml(route.url)})</option>`).join('')}</select></div>`;
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
