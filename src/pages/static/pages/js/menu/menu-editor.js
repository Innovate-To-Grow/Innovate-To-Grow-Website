/**
 * Menu Visual Editor
 * Handles the visual editing of menu items in Django admin
 */
(function() {
  // CSS paths - use the same CSS as frontend
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
        href = `/${item.page_slug}`;
      } else if (item.type === 'external' && item.url) {
        href = item.url;
        if (item.open_in_new_tab) {
          targetAttr = ' target="_blank" rel="noopener noreferrer"';
        }
      }
      
      const icon = item.icon ? `<i class="fa ${item.icon}"></i> ` : '';
      const hasChildren = item.children && item.children.length > 0;
      
      if (level === 0) {
        // Top-level items - use new menu-bar classes
        let childrenHtml = '';
        if (hasChildren) {
          childrenHtml = `
            <div class="menu-dropdown is-open">
              ${renderMenuItemsHtml(item.children, 1)}
            </div>
          `;
        }
        
        return `
          <li class="menu-bar-item${hasChildren ? ' has-children is-open' : ''}">
            <a href="${escapeAttr(href)}" class="menu-bar-link"${targetAttr} onclick="return false;">
              ${icon}<span>${escapeHtml(item.title)}</span>
              ${hasChildren ? '<i class="fa fa-angle-down menu-bar-arrow"></i>' : ''}
            </a>
            ${childrenHtml}
          </li>
        `;
      } else {
        // Submenu items - use new dropdown classes
        let childrenHtml = '';
        if (hasChildren) {
          childrenHtml = `
            <div class="menu-dropdown-nested">
              ${renderMenuItemsHtml(item.children, level + 1)}
            </div>
          `;
        }
        
        return `
          <li class="menu-dropdown-item${hasChildren ? ' has-children' : ''}">
            <a href="${escapeAttr(href)}" class="menu-dropdown-link"${targetAttr} onclick="return false;">
              ${icon}<span>${escapeHtml(item.title)}</span>
              ${hasChildren ? '<i class="fa fa-angle-right menu-dropdown-arrow"></i>' : ''}
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
    
    // Get current date for display
    const date = new Date();
    const days = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
    const months = ['JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE', 'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER'];
    const currentDate = `${days[date.getDay()]} ${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
    
    return `
      <header class="site-header" role="banner">
        <!-- Top blue bar -->
        <div class="site-header-top">
          <div class="site-header-container site-header-top-inner">
            <a class="ucm-wordmark" href="#" onclick="return false;" aria-label="UC Merced">
              <img src="/static/images/ucmlogo.png" alt="UC Merced" onerror="this.parentElement.style.display='none'">
            </a>
            
            <a class="site-header-top-logo" href="#" onclick="return false;" aria-label="Innovate To Grow">
              <img class="site-header-top-logo-full" src="/static/images/I2G-fullname-low.png" alt="Innovate To Grow" onerror="this.style.display='none'">
            </a>
            
            <div class="site-header-top-links" aria-label="Quick links">
              <a href="#" onclick="return false;">Directory</a>
              <a href="#" onclick="return false;">Apply</a>
              <a href="#" onclick="return false;">Give</a>
            </div>
          </div>
        </div>
        
        <!-- White menu bar -->
        <div class="site-header-bottom">
          <div class="site-header-container site-header-bottom-inner">
            <div class="site-header-bottom-left">
              <a class="site-header-badge" href="#" onclick="return false;" aria-label="Home">
                <img src="/static/images/i2glogo.png" alt="Innovate To Grow" onerror="this.style.display='none'">
              </a>
              
              <nav class="site-header-nav" aria-label="Main menu">
                <ul class="menu-bar-list">
                  ${renderMenuItemsHtml(items, 0)}
                </ul>
              </nav>
            </div>
            
            <div class="site-header-date" aria-label="Current date">
              ${currentDate}
            </div>
          </div>
        </div>
      </header>
    `;
  }
  
  function updatePreview() {
    if (!iframe) return;
    
    try {
      const menuHtml = renderMenuHtml(menuItems);
      
      // Inline CSS to ensure it works in the iframe
      const inlineCSS = `
        :root {
          --header-navy: #003366;
          --header-navy-dark: #0b1f3f;
          --header-gold: #daa520;
          --header-text: #003366;
          --header-bg: #ffffff;
          --dropdown-bg: #f5f5f5;
          --dropdown-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
        }
        
        * { box-sizing: border-box; }
        body { margin: 0; padding: 0; font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; background: #f5f5f5; }
        
        .site-header { position: relative; z-index: 1000; }
        .site-header-container { width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 24px; }
        
        /* Top bar */
        .site-header-top { background: var(--header-navy-dark); border-bottom: 4px solid var(--header-gold); }
        .site-header-top-inner { height: 60px; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
        .ucm-wordmark { display: flex; align-items: center; text-decoration: none; flex-shrink: 0; }
        .ucm-wordmark img { height: 32px; width: auto; display: block; }
        .site-header-top-logo { display: flex; align-items: center; justify-content: center; text-decoration: none; flex: 1; }
        .site-header-top-logo img { height: 36px; width: auto; display: block; }
        .site-header-top-links { display: flex; align-items: center; gap: 24px; flex-shrink: 0; }
        .site-header-top-links a { color: #fff; text-decoration: none; font-size: 14px; font-weight: 600; }
        .site-header-top-links a:hover { text-decoration: underline; }
        
        /* Bottom menu bar */
        .site-header-bottom { background: var(--header-bg); border-bottom: 1px solid #e0e0e0; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08); }
        .site-header-bottom-inner { height: 47px; display: flex; align-items: center; justify-content: space-between; gap: 32px; }
        .site-header-bottom-left { display: flex; align-items: center; gap: 20px; min-width: 0; flex: 1; }
        .site-header-badge { display: flex; align-items: center; justify-content: center; text-decoration: none; flex: 0 0 auto; }
        .site-header-badge img { width: 38px; height: 38px; border-radius: 50%; display: block; object-fit: cover; border: 2px solid var(--header-gold); box-shadow: 0 2px 8px rgba(0, 0, 0, 0.12); }
        .site-header-nav { flex: 1; display: flex; justify-content: flex-start; min-width: 0; }
        .site-header-date { flex: 0 0 auto; font-size: 11px; font-weight: 600; color: var(--header-text); letter-spacing: 1px; text-transform: uppercase; white-space: nowrap; opacity: 0.7; }
        
        /* Menu items */
        .menu-bar-list { display: flex; align-items: center; list-style: none; margin: 0; padding: 0; gap: 28px; }
        .menu-bar-item { position: relative; }
        .menu-bar-link { display: inline-flex; align-items: center; gap: 5px; padding: 8px 0; color: var(--header-text); text-decoration: none; font-size: 15px; font-weight: 700; line-height: 1.2; letter-spacing: 0.2px; white-space: nowrap; position: relative; }
        .menu-bar-link::after { content: ''; position: absolute; bottom: 4px; left: 0; right: 0; height: 2px; background: var(--header-gold); transform: scaleX(0); transition: transform 0.25s ease; }
        .menu-bar-link:hover::after, .menu-bar-item.is-open > .menu-bar-link::after { transform: scaleX(1); }
        .menu-bar-arrow { font-size: 11px; opacity: 0.6; margin-left: 2px; }
        
        /* Dropdowns */
        .menu-dropdown { position: absolute; top: 100%; left: 0; min-width: 220px; background: var(--dropdown-bg); border-left: 3px solid var(--header-gold); box-shadow: var(--dropdown-shadow); padding: 12px 0; margin-top: 8px; z-index: 1100; }
        .menu-dropdown.is-open { display: block; }
        .menu-dropdown-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
        .menu-dropdown-item { position: relative; }
        .menu-dropdown-link { display: flex; align-items: center; gap: 10px; padding: 10px 20px; color: var(--header-text); text-decoration: none; font-size: 14px; font-weight: 700; font-style: italic; white-space: nowrap; }
        .menu-dropdown-link:hover { background: rgba(0, 51, 102, 0.06); padding-left: 24px; }
        .menu-dropdown-arrow { margin-left: auto; color: #888; font-size: 11px; }
        .menu-dropdown-nested { position: absolute; top: 0; left: 100%; min-width: 200px; background: var(--header-bg); border-left: 3px solid var(--header-gold); box-shadow: var(--dropdown-shadow); padding: 8px 0; z-index: 1101; display: none; }
        .menu-dropdown-item.has-children:hover > .menu-dropdown-nested { display: block; }
      `;
      
      const fullHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="${FONT_AWESOME_CSS}">
  <style>${inlineCSS}</style>
</head>
<body>
  ${menuHtml}
</body>
</html>`;
      
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      doc.open();
      doc.write(fullHtml);
      doc.close();
      
      // Adjust iframe height
      setTimeout(() => {
        try {
          const height = Math.max(doc.body.scrollHeight, doc.body.offsetHeight, doc.documentElement.scrollHeight);
          iframe.style.height = Math.max(height + 20, 200) + 'px';
        } catch (e) {}
      }, 150);
      
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
