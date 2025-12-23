/**
 * Menu Visual Editor
 * Handles the visual editing of menu items in Django admin
 */
(function() {
  // CSS paths - use the same CSS as frontend
  const MENU_CSS = '/static/layout/css/main-menu.css';
  const FRONTEND_CSS = ['/static/css/theme.css', '/static/css/custom.css'];
  const FONT_AWESOME_CSS = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css';
  
  // Get the hidden JSON input
  let jsonInput = document.getElementById('id_items') || document.querySelector('textarea[name="items"]');
  const iframe = document.getElementById('menu-preview-iframe');
  
  // Current data state
  let menuItems = [];
  
  // Available pages (will be populated via API)
  let availablePages = [];
  
  // Initialize
  async function init() {
    // Load available pages
    try {
      const response = await fetch('/api/pages/');
      if (response.ok) {
        const data = await response.json();
        availablePages = data.pages || data || [];
      }
    } catch (e) {
      console.log('Could not load pages list');
    }
    
    // Parse initial data
    if (jsonInput) {
      try {
        const parsed = JSON.parse(jsonInput.value || '[]');
        menuItems = Array.isArray(parsed) ? parsed : [];
      } catch (e) {
        console.error('Failed to parse initial JSON:', e);
        menuItems = [];
      }
    }
    
    // Ensure Home item always exists
    ensureHomeItem();
    
    renderAll();
    updatePreview();
  }
  
  // Ensure Home item exists (required)
  function ensureHomeItem() {
    if (!hasHomeItem()) {
      // Add Home item at the beginning
      menuItems.unshift({
        type: 'home',
        title: 'Home',
        icon: '',
        open_in_new_tab: false,
        children: []
      });
      syncToJson();
    }
  }
  
  // Render all items
  function renderAll() {
    const container = document.getElementById('menu-items-container');
    container.innerHTML = renderItems(menuItems, 'menuItems', true);
    document.getElementById('json-editor').value = JSON.stringify(menuItems, null, 2);
    
    // Hide "Add Home" button if Home already exists
    const addHomeBtn = document.getElementById('btn-add-home');
    if (addHomeBtn) {
      addHomeBtn.style.display = hasHomeItem() ? 'none' : 'inline-block';
    }
  }
  
  // Check if Home item exists in menu
  function hasHomeItem() {
    return menuItems.some(item => item.type === 'home');
  }
  
  // Render items recursively
  function renderItems(items, path, isTopLevel = true) {
    if (!items || items.length === 0) {
      return '<p style="color: #999; font-style: italic;">No menu items yet. Add items using the buttons below.</p>';
    }
    
    return items.map((item, idx) => {
      const itemPath = `${path}[${idx}]`;
      const hasChildren = item.children && item.children.length > 0;
      const typeBadgeClass = `type-${item.type}`;
      const typeLabel = item.type === 'home' ? 'Home' : item.type === 'page' ? 'Page' : 'External';
      const isHome = item.type === 'home';
      
      // Type selector - Home type cannot be changed at top level
      const canChangeType = !(isHome && isTopLevel);
      const typeSelector = canChangeType ? `
        <div class="item-field" style="max-width: 120px;">
          <label>Type</label>
          <select onchange="changeItemType('${itemPath}', this.value)">
            <option value="page" ${item.type === 'page' ? 'selected' : ''}>Page</option>
            <option value="external" ${item.type === 'external' ? 'selected' : ''}>External</option>
          </select>
        </div>
      ` : '';
      
      let fieldsHtml = '';
      
      if (item.type === 'home') {
        fieldsHtml = `
          <div class="item-row">
            <div class="item-field">
              <label>Title</label>
              <input type="text" value="${escapeAttr(item.title)}" onchange="updateItem('${itemPath}', 'title', this.value)">
            </div>
            <div class="item-field item-field-small">
              <label>Icon (optional)</label>
              <input type="text" value="${escapeAttr(item.icon || '')}" placeholder="fa-home" onchange="updateItem('${itemPath}', 'icon', this.value)">
            </div>
          </div>
        `;
      } else if (item.type === 'page') {
        const pageOptions = availablePages.map(p => 
          `<option value="${escapeAttr(p.slug)}" ${item.page_slug === p.slug ? 'selected' : ''}>${escapeHtml(p.title)} (/${p.slug})</option>`
        ).join('');
        
        fieldsHtml = `
          <div class="item-row">
            ${typeSelector}
            <div class="item-field">
              <label>Title</label>
              <input type="text" value="${escapeAttr(item.title)}" onchange="updateItem('${itemPath}', 'title', this.value)">
            </div>
            <div class="item-field">
              <label>Page</label>
              <select onchange="updateItem('${itemPath}', 'page_slug', this.value)">
                <option value="">-- Select Page --</option>
                ${pageOptions}
              </select>
            </div>
            <div class="item-field item-field-small">
              <label>Icon</label>
              <input type="text" value="${escapeAttr(item.icon || '')}" placeholder="fa-file" onchange="updateItem('${itemPath}', 'icon', this.value)">
            </div>
          </div>
        `;
      } else if (item.type === 'external') {
        fieldsHtml = `
          <div class="item-row">
            ${typeSelector}
            <div class="item-field">
              <label>Title</label>
              <input type="text" value="${escapeAttr(item.title)}" onchange="updateItem('${itemPath}', 'title', this.value)">
            </div>
            <div class="item-field">
              <label>URL</label>
              <input type="text" value="${escapeAttr(item.url || '')}" placeholder="https://example.com" onchange="updateItem('${itemPath}', 'url', this.value)">
            </div>
            <div class="item-field item-field-small">
              <label>Icon</label>
              <input type="text" value="${escapeAttr(item.icon || '')}" placeholder="fa-external-link" onchange="updateItem('${itemPath}', 'icon', this.value)">
            </div>
            <div class="item-field-checkbox">
              <input type="checkbox" id="newtab-${itemPath}" ${item.open_in_new_tab ? 'checked' : ''} onchange="updateItem('${itemPath}', 'open_in_new_tab', this.checked)">
              <label for="newtab-${itemPath}">New tab</label>
            </div>
          </div>
        `;
      }
      
      // Home items cannot have children
      const childrenHtml = (hasChildren && !isHome) ? `
        <div class="menu-children-container">
          ${renderItems(item.children, `${itemPath}.children`, false)}
        </div>
      ` : '';
      
      // Build action buttons - Home item cannot be deleted and cannot have children
      let actionButtons = '';
      if (idx > 0) {
        actionButtons += `<button type="button" class="btn-move" onclick="moveItem('${itemPath}', -1)">↑</button>`;
      }
      if (idx < items.length - 1) {
        actionButtons += `<button type="button" class="btn-move" onclick="moveItem('${itemPath}', 1)">↓</button>`;
      }
      // Only non-Home items can have children
      if (!isHome) {
        actionButtons += `<button type="button" class="btn-add-child" onclick="addChildItem('${itemPath}')">+ Child</button>`;
      }
      // Home item cannot be deleted (only at top level)
      if (!isHome || !isTopLevel) {
        actionButtons += `<button type="button" class="btn-delete" onclick="removeItem('${itemPath}')">Delete</button>`;
      } else {
        actionButtons += `<span class="btn-disabled" title="Home is required">Required</span>`;
      }
      
      return `
        <div class="menu-item-card ${hasChildren && !isHome ? 'has-children' : ''}${isHome && isTopLevel ? ' home-required' : ''}">
          <div class="menu-item-card-header">
            <span class="menu-item-card-title">
              <span class="menu-item-type-badge ${typeBadgeClass}">${typeLabel}</span>
              ${escapeHtml(item.title || 'Untitled')}
            </span>
            <div class="menu-item-card-actions">
              ${actionButtons}
            </div>
          </div>
          ${fieldsHtml}
          ${childrenHtml}
        </div>
      `;
    }).join('');
  }
  
  // Sync to hidden JSON field
  function syncToJson() {
    if (jsonInput) {
      jsonInput.value = JSON.stringify(menuItems);
    }
    document.getElementById('json-editor').value = JSON.stringify(menuItems, null, 2);
    updatePreview();
  }
  
  // Get item by path
  function getItemByPath(path) {
    return eval(path);
  }
  
  // Set item property by path
  function setItemProperty(path, property, value) {
    eval(`${path}.${property} = ${JSON.stringify(value)}`);
  }
  
  // Add menu item
  window.addMenuItem = function(type) {
    const newItem = {
      type: type,
      title: type === 'home' ? 'Home' : (type === 'page' ? 'New Page Link' : 'New External Link'),
      icon: '',
      open_in_new_tab: type === 'external',
      children: []
    };
    
    if (type === 'page') {
      newItem.page_slug = '';
    } else if (type === 'external') {
      newItem.url = '';
    }
    
    menuItems.push(newItem);
    renderAll();
    syncToJson();
  };
  
  // Add child item
  window.addChildItem = function(parentPath) {
    const parent = getItemByPath(parentPath);
    if (!parent.children) parent.children = [];
    
    parent.children.push({
      type: 'page',
      title: 'New Child Link',
      page_slug: '',
      icon: '',
      open_in_new_tab: false,
      children: []
    });
    
    renderAll();
    syncToJson();
  };
  
  // Update item property
  window.updateItem = function(path, property, value) {
    setItemProperty(path, property, value);
    renderAll();
    syncToJson();
  };
  
  // Change item type
  window.changeItemType = function(path, newType) {
    const item = getItemByPath(path);
    const oldType = item.type;
    
    if (oldType === newType) return;
    
    // Update type
    item.type = newType;
    
    // Reset type-specific fields
    if (newType === 'page') {
      item.page_slug = item.page_slug || '';
      delete item.url;
      item.open_in_new_tab = false;
    } else if (newType === 'external') {
      item.url = item.url || '';
      delete item.page_slug;
      item.open_in_new_tab = true;
    } else if (newType === 'home') {
      delete item.url;
      delete item.page_slug;
      item.open_in_new_tab = false;
      // Clear children for home type
      item.children = [];
    }
    
    renderAll();
    syncToJson();
  };
  
  // Remove item
  window.removeItem = function(path) {
    const match = path.match(/(.+)\[(\d+)\]$/);
    if (match) {
      const parentPath = match[1];
      const index = parseInt(match[2]);
      const parent = eval(parentPath);
      parent.splice(index, 1);
      renderAll();
      syncToJson();
    }
  };
  
  // Move item up or down
  window.moveItem = function(path, direction) {
    const match = path.match(/(.+)\[(\d+)\]$/);
    if (match) {
      const parentPath = match[1];
      const index = parseInt(match[2]);
      const parent = eval(parentPath);
      const newIndex = index + direction;
      
      if (newIndex >= 0 && newIndex < parent.length) {
        const item = parent.splice(index, 1)[0];
        parent.splice(newIndex, 0, item);
        renderAll();
        syncToJson();
      }
    }
  };
  
  // Toggle JSON view
  window.toggleJsonView = function() {
    document.getElementById('json-raw-view').classList.toggle('show');
  };
  
  // Helper functions
  function escapeHtml(val) {
    const div = document.createElement('div');
    div.textContent = val || '';
    return div.innerHTML;
  }
  
  function escapeAttr(val) {
    return String(val || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  
  // ===== Preview =====
  // Render menu items recursively with proper structure matching frontend
  function renderMenuItemsHtml(items, level) {
    if (!items || items.length === 0) {
      return '';
    }
    
    return items.map(item => {
      let href = '#';
      let targetAttr = '';
      
      if (item.type === 'home') {
        href = '/';
      } else if (item.type === 'page' && item.page_slug) {
        href = `/pages/${item.page_slug}`;
      } else if (item.type === 'external' && item.url) {
        href = item.url;
        if (item.open_in_new_tab) {
          targetAttr = ' target="_blank" rel="noopener noreferrer"';
        }
      }
      
      const icon = item.icon ? `<i class="fa ${item.icon}"></i> ` : '';
      const hasChildren = item.children && item.children.length > 0;
      
      if (level === 0) {
        // Top-level items
        let childrenHtml = '';
        if (hasChildren) {
          childrenHtml = `
            <div class="menu-sub-wrapper">
              <ul class="menu-sub">
                ${renderMenuItemsHtml(item.children, 1)}
              </ul>
            </div>
          `;
        }
        
        return `
          <li class="menu-item${hasChildren ? ' has-children' : ''}">
            <a href="${escapeAttr(href)}" class="menu-link"${targetAttr} onclick="return false;">
              ${icon}${escapeHtml(item.title)}
            </a>
            ${childrenHtml}
          </li>
        `;
      } else {
        // Submenu items
        let childrenHtml = '';
        if (hasChildren) {
          childrenHtml = `
            <div class="menu-sub-nested-wrapper">
              <ul class="menu-sub menu-sub-nested">
                ${renderMenuItemsHtml(item.children, level + 1)}
              </ul>
            </div>
          `;
        }
        
        return `
          <li class="menu-sub-item${hasChildren ? ' has-children' : ''}">
            <a href="${escapeAttr(href)}"${targetAttr} onclick="return false;">
              ${icon}${escapeHtml(item.title)}
              ${hasChildren ? '<span class="menu-arrow">›</span>' : ''}
            </a>
            ${childrenHtml}
          </li>
        `;
      }
    }).join('');
  }
  
  function renderMenuHtml(items) {
    if (!items || items.length === 0) {
      return '<div style="color:#666;font-style:italic;padding:20px;text-align:center;">No menu items</div>';
    }
    
    return `
      <nav class="menu-shell" aria-label="Main menu">
        <div class="menu-inner">
          <div class="menu-left">
            <div class="menu-logo">
              <a href="/" aria-label="Innovate to Grow">
                <img src="/static/images/i2glogo.png" alt="Logo" onerror="this.style.display='none'">
              </a>
            </div>
            <ul class="menu-list">
              ${renderMenuItemsHtml(items, 0)}
            </ul>
          </div>
        </div>
      </nav>
    `;
  }
  
  function updatePreview() {
    if (!iframe) return;
    
    try {
      const menuHtml = renderMenuHtml(menuItems);
      
      // Load the exact same CSS files as frontend
      const cssLinks = [
        ...FRONTEND_CSS.map(href => `<link rel="stylesheet" href="${href}">`),
        `<link rel="stylesheet" href="${MENU_CSS}">`
      ].join('\n');
      
      // Only minimal overrides for preview context
      const previewOverrides = `
        body {
          margin: 0;
          padding: 0;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
        }
        /* Show submenus on hover in preview */
        .menu-item:hover > .menu-sub-wrapper {
          display: block;
        }
        .menu-sub-item.has-children:hover > .menu-sub-nested-wrapper {
          display: block;
        }
      `;
      
      const fullHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  ${cssLinks}
  <link rel="stylesheet" href="${FONT_AWESOME_CSS}">
  <style>${previewOverrides}</style>
</head>
<body>
  ${menuHtml}
</body>
</html>`;
      
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      doc.open();
      doc.write(fullHtml);
      doc.close();
      
    } catch (err) {
      console.error('Preview error:', err);
    }
  }
  
  // Run on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
