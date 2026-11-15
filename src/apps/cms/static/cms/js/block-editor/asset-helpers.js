// The CMS asset picker's helpers (assets.js takes them from window.ITGCmsAssetPickerHelpers): its configuration,
// file-type and size helpers, the picker's markup, and inserting a chosen asset into the edited field. None of
// them touches the picker's state. Load after primitives.js and before assets.js.
(function () {
    const config = window.CMS_ASSET_MANAGER || {};
    const P = window.ITGCmsBlockPrimitives || {};
    const escapeHtml = P.escapeHtml || function (value) {
        const div = document.createElement('div');
        div.textContent = value || '';
        return div.innerHTML;
    };
    const escapeAttr = P.escapeAttr || function (value) {
        return String(value || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    };
    const imageExtensions = new Set((config.imageExtensions || []).map(ext => String(ext).toLowerCase()));

    function hasConfig() {
        return Boolean(config.listUrl && config.uploadUrl);
    }

    function extensionList(filter) {
        const extensions = filter === 'image' ? (config.imageExtensions || []) : (config.allowedExtensions || []);
        return extensions.map(ext => '.' + ext).join(',');
    }

    function csrfToken() {
        const el = document.querySelector('[name=csrfmiddlewaretoken]');
        if (el && el.value) return el.value;
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function closestElement(target, selector) {
        if (!target) return null;
        const element = target.nodeType === 1 ? target : target.parentElement;
        return element && element.closest ? element.closest(selector) : null;
    }

    function isImage(asset) {
        return Boolean(asset && (asset.is_image || imageExtensions.has(String(asset.extension || '').toLowerCase())));
    }

    function fileExtension(filename) {
        const parts = String(filename || '').toLowerCase().split('.');
        return parts.length > 1 ? parts.pop() : '';
    }

    function fileSize(size) {
        if (!size && size !== 0) return '';
        if (size < 1024) return size + ' B';
        if (size < 1024 * 1024) return Math.round(size / 1024) + ' KB';
        return (size / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function modalMarkup() {
        return `
            <div class="cms-asset-modal-backdrop" data-asset-action="close"></div>
            <div class="cms-asset-modal-panel" role="dialog" aria-modal="true" aria-labelledby="cms-asset-modal-title">
                <div class="cms-asset-modal-header">
                    <h3 id="cms-asset-modal-title">Insert CMS Asset</h3>
                    <button type="button" class="cms-asset-modal-close" data-asset-action="close" aria-label="Close">&times;</button>
                </div>
                <div class="cms-asset-upload">
                    <div class="cms-asset-upload-fields">
                        <div class="cms-asset-file-control">
                            <input type="file" id="cms-asset-upload-file" class="cms-asset-file-input">
                            <label for="cms-asset-upload-file" class="cms-asset-file-button">Choose file</label>
                            <span class="cms-asset-file-name" id="cms-asset-upload-filename">No file selected</span>
                        </div>
                        <input type="text" id="cms-asset-upload-name" placeholder="Optional display name">
                        <button type="button" id="cms-asset-upload-submit">Upload and insert</button>
                    </div>
                    <div class="cms-asset-upload-hint" id="cms-asset-upload-hint"></div>
                    <div class="cms-asset-error" id="cms-asset-error"></div>
                </div>
                <div class="cms-asset-search-row">
                    <input type="search" id="cms-asset-search" placeholder="Search assets">
                    <button type="button" id="cms-asset-search-submit">Search</button>
                </div>
                <div class="cms-asset-list" id="cms-asset-list"></div>
            </div>`;
    }

    function assetRowMarkup(asset, filter) {
        const image = isImage(asset);
        const unavailable = filter === 'image' && !image;
        const preview = image
            ? `<img src="${escapeAttr(asset.public_url)}" alt="${escapeAttr(asset.name)}" loading="lazy">`
            : `<span class="cms-asset-file-icon">${escapeHtml((asset.extension || 'file').toUpperCase())}</span>`;
        return `<div class="cms-asset-row${unavailable ? ' is-disabled' : ''}" data-asset-id="${escapeAttr(asset.id)}">
                <div class="cms-asset-thumb">${preview}</div>
                <div class="cms-asset-info">
                    <strong>${escapeHtml(asset.name)}</strong>
                    <span>${escapeHtml(asset.extension || 'file')}${asset.size ? ' · ' + escapeHtml(fileSize(asset.size)) : ''}</span>
                    <a href="${escapeAttr(asset.public_url)}" target="_blank" rel="noopener noreferrer">Open</a>
                </div>
                <button type="button" data-asset-action="select" data-asset-id="${escapeAttr(asset.id)}"${unavailable ? ' disabled' : ''}>Insert</button>
            </div>`;
    }

    function htmlSnippet(asset) {
        if (isImage(asset)) {
            return `<img src="${escapeAttr(asset.public_url)}" alt="${escapeAttr(asset.name)}" loading="lazy">`;
        }
        return `<a href="${escapeAttr(asset.public_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(asset.name)}</a>`;
    }

    function insertHtml(fieldId, html) {
        const field = document.getElementById(fieldId);
        if (!field) return;
        const cm = field._cmInstance;
        if (cm) {
            cm.replaceSelection(html);
            cm.focus();
            return;
        }
        const start = field.selectionStart || field.value.length;
        const end = field.selectionEnd || start;
        field.value = field.value.slice(0, start) + html + field.value.slice(end);
        field.dispatchEvent(new Event('input', { bubbles: true }));
        field.focus();
    }

    function insertUrl(target, url) {
        const field = document.getElementById(target.fieldId);
        if (field) {
            field.value = url;
            field.dispatchEvent(new Event('input', { bubbles: true }));
        } else if (window.updateBlockData) {
            window.updateBlockData(target.blockIdx, target.dataPath, url);
        }
    }

    window.ITGCmsAssetPickerHelpers = {
        config, imageExtensions, hasConfig, extensionList, csrfToken, closestElement, isImage, fileExtension,
        fileSize, modalMarkup, assetRowMarkup, htmlSnippet, insertHtml, insertUrl,
    };
})();
