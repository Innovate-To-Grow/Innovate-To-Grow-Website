(function () {
    const {
        config, imageExtensions, hasConfig, extensionList, csrfToken, closestElement, isImage, fileExtension,
        fileSize, modalMarkup, assetRowMarkup, htmlSnippet, insertHtml, insertUrl,
    } = window.ITGCmsAssetPickerHelpers;
    const state = { target: null, assets: [], query: '', loading: false };
    let modal = null;

    function targetAssetType() {
        return state.target && state.target.filter === 'image' ? 'image' : '';
    }

    function ensureModal() {
        if (modal) return modal;
        modal = document.createElement('div');
        modal.className = 'cms-asset-modal';
        modal.innerHTML = modalMarkup();
        document.body.appendChild(modal);
        modal.addEventListener('click', handleModalClick);
        modal.querySelector('#cms-asset-search').addEventListener('input', event => {
            state.query = event.target.value;
        });
        modal.querySelector('#cms-asset-search-submit').addEventListener('click', () => loadAssets());
        modal.querySelector('#cms-asset-upload-file').addEventListener('change', updateSelectedFileName);
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
        updateSelectedFileName();
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

    function updateSelectedFileName() {
        const fileInput = modal && modal.querySelector('#cms-asset-upload-file');
        const fileName = modal && modal.querySelector('#cms-asset-upload-filename');
        if (!fileInput || !fileName) return;
        const file = fileInput.files && fileInput.files[0];
        fileName.textContent = file ? file.name : 'No file selected';
        fileName.classList.toggle('has-file', Boolean(file));
        if (file) showError('');
    }

    function loadAssets() {
        if (!modal || state.loading) return;
        state.loading = true;
        renderAssets();
        const url = new URL(config.listUrl, window.location.origin);
        if (state.query) url.searchParams.set('q', state.query);
        const assetType = targetAssetType();
        if (assetType) url.searchParams.set('type', assetType);
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
        list.innerHTML = state.assets.map(asset => assetRowMarkup(asset, filter)).join('');
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
        if (targetAssetType() === 'image' && !imageExtensions.has(fileExtension(file.name))) {
            showError('Select an image asset for this field.');
            return;
        }
        showError('');
        const formData = new FormData();
        formData.append('file', file);
        formData.append('name', nameInput.value || file.name);
        const uploadUrl = new URL(config.uploadUrl, window.location.origin);
        const assetType = targetAssetType();
        if (assetType) uploadUrl.searchParams.set('type', assetType);
        fetch(uploadUrl.toString(), {
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
