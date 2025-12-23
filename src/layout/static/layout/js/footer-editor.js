/**
 * Footer Content Visual Editor
 * Handles the visual editing of footer content in Django admin
 */
(function() {
  // Frontend CSS paths
  const FRONTEND_CSS = ['/static/css/theme.css', '/static/css/custom.css'];
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

    const cta = (content.cta_buttons || []).map(btn => {
      const color = btn.style === 'gold' ? 'gold' : 'blue';
      return `<div class="sb-col hb__buttons-${color}"><a class="btn--invert-${color} hb__play" href="${escapeAttr(btn.href)}" onclick="return false;">${escapeHtml(btn.label)}</a></div>`;
    }).join('');

    const contact = content.contact_html ? `<div class="i2gHome">${content.contact_html}</div>` : '';
    const ctaBlock = (cta || contact) ? `<div class="home-bottom-cta"><div class="container"><div class="sb-row home-cta-row">${cta}</div>${contact}</div></div>` : '';

    const columns = (content.columns || []).map((col, idx, arr) => {
      const links = (col.links || []).map(link => `<li><a href="${escapeAttr(link.href)}" target="${escapeAttr(link.target || '_blank')}" rel="${escapeAttr(link.rel || 'noopener')}" onclick="return false;">${escapeHtml(link.label)}</a></li>`).join('');
      const linkList = links ? `<ul>${links}</ul>` : '';
      const body = col.body_html ? `<div>${col.body_html}</div>` : '';
      
      const social = (idx === arr.length - 1 && (content.social_links || []).length) ? `
        <div class="socialIcons">
          <ul>
            ${(content.social_links || []).map(s => `<li><a href="${escapeAttr(s.href)}" target="${escapeAttr(s.target || '_blank')}" rel="${escapeAttr(s.rel || 'noopener')}" aria-label="${escapeAttr(s.aria_label)}" onclick="return false;"><i class="${escapeAttr(s.icon_class)}"></i></a></li>`).join('')}
          </ul>
        </div>
      ` : '';
      
      const title = col.title ? `<h2>${escapeHtml(col.title)}</h2>` : '';
      const isLast = idx === arr.length - 1;
      return `<div class="fColumn${isLast ? ' fAddress' : ''}">${title}${linkList}${body}${social}</div>`;
    }).join('');

    const columnBlock = columns ? `<div class="final-foot"><div class="container"><div class="footer-links">${columns}</div></div></div>` : '';

    const footerLinks = (content.footer_links || []).map(l => `<li><a href="${escapeAttr(l.href)}" target="${escapeAttr(l.target || '_blank')}" rel="${escapeAttr(l.rel || 'noopener')}" onclick="return false;">${escapeHtml(l.label)}</a></li>`).join('');
    const copyright = content.copyright ? `<li>${escapeHtml(content.copyright)}</li>` : '';
    const copyBlock = (copyright || footerLinks) ? `<div class="copyright"><div class="container"><ul>${copyright}${footerLinks}</ul></div></div>` : '';

    return `${ctaBlock}<div id="footer" class="clearfix site-footer" role="contentinfo">${columnBlock}${copyBlock}</div>`;
  }
  
  function updatePreview() {
    if (!iframe) return;
    
    try {
      const footerHtml = renderFooterHtml(footerData);
      const cssLinks = FRONTEND_CSS.map(href => `<link rel="stylesheet" href="${href}">`).join('\n');
      
      const previewStyles = `
        body { margin: 0; padding: 0; background: #fff; }
      `;
      
      const fullHtml = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  ${cssLinks}
  <link rel="stylesheet" href="${FONT_AWESOME_CSS}">
  <style>${previewStyles}</style>
</head>
<body class="html front not-logged-in no-sidebars page-node">
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
