/**
 * Footer Content Visual Editor
 * Handles the visual editing of footer content in Django admin
 */
(function() {
  // CSS paths
  const FONT_AWESOME_CSS = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css';
  
  // Get the hidden JSON input
  let jsonInput = document.getElementById('id_content') || document.querySelector('textarea[name="content"]');
  const iframe = document.getElementById('footer-preview-iframe');
  const errorBox = document.getElementById('footer-preview-error');
  
  // Current data state
  let footerData = {
    cta_buttons: [],
    contact_html: '',
    columns: [],
    social_links: [],
    copyright: '',
    footer_links: []
  };
  
  // Initialize
  function init() {
    if (jsonInput) {
      try {
        const parsed = JSON.parse(jsonInput.value || '{}');
        footerData = { ...footerData, ...parsed };
      } catch (e) {
        console.error('Failed to parse initial JSON:', e);
      }
    }
    
    // Set up tab switching
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.editor-section').forEach(s => s.classList.remove('active'));
        btn.classList.add('active');
        document.getElementById('section-' + btn.dataset.tab).classList.add('active');
      });
    });
    
    // Set up input listeners
    document.getElementById('contact-html-input').addEventListener('input', (e) => {
      footerData.contact_html = e.target.value;
      syncToJson();
    });
    
    document.getElementById('copyright-input').addEventListener('input', (e) => {
      footerData.copyright = e.target.value;
      syncToJson();
    });
    
    renderAll();
    updatePreview();
  }
  
  // Render all sections
  function renderAll() {
    renderCtaButtons();
    renderColumns();
    renderSocialLinks();
    renderFooterLinks();
    
    document.getElementById('contact-html-input').value = footerData.contact_html || '';
    document.getElementById('copyright-input').value = footerData.copyright || '';
    document.getElementById('json-editor').value = JSON.stringify(footerData, null, 2);
  }
  
  // Sync to hidden JSON field
  function syncToJson() {
    if (jsonInput) {
      jsonInput.value = JSON.stringify(footerData);
    }
    document.getElementById('json-editor').value = JSON.stringify(footerData, null, 2);
    updatePreview();
  }
  
  // ===== CTA Buttons =====
  window.addCtaButton = function() {
    footerData.cta_buttons.push({ label: 'New Button', href: '#', style: 'blue' });
    renderCtaButtons();
    syncToJson();
  };
  
  window.removeCtaButton = function(idx) {
    footerData.cta_buttons.splice(idx, 1);
    renderCtaButtons();
    syncToJson();
  };
  
  function renderCtaButtons() {
    const container = document.getElementById('cta-list');
    container.innerHTML = footerData.cta_buttons.map((btn, idx) => `
      <div class="item-card">
        <div class="item-card-header">
          <span class="item-card-title">Button ${idx + 1}</span>
          <div class="item-card-actions">
            <button type="button" class="btn-delete" onclick="removeCtaButton(${idx})">Delete</button>
          </div>
        </div>
        <div class="item-row">
          <div class="item-field">
            <label>Label</label>
            <input type="text" value="${escapeAttr(btn.label)}" onchange="updateCtaButton(${idx}, 'label', this.value)">
          </div>
          <div class="item-field">
            <label>URL</label>
            <input type="text" value="${escapeAttr(btn.href)}" onchange="updateCtaButton(${idx}, 'href', this.value)">
          </div>
          <div class="item-field" style="max-width: 120px;">
            <label>Style</label>
            <select onchange="updateCtaButton(${idx}, 'style', this.value)">
              <option value="blue" ${btn.style === 'blue' ? 'selected' : ''}>Blue</option>
              <option value="gold" ${btn.style === 'gold' ? 'selected' : ''}>Gold</option>
            </select>
          </div>
        </div>
      </div>
    `).join('');
  }
  
  window.updateCtaButton = function(idx, field, value) {
    footerData.cta_buttons[idx][field] = value;
    syncToJson();
  };
  
  // ===== Columns =====
  window.addColumn = function() {
    footerData.columns.push({ title: 'New Column', links: [], body_html: '' });
    renderColumns();
    syncToJson();
  };
  
  window.removeColumn = function(idx) {
    footerData.columns.splice(idx, 1);
    renderColumns();
    syncToJson();
  };
  
  window.addColumnLink = function(colIdx) {
    footerData.columns[colIdx].links = footerData.columns[colIdx].links || [];
    footerData.columns[colIdx].links.push({ label: 'New Link', href: '#', target: '_blank', rel: 'noopener' });
    renderColumns();
    syncToJson();
  };
  
  window.removeColumnLink = function(colIdx, linkIdx) {
    footerData.columns[colIdx].links.splice(linkIdx, 1);
    renderColumns();
    syncToJson();
  };
  
  window.updateColumn = function(idx, field, value) {
    footerData.columns[idx][field] = value;
    syncToJson();
  };
  
  window.updateColumnLink = function(colIdx, linkIdx, field, value) {
    footerData.columns[colIdx].links[linkIdx][field] = value;
    syncToJson();
  };
  
  function renderColumns() {
    const container = document.getElementById('columns-list');
    container.innerHTML = footerData.columns.map((col, idx) => `
      <div class="item-card">
        <div class="item-card-header">
          <span class="item-card-title">Column ${idx + 1}: ${escapeHtml(col.title || 'Untitled')}</span>
          <div class="item-card-actions">
            <button type="button" class="btn-delete" onclick="removeColumn(${idx})">Delete</button>
          </div>
        </div>
        <div class="item-row">
          <div class="item-field">
            <label>Title</label>
            <input type="text" value="${escapeAttr(col.title)}" onchange="updateColumn(${idx}, 'title', this.value)">
          </div>
        </div>
        <div class="item-field">
          <label>Body HTML (optional)</label>
          <textarea rows="2" onchange="updateColumn(${idx}, 'body_html', this.value)">${escapeHtml(col.body_html || '')}</textarea>
        </div>
        <div class="column-links">
          <label style="font-weight: 600; margin-bottom: 8px; display: block;">Links</label>
          ${(col.links || []).map((link, linkIdx) => `
            <div class="link-item">
              <input type="text" placeholder="Label" value="${escapeAttr(link.label)}" onchange="updateColumnLink(${idx}, ${linkIdx}, 'label', this.value)">
              <input type="text" placeholder="URL" value="${escapeAttr(link.href)}" onchange="updateColumnLink(${idx}, ${linkIdx}, 'href', this.value)">
              <button type="button" class="btn-delete" onclick="removeColumnLink(${idx}, ${linkIdx})">×</button>
            </div>
          `).join('')}
          <button type="button" class="btn-add" style="padding: 4px 8px; font-size: 11px;" onclick="addColumnLink(${idx})">+ Link</button>
        </div>
      </div>
    `).join('');
  }
  
  // ===== Social Links =====
  window.addSocialLink = function() {
    footerData.social_links.push({
      href: '#',
      icon_class: 'fa fa-facebook',
      aria_label: 'Facebook',
      target: '_blank',
      rel: 'noopener'
    });
    renderSocialLinks();
    syncToJson();
  };
  
  window.removeSocialLink = function(idx) {
    footerData.social_links.splice(idx, 1);
    renderSocialLinks();
    syncToJson();
  };
  
  window.updateSocialLink = function(idx, field, value) {
    footerData.social_links[idx][field] = value;
    syncToJson();
  };
  
  function renderSocialLinks() {
    const container = document.getElementById('social-list');
    const iconOptions = [
      { value: 'fa fa-facebook', label: 'Facebook' },
      { value: 'fa fa-twitter', label: 'Twitter/X' },
      { value: 'fa fa-linkedin', label: 'LinkedIn' },
      { value: 'fa fa-instagram', label: 'Instagram' },
      { value: 'fa fa-youtube', label: 'YouTube' },
      { value: 'fa fa-github', label: 'GitHub' }
    ];
    
    container.innerHTML = footerData.social_links.map((link, idx) => `
      <div class="item-card">
        <div class="item-card-header">
          <span class="item-card-title"><i class="${link.icon_class}"></i> ${escapeHtml(link.aria_label)}</span>
          <div class="item-card-actions">
            <button type="button" class="btn-delete" onclick="removeSocialLink(${idx})">Delete</button>
          </div>
        </div>
        <div class="item-row">
          <div class="item-field">
            <label>Platform</label>
            <select onchange="updateSocialLink(${idx}, 'icon_class', this.value); updateSocialLink(${idx}, 'aria_label', this.options[this.selectedIndex].text);">
              ${iconOptions.map(opt => `<option value="${opt.value}" ${link.icon_class === opt.value ? 'selected' : ''}>${opt.label}</option>`).join('')}
            </select>
          </div>
          <div class="item-field">
            <label>URL</label>
            <input type="text" value="${escapeAttr(link.href)}" onchange="updateSocialLink(${idx}, 'href', this.value)">
          </div>
        </div>
      </div>
    `).join('');
  }
  
  // ===== Footer Links =====
  window.addFooterLink = function() {
    footerData.footer_links.push({ label: 'New Link', href: '#', target: '_blank', rel: 'noopener' });
    renderFooterLinks();
    syncToJson();
  };
  
  window.removeFooterLink = function(idx) {
    footerData.footer_links.splice(idx, 1);
    renderFooterLinks();
    syncToJson();
  };
  
  window.updateFooterLink = function(idx, field, value) {
    footerData.footer_links[idx][field] = value;
    syncToJson();
  };
  
  function renderFooterLinks() {
    const container = document.getElementById('footer-links-list');
    container.innerHTML = footerData.footer_links.map((link, idx) => `
      <div class="item-card">
        <div class="item-row">
          <div class="item-field">
            <label>Label</label>
            <input type="text" value="${escapeAttr(link.label)}" onchange="updateFooterLink(${idx}, 'label', this.value)">
          </div>
          <div class="item-field">
            <label>URL</label>
            <input type="text" value="${escapeAttr(link.href)}" onchange="updateFooterLink(${idx}, 'href', this.value)">
          </div>
          <div class="item-card-actions" style="align-self: flex-end; padding-bottom: 4px;">
            <button type="button" class="btn-delete" onclick="removeFooterLink(${idx})">Delete</button>
          </div>
        </div>
      </div>
    `).join('');
  }
  
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
  function renderFooterHtml(content) {
    if (!content || Object.keys(content).length === 0) {
      return '<div style="color:#666;font-style:italic;padding:40px;text-align:center;">No content</div>';
    }

    // CTA buttons section
    const cta = (content.cta_buttons || []).map(btn => {
      const color = btn.style === 'gold' ? 'gold' : 'blue';
      return `<div class="sb-col hb__buttons-${color}"><a class="btn--invert-${color} hb__play" href="${escapeAttr(btn.href)}" onclick="return false;">${escapeHtml(btn.label)}</a></div>`;
    }).join('');

    const contact = content.contact_html ? `<div class="i2gHome">${content.contact_html}</div>` : '';
    const ctaBlock = (cta || contact) ? `<div class="sb-row home-cta-row">${cta}${contact}</div>` : '';

    // Footer columns - using new structure matching Footer.tsx
    const columns = (content.columns || []).map((col, idx, arr) => {
      const isAddressColumn = idx === arr.length - 1;
      
      // Links
      const links = (col.links || []).map(link => 
        `<li><a href="${escapeAttr(link.href)}" target="${escapeAttr(link.target || '_blank')}" rel="${escapeAttr(link.rel || 'noopener')}" onclick="return false;">${escapeHtml(link.label)}</a></li>`
      ).join('');
      const linkList = links ? `<ul>${links}</ul>` : '';
      
      // Body HTML
      const body = col.body_html ? `<div class="footer-column__body">${col.body_html}</div>` : '';
      
      // Social icons (only in last column)
      const social = (isAddressColumn && (content.social_links || []).length) ? `
        <div class="socialIcons">
          <ul class="fa-ul inline">
            ${(content.social_links || []).map(s => 
              `<li class="fa-li"><a href="${escapeAttr(s.href)}" target="${escapeAttr(s.target || '_blank')}" rel="${escapeAttr(s.rel || 'noopener')}" aria-label="${escapeAttr(s.aria_label)}" onclick="return false;"><i class="${escapeAttr(s.icon_class)}"></i></a></li>`
            ).join('')}
          </ul>
        </div>
      ` : '';
      
      const title = col.title ? `<h2>${escapeHtml(col.title)}</h2>` : '';
      const columnClass = `footer-column${isAddressColumn ? ' footer-column--address' : ''}`;
      
      return `<div class="${columnClass}">${title}${linkList}${body}${social}</div>`;
    }).join('');

    // Footer main section
    const columnsBlock = columns ? `
      <div class="footer-main">
        <div class="footer-container">
          <div class="footer-columns">
            ${columns}
          </div>
        </div>
      </div>
    ` : '';

    // Footer bottom bar
    const footerLinks = (content.footer_links || []).map(l => 
      `<li><a href="${escapeAttr(l.href)}" target="${escapeAttr(l.target || '_blank')}" rel="${escapeAttr(l.rel || 'noopener')}" onclick="return false;">${escapeHtml(l.label)}</a></li>`
    ).join('');
    const copyright = content.copyright ? `<li>${escapeHtml(content.copyright)}</li>` : '';
    
    const hasFooterLinks = (content.footer_links || []).length > 0;
    const hasCopyright = Boolean(content.copyright);
    const shouldShowFooterBottom = hasFooterLinks || hasCopyright;
    
    const footerBottomBlock = shouldShowFooterBottom ? `
      <div class="footer-bottom">
        <div class="footer-container">
          <ul class="footer-meta">
            ${copyright}${footerLinks}
          </ul>
        </div>
      </div>
    ` : '';

    return `
      ${ctaBlock}
      <footer id="footer" class="site-footer" role="contentinfo">
        ${columnsBlock}
        ${footerBottomBlock}
      </footer>
    `;
  }
  
  function updatePreview() {
    if (!iframe) return;
    
    try {
      const footerHtml = renderFooterHtml(footerData);
      
      // Inline CSS to ensure it works in the iframe
      const inlineCSS = `
        * { box-sizing: border-box; }
        body { margin: 0; padding: 0; background: #fff; font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; }
        
        .site-footer { background: #e5e6ea; color: #0b2653; width: 100%; margin-top: auto; }
        .footer-main { padding: 48px 0 60px; }
        .footer-container { width: 100%; max-width: 1180px; margin: 0 auto; padding: 0 24px; }
        .footer-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 32px 56px; }
        .footer-column h2 { font-size: 16px; margin: 0 0 18px; text-transform: uppercase; letter-spacing: 0.8px; color: #0b2653; }
        .footer-column ul { list-style: none; padding: 0; margin: 0; }
        .footer-column li + li { margin-top: 10px; }
        .footer-column a { font-size: 14px; text-decoration: none; color: #0b2653; transition: color 0.2s ease; }
        .footer-column a:hover { color: #04122d; text-decoration: underline; }
        .footer-column__body { color: #0b2653; font-size: 14px; line-height: 1.6; }
        .footer-column--address p { margin: 4px 0; color: #0b2653; }
        
        .socialIcons { margin-top: 20px; }
        .socialIcons .fa-ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 12px; }
        .socialIcons .fa-li { position: static; margin: 0; padding: 0; }
        .socialIcons a { width: 40px; height: 40px; border-radius: 50%; background: #0b2653; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 18px; text-decoration: none; transition: transform 0.2s ease, background 0.2s ease; }
        .socialIcons a:hover { background: #061432; transform: translateY(-2px); }
        
        .footer-bottom { background: #0b1f3f; border-top: 6px solid #d3a437; padding: 18px 0; }
        .footer-meta { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 18px 28px; color: #fff; }
        .footer-meta li { font-size: 13px; color: #fff; }
        .footer-meta a { color: inherit; text-decoration: none; font-weight: 500; }
        .footer-meta a:hover { opacity: 0.75; }
        
        .home-cta-row { background: transparent; padding: 24px 0; }
        .sb-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 16px; width: 100%; max-width: 960px; margin: 0 auto; padding: 0 20px; }
        .sb-col { display: flex; justify-content: center; }
        .hb__play { display: inline-flex; align-items: center; justify-content: center; border-radius: 0; border: 2px solid currentColor; padding: 10px 26px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; text-decoration: none; transition: background 0.2s ease, color 0.2s ease; }
        .btn--invert-gold { color: #936200; border-color: #d3a437; background: transparent; }
        .btn--invert-gold:hover { background: #d3a437; color: #0b1f3f; }
        .btn--invert-blue { color: #0b2653; border-color: #0b2653; background: transparent; }
        .btn--invert-blue:hover { background: #0b2653; color: #fff; }
        .i2gHome { font-size: 14px; line-height: 1.6; color: #0b2653; }
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
  ${footerHtml}
</body>
</html>`;
      
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      doc.open();
      doc.write(fullHtml);
      doc.close();
      
      setTimeout(() => {
        try {
          const height = Math.max(doc.body.scrollHeight, doc.body.offsetHeight, doc.documentElement.scrollHeight);
          iframe.style.height = Math.max(height + 20, 300) + 'px';
        } catch (e) {}
      }, 150);
      
      if (errorBox) errorBox.textContent = '';
    } catch (err) {
      if (errorBox) errorBox.textContent = 'Preview error: ' + err.message;
    }
  }
  
  // Run on load
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
