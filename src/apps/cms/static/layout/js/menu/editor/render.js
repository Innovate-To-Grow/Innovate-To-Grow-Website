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

    function safeItemType(item) {
        return ['home', 'external', 'app'].includes(item.type) ? item.type : 'app';
    }

    function renderItems(items, path, routes, isTopLevel = true) {
        if (!items || items.length === 0) return '<p style="color: #999; font-style: italic;">No menu items yet. Add items using the buttons below.</p>';
        return items.map((item, idx) => {
            const itemPath = `${path}[${idx}]`;
            const itemType = safeItemType(item);
            const hasChildren = item.children && item.children.length > 0;
            const isCmsPage = itemType === 'app' && routes.cmsRoutes.some(route => route.url === item.url);
            const typeBadgeClass = isCmsPage ? 'type-cms' : `type-${itemType}`;
            const typeLabel = itemType === 'home' ? 'Home' : itemType === 'external' ? 'External' : isCmsPage ? 'CMS Page' : 'App';
            const typeSelector = `<div class="item-field" style="max-width: 120px;"><label>Type</label><select ${actionAttrs('changeItemType', 'change', [itemPath], 'value')}><option value="home" ${itemType === 'home' ? 'selected' : ''}>Home</option><option value="app" ${itemType === 'app' ? 'selected' : ''}>${isCmsPage ? 'CMS Page' : 'App Route'}</option><option value="external" ${itemType === 'external' ? 'selected' : ''}>External</option></select></div>`;
            const fieldsHtml = itemType === 'home' ? renderHomeFields(item, itemPath, typeSelector) : itemType === 'external' ? renderExternalFields(item, itemPath, typeSelector) : renderAppFields(item, itemPath, typeSelector, routes);
            const childrenHtml = hasChildren ? `<div class="menu-children-container">${renderItems(item.children, `${itemPath}.children`, routes, false)}</div>` : '';
            let actionButtons = '';
            if (idx > 0) actionButtons += `<button type="button" class="btn-move" ${actionAttrs('moveItem', 'click', [itemPath, -1])}>↑</button>`;
            if (idx < items.length - 1) actionButtons += `<button type="button" class="btn-move" ${actionAttrs('moveItem', 'click', [itemPath, 1])}>↓</button>`;
            actionButtons += `<button type="button" class="btn-add-child" ${actionAttrs('addChildItem', 'click', [itemPath])}>+ Child</button><button type="button" class="btn-delete" ${actionAttrs('removeItem', 'click', [itemPath])}>Delete</button>`;
            return `<div class="menu-item-card ${hasChildren ? 'has-children' : ''}"><div class="menu-item-card-header"><span class="menu-item-card-title"><span class="menu-item-type-badge ${typeBadgeClass}">${typeLabel}</span>${escapeHtml(item.title || 'Untitled')}</span><div class="menu-item-card-actions">${actionButtons}</div></div>${fieldsHtml}${childrenHtml}</div>`;
        }).join('');
    }

    function renderHomeFields(item, itemPath, typeSelector) {
        return `<div class="item-row">${typeSelector}<div class="item-field"><label>Title</label><input type="text" value="${escapeAttr(item.title)}" ${actionAttrs('updateItem', 'change', [itemPath, 'title'], 'value')}></div><div class="item-field" style="flex: 0; white-space: nowrap;"><label>URL</label><span style="color: #666; font-size: 13px; padding: 6px 0; display: block;">/ (homepage)</span></div><div class="item-field item-field-small"><label>Icon</label><input type="text" value="${escapeAttr(item.icon || '')}" placeholder="fa-home" ${actionAttrs('updateItem', 'change', [itemPath, 'icon'], 'value')}></div></div>`;
    }

    function renderExternalFields(item, itemPath, typeSelector) {
        return `<div class="item-row">${typeSelector}<div class="item-field"><label>Title</label><input type="text" value="${escapeAttr(item.title)}" ${actionAttrs('updateItem', 'change', [itemPath, 'title'], 'value')}></div><div class="item-field"><label>URL</label><input type="text" value="${escapeAttr(item.url || '')}" placeholder="https://example.com" ${actionAttrs('updateItem', 'change', [itemPath, 'url'], 'value')}></div><div class="item-field item-field-small"><label>Icon</label><input type="text" value="${escapeAttr(item.icon || '')}" placeholder="fa-external-link" ${actionAttrs('updateItem', 'change', [itemPath, 'icon'], 'value')}></div><div class="item-field-checkbox"><input type="checkbox" id="newtab-${itemPath}" ${item.open_in_new_tab ? 'checked' : ''} ${actionAttrs('updateItem', 'change', [itemPath, 'open_in_new_tab'], 'checked')}><label for="newtab-${itemPath}">New tab</label></div></div>`;
    }

    function renderAppFields(item, itemPath, typeSelector, routes) {
        const appOptions = routes.appRoutes.map(route => `<option value="${escapeAttr(route.url)}" ${item.url === route.url ? 'selected' : ''}>${escapeHtml(route.title)} (${escapeHtml(route.url)})</option>`).join('');
        const cmsOptions = routes.cmsRoutes.map(route => `<option value="${escapeAttr(route.url)}" ${item.url === route.url ? 'selected' : ''}>${escapeHtml(route.title)} (${escapeHtml(route.url)})</option>`).join('');
        const knownUrl = !item.url || routes.allRoutes.some(route => route.url === item.url);
        const warningHtml = knownUrl ? '' : '<span style="color:#dc3545;font-size:12px;margin-left:4px;" title="This URL does not match any known route or CMS page">&#9888; Unknown route</span>';
        return `<div class="item-row">${typeSelector}<div class="item-field"><label>Title</label><input type="text" value="${escapeAttr(item.title)}" ${actionAttrs('updateItem', 'change', [itemPath, 'title'], 'value')}></div><div class="item-field"><label>Route${warningHtml}</label><select ${actionAttrs('selectAppRoute', 'change', [itemPath], 'value')}><option value="">-- Select Route --</option>${appOptions ? `<optgroup label="App Routes">${appOptions}</optgroup>` : ''}${cmsOptions ? `<optgroup label="CMS Pages">${cmsOptions}</optgroup>` : ''}</select></div><div class="item-field item-field-small"><label>Icon</label><input type="text" value="${escapeAttr(item.icon || '')}" placeholder="fa-calendar" ${actionAttrs('updateItem', 'change', [itemPath, 'icon'], 'value')}></div></div>`;
    }

    function renderMenuItemsHtml(items, level) {
        if (!items || items.length === 0) return '';
        return items.map(item => {
            const href = item.url || '#';
            const targetAttr = item.type === 'external' && item.open_in_new_tab ? ' target="_blank" rel="noopener noreferrer"' : '';
            const icon = item.icon ? `<i class="fa ${escapeAttr(item.icon)}"></i> ` : '';
            const hasChildren = item.children && item.children.length > 0;
            if (level === 0) {
                const childrenHtml = hasChildren ? `<div class="menu-dropdown is-open">${renderMenuItemsHtml(item.children, 1)}</div>` : '';
                return `<li class="menu-bar-item${hasChildren ? ' has-children is-open' : ''}"><a href="${escapeAttr(href)}" class="menu-bar-link" data-preview-link${targetAttr}>${icon}<span>${escapeHtml(item.title)}</span>${hasChildren ? '<i class="fa fa-angle-down menu-bar-arrow"></i>' : ''}</a>${childrenHtml}</li>`;
            }
            const childrenHtml = hasChildren ? `<div class="menu-dropdown-nested">${renderMenuItemsHtml(item.children, level + 1)}</div>` : '';
            return `<li class="menu-dropdown-item${hasChildren ? ' has-children' : ''}"><a href="${escapeAttr(href)}" class="menu-dropdown-link" data-preview-link${targetAttr}>${icon}<span>${escapeHtml(item.title)}</span>${hasChildren ? '<i class="fa fa-angle-right menu-dropdown-arrow"></i>' : ''}</a>${childrenHtml}</li>`;
        }).join('');
    }

    window.ITGMenuEditorRender = {
        renderAll: function (container, jsonEditor, menuItems, routes) {
            container.innerHTML = renderItems(menuItems, 'menuItems', routes, true);
            jsonEditor.value = JSON.stringify(menuItems, null, 2);
        },
    };
})();
