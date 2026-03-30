(function () {
    const FONT_AWESOME_CSS = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css';

    function escapeHtml(val) {
        const div = document.createElement('div');
        div.textContent = val || '';
        return div.innerHTML;
    }

    function escapeAttr(val) {
        return String(val || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function renderFooterHtml(content) {
        const hasContent = content && ((content.cta_buttons || []).length || (content.contact_html || '').trim() || (content.columns || []).length || (content.social_links || []).length || (content.copyright || '').trim() || (content.footer_links || []).length);
        if (!hasContent) return '<div style="color:#666;font-style:italic;padding:40px;text-align:center;background:#f5f5f5;border-radius:4px;">No footer content yet. Add some content using the editor above.</div>';
        const cta = (content.cta_buttons || []).map(btn => `<div class="sb-col hb__buttons-${btn.style === 'gold' ? 'gold' : 'blue'}"><a class="btn--invert-${btn.style === 'gold' ? 'gold' : 'blue'} hb__play" href="${escapeAttr(btn.href)}" onclick="return false;">${escapeHtml(btn.label)}</a></div>`).join('');
        const contact = content.contact_html ? `<div class="i2gHome">${content.contact_html}</div>` : '';
        const ctaBlock = cta || contact ? `<div class="sb-row home-cta-row">${cta}${contact}</div>` : '';
        const columns = (content.columns || []).map((col, idx, arr) => `<div class="footer-column${idx === arr.length - 1 ? ' footer-column--address' : ''}">${col.title ? `<h2>${escapeHtml(col.title)}</h2>` : ''}${(col.links || []).length ? `<ul>${(col.links || []).map(link => `<li><a href="${escapeAttr(link.href)}" target="${escapeAttr(link.target || '_blank')}" rel="${escapeAttr(link.rel || 'noopener')}" onclick="return false;">${escapeHtml(link.label)}</a></li>`).join('')}</ul>` : ''}${col.body_html ? `<div class="footer-column__body">${col.body_html}</div>` : ''}${idx === arr.length - 1 && (content.social_links || []).length ? `<div class="socialIcons"><ul class="fa-ul inline">${(content.social_links || []).map(s => `<li class="fa-li"><a href="${escapeAttr(s.href)}" target="${escapeAttr(s.target || '_blank')}" rel="${escapeAttr(s.rel || 'noopener')}" aria-label="${escapeAttr(s.aria_label)}" onclick="return false;"><i class="${escapeAttr(s.icon_class)}"></i></a></li>`).join('')}</ul></div>` : ''}</div>`).join('');
        const footerLinks = (content.footer_links || []).map(link => `<li><a href="${escapeAttr(link.href)}" target="${escapeAttr(link.target || '_blank')}" rel="${escapeAttr(link.rel || 'noopener')}" onclick="return false;">${escapeHtml(link.label)}</a></li>`).join('');
        const footerBottom = (content.copyright || '').trim() || footerLinks ? `<div class="footer-bottom"><div class="footer-container"><ul class="footer-meta">${content.copyright ? `<li>${escapeHtml(content.copyright)}</li>` : ''}${footerLinks}</ul></div></div>` : '';
        return `${ctaBlock}<footer id="footer" class="site-footer" role="contentinfo">${columns ? `<div class="footer-main"><div class="footer-container"><div class="footer-columns">${columns}</div></div></div>` : ''}${footerBottom}</footer>`;
    }

    function updatePreview(iframe, errorBox, footerData) {
        if (!iframe) return;
        try {
            const inlineCSS = `* { box-sizing: border-box; } body { margin: 0; padding: 0; background: #fff; font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif; } .site-footer { background: #e5e6ea; color: #0b2653; width: 100%; margin-top: auto; } .footer-main { padding: 48px 0 60px; } .footer-container { width: 100%; max-width: 1180px; margin: 0 auto; padding: 0 24px; } .footer-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 32px 56px; } .footer-column h2 { font-size: 16px; margin: 0 0 18px; text-transform: uppercase; letter-spacing: 0.8px; color: #0b2653; } .footer-column ul { list-style: none; padding: 0; margin: 0; } .footer-column li + li { margin-top: 10px; } .footer-column a { font-size: 14px; text-decoration: none; color: #0b2653; transition: color 0.2s ease; } .footer-column a:hover { color: #04122d; text-decoration: underline; } .footer-column__body { color: #0b2653; font-size: 14px; line-height: 1.6; } .footer-column--address p { margin: 4px 0; color: #0b2653; } .socialIcons { margin-top: 20px; } .socialIcons .fa-ul { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 12px; } .socialIcons .fa-li { position: static; margin: 0; padding: 0; } .socialIcons a { width: 40px; height: 40px; border-radius: 50%; background: #0b2653; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 18px; text-decoration: none; transition: transform 0.2s ease, background 0.2s ease; } .socialIcons a:hover { background: #061432; transform: translateY(-2px); } .footer-bottom { background: #0b1f3f; border-top: 6px solid #d3a437; padding: 18px 0; } .footer-meta { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; justify-content: center; gap: 18px 28px; color: #fff; } .footer-meta li { font-size: 13px; color: #fff; } .footer-meta a { color: inherit; text-decoration: none; font-weight: 500; } .footer-meta a:hover { opacity: 0.75; } .home-cta-row { background: transparent; padding: 24px 0; } .sb-row { display: flex; flex-wrap: wrap; justify-content: center; gap: 16px; width: 100%; max-width: 960px; margin: 0 auto; padding: 0 20px; } .sb-col { display: flex; justify-content: center; } .hb__play { display: inline-flex; align-items: center; justify-content: center; border-radius: 0; border: 2px solid currentColor; padding: 10px 26px; font-size: 13px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; text-decoration: none; transition: background 0.2s ease, color 0.2s ease; } .btn--invert-gold { color: #936200; border-color: #d3a437; background: transparent; } .btn--invert-gold:hover { background: #d3a437; color: #0b1f3f; } .btn--invert-blue { color: #0b2653; border-color: #0b2653; background: transparent; } .btn--invert-blue:hover { background: #0b2653; color: #fff; } .i2gHome { font-size: 14px; line-height: 1.6; color: #0b2653; }`;
            const doc = iframe.contentDocument || iframe.contentWindow.document;
            doc.open();
            doc.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><link rel="stylesheet" href="${FONT_AWESOME_CSS}"><style>${inlineCSS}</style></head><body>${renderFooterHtml(footerData)}</body></html>`);
            doc.close();
            setTimeout(() => { try { iframe.style.height = Math.max(Math.max(doc.body.scrollHeight, doc.body.offsetHeight, doc.documentElement.scrollHeight) + 20, 300) + 'px'; } catch (e) {} }, 150);
            if (errorBox) errorBox.textContent = '';
        } catch (err) {
            if (errorBox) errorBox.textContent = 'Preview error: ' + err.message;
        }
    }

    window.ITGFooterPreview = { updatePreview: updatePreview };
})();
