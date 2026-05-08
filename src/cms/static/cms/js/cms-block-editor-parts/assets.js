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
    const imageExtensions = new Set(config.imageExtensions || []);
    const state = { target: null, assets: [], query: '', loading: false };
    let modal = null;

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
        return Boolean(asset && (asset.is_image || imageExtensions.has(asset.extension)));
    }

    function fileSize(size) {
        if (!size && size !== 0) return '';
        if (size < 1024) return size + ' B';
        if (size < 1024 * 1024) return Math.round(size / 1024) + ' KB';
        return (size / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function ensureModal() {
        if (modal) return modal;
        modal = document.createElement('div');
        modal.className = 'cms-asset-modal';
        modal.innerHTML = `
            <div class="cms-asset-modal-backdrop" data-asset-action="close"></div>
            <div class="cms-asset-modal-panel" role="dialog" aria-modal="true" aria-labelledby="cms-asset-modal-title">
                <div class="cms-asset-modal-header">
                    <h3 id="cms-asset-modal-title">Insert CMS Asset</h3>
                    <button type="button" class="cms-asset-modal-close" data-asset-action="close" aria-label="Close">&times;</button>
                </div>
                <div class="cms-asset-upload">
                    <div class="cms-asset-upload-fields">
                        <input type="file" id="cms-asset-upload-file">
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
        document.body.appendChild(modal);
        modal.addEventListener('click', handleModalClick);
        modal.querySelector('#cms-asset-search').addEventListener('input', event => {
            state.query = event.target.value;
        });
        modal.querySelector('#cms-asset-search-submit').addEventListener('click', () => loadAssets());
        modal.querySelector('#cms-asset-upload-submit').addEventListener('click', uploadAsset);
        return modal;
    }

    function showError(message) {
        const el = modal && modal.querySelector('#cms-asset-error');
        if (!el) return;
        el.textContent = message || '';
        el.classList.toggle('is-visible', Boolean(message));
    }

    function openPicker(target) {
        if (!hasConfig()) {
            alert('CMS asset manager is not configured.');
            return;
        }
        state.target = target;
        ensureModal();
        showError('');
        modal.classList.add('is-open');
        const fileInput = modal.querySelector('#cms-asset-upload-file');
        const hint = modal.querySelector('#cms-asset-upload-hint');
        const search = modal.querySelector('#cms-asset-search');
        fileInput.value = '';
        fileInput.setAttribute('accept', extensionList(target.filter));
        modal.querySelector('#cms-asset-upload-name').value = '';
        hint.textContent = `Allowed: ${extensionList(target.filter) || 'configured CMS asset types'} · Max ${fileSize(config.maxBytes || 0)}`;
        search.value = state.query;
        loadAssets();
    }

    function closePicker() {
        if (modal) modal.classList.remove('is-open');
        state.target = null;
    }

    function loadAssets() {
        if (!modal || state.loading) return;
        state.loading = true;
        renderAssets();
        const url = new URL(config.listUrl, window.location.origin);
        if (state.query) url.searchParams.set('q', state.query);
        fetch(url.toString(), { credentials: 'same-origin' })
            .then(response => response.ok ? response.json() : Promise.reject(new Error('Unable to load assets.')))
            .then(data => {
                state.assets = Array.isArray(data.assets) ? data.assets : [];
                state.loading = false;
                renderAssets();
            })
            .catch(error => {
                state.loading = false;
                showError(error.message || 'Unable to load assets.');
                renderAssets();
            });
    }

    function renderAssets() {
        const list = modal && modal.querySelector('#cms-asset-list');
        if (!list) return;
        if (state.loading) {
            list.innerHTML = '<p class="cms-asset-empty">Loading assets...</p>';
            return;
        }
        if (!state.assets.length) {
            list.innerHTML = '<p class="cms-asset-empty">No assets found.</p>';
            return;
        }
        const filter = state.target && state.target.filter;
        list.innerHTML = state.assets.map(asset => {
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
        }).join('');
    }

    function uploadAsset() {
        const fileInput = modal.querySelector('#cms-asset-upload-file');
        const nameInput = modal.querySelector('#cms-asset-upload-name');
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
            showError('Select a file to upload.');
            return;
        }
        if (config.maxBytes && file.size > config.maxBytes) {
            showError('CMS asset uploads must be 20 MB or smaller.');
            return;
        }
        showError('');
        const formData = new FormData();
        formData.append('file', file);
        formData.append('name', nameInput.value || file.name);
        fetch(config.uploadUrl, {
            method: 'POST',
            body: formData,
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken() },
        }).then(response => response.json().then(data => ({ response, data })))
            .then(({ response, data }) => {
                if (!response.ok) throw new Error(data.detail || 'Upload failed.');
                if (data.asset) selectAsset(data.asset);
            })
            .catch(error => showError(error.message || 'Upload failed.'));
    }

    function handleModalClick(event) {
        const actionEl = closestElement(event.target, '[data-asset-action]');
        if (!actionEl) return;
        const action = actionEl.getAttribute('data-asset-action');
        if (action === 'close') {
            closePicker();
            return;
        }
        if (action === 'select') {
            const asset = state.assets.find(item => item.id === actionEl.getAttribute('data-asset-id'));
            if (asset) selectAsset(asset);
        }
    }

    function selectAsset(asset) {
        if (!state.target) return;
        if (state.target.filter === 'image' && !isImage(asset)) {
            showError('Select an image asset for this field.');
            return;
        }
        if (state.target.kind === 'html') {
            insertHtml(state.target.fieldId, htmlSnippet(asset));
        } else {
            insertUrl(state.target, asset.public_url);
        }
        closePicker();
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

    document.addEventListener('click', event => {
        const button = closestElement(event.target, '.cms-asset-picker-trigger');
        if (!button) return;
        event.preventDefault();
        openPicker({
            kind: button.getAttribute('data-asset-target-kind') || 'url',
            blockIdx: parseInt(button.getAttribute('data-block-idx'), 10),
            dataPath: button.getAttribute('data-data-path') || '',
            filter: button.getAttribute('data-asset-filter') || 'any',
            fieldId: button.getAttribute('data-field-id') || '',
        });
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && modal && modal.classList.contains('is-open')) closePicker();
    });

    window.openCmsAssetPicker = openPicker;
})();
